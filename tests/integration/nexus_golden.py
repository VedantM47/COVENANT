"""Nexus golden test — ENG-2025-002. THE FALSIFIABILITY GATE.

Borrower reports 4.574x compliant.
Platform must compute ≈5.352x — a HARD BREACH (threshold 5.00x).
Two compounding errors must both be caught.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.audit import verify_chain
from app.settings import get_settings
from app.stages.runner import run_pipeline

FIXTURE_DIR = Path("D:/covenant/test_inputs/nexus")
TRUTH_FILE = FIXTURE_DIR / "engagement_metadata.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def create_engagement_from_fixture(fixture_dir: Path) -> tuple[Path, str, dict]:
    settings = get_settings()
    engagement_id = f"ENG-TEST-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    raw_dir = engagement_dir / "raw"
    for f in fixture_dir.glob("*.pdf"):
        shutil.copy2(f, raw_dir / f.name)
    for f in fixture_dir.glob("*.xlsx"):
        shutil.copy2(f, raw_dir / f.name)

    metadata = load_json(fixture_dir / "engagement_metadata.json")
    return engagement_dir, engagement_id, metadata


@pytest.mark.asyncio
async def test_nexus_end_to_end_breach_caught():
    """Nexus golden test — hidden breach must be detected."""
    import os
    os.environ["LLM_PROVIDER"] = "mock_replay"
    os.environ["MOCK_REPLAY_FIXTURE"] = "nexus"
    from app.llm_providers.mock_replay import reset_mock_usage
    reset_mock_usage("nexus")

    truth = load_json(TRUTH_FILE)
    engagement_dir, engagement_id, metadata = create_engagement_from_fixture(FIXTURE_DIR)

    # Simulate human gate 2 decision: Nexus EBITDA bridge uses LTM Total column.
    # Human confirms this at gate 2.
    metadata["_ebitda_total_column_override"] = "LTM Total"

    doc_paths = list((engagement_dir / "raw").glob("*"))
    results = await run_pipeline(
        engagement_dir, engagement_id, metadata, doc_paths,
        through_stage="stage_5",
        auto_approve_high_confidence=True,
    )

    stage3 = results["stage3"]
    stage4 = results["stage4"]

    # Find leverage covenant
    cov = next(
        (r for r in stage3.results if "LEVERAGE" in r.covenant_id.upper()),
        None
    )
    assert cov is not None, "COV-NET-LEVERAGE not found"

    # Platform ratio must be ≈5.352x (within 0.005)
    expected_ratio = truth["correct_calculation"]["net_leverage_ratio"]
    assert abs(cov.ratio_float - expected_ratio) < 0.005, (
        f"Expected ratio ≈{expected_ratio}, got {cov.ratio_float:.4f}"
    )

    # THE BREACH — must be non-compliant
    assert cov.is_compliant is False, (
        f"BREACH NOT DETECTED: ratio={cov.ratio_float:.3f}x > 5.00x threshold but is_compliant=True"
    )
    assert truth["breach"] is True

    # Reconciliation verdict must include BREACH
    recon = next(
        (r for r in stage4.covenant_reconciliations if "LEVERAGE" in r.covenant_id.upper()),
        None
    )
    assert recon is not None
    assert recon.verdict in ("BREACH_WITH_DISCLOSURE_MISMATCH", "BREACH"), (
        f"Expected BREACH verdict, got {recon.verdict}"
    )

    # Must have HIGH severity exception
    assert any(e.severity == "HIGH" for e in stage4.exceptions), (
        f"No HIGH severity exception found: {[(e.type, e.severity) for e in stage4.exceptions]}"
    )
    assert any(e.type == "HARD_BREACH" for e in stage4.exceptions), (
        f"No HARD_BREACH exception found: {[e.type for e in stage4.exceptions]}"
    )

    # Both root causes identified
    assert recon.root_cause is not None
    err_types = {e.get("kind", "") for e in recon.root_cause.identified_errors}
    assert "circular_cap_misapplication" in err_types, f"ERR-001 not found in {err_types}"
    assert "unsupported_debt_exclusion" in err_types, f"ERR-002 not found in {err_types}"

    # Borrower OVERSTATES EBITDA on Nexus (opposite of FirstBank)
    if "ebitda" in recon.root_cause.components:
        ebitda_comp = recon.root_cause.components["ebitda"]
        assert ebitda_comp.borrower > ebitda_comp.platform, (
            f"Expected borrower EBITDA > platform EBITDA on Nexus, "
            f"got borrower={ebitda_comp.borrower}, platform={ebitda_comp.platform}"
        )

    # Net debt: borrower understates (excludes Mezz $85M)
    if "net_debt" in recon.root_cause.components:
        nd_comp = recon.root_cause.components["net_debt"]
        expected_borrower_nd = truth["known_errors"]["ERR-002"]["borrower_net_debt"]
        expected_correct_nd = truth["known_errors"]["ERR-002"]["correct_net_debt"]
        assert abs(nd_comp.borrower - expected_borrower_nd) < 1000
        assert abs(nd_comp.platform - expected_correct_nd) < 1000

    # Chain integrity
    chain = verify_chain(engagement_dir)
    assert chain.is_intact, f"Chain broken: {chain.violations}"

    print(f"\nPASS Nexus BREACH DETECTED: ratio={cov.ratio_float:.3f}x > 5.00x threshold, "
          f"is_compliant={cov.is_compliant}, "
          f"exceptions={[(e.type, e.severity) for e in stage4.exceptions]}, "
          f"chain_events={chain.total_events}")
