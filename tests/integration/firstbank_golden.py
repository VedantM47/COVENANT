"""FirstBank golden test — ENG-2025-001.

Borrower reports 4.228x compliant.
Platform must compute ≈1.374x compliant with 2.854x variance.
Both root causes must be identified.
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

FIXTURE_DIR = Path("D:/covenant/test_inputs/firstbank")
TRUTH_FILE = FIXTURE_DIR / "engagement_metadata.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def create_engagement_from_fixture(fixture_dir: Path) -> tuple[Path, str, dict]:
    """Create a fresh engagement directory from fixture files."""
    settings = get_settings()
    engagement_id = f"ENG-TEST-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    # Copy fixture files to raw/
    raw_dir = engagement_dir / "raw"
    for f in fixture_dir.glob("*.pdf"):
        shutil.copy2(f, raw_dir / f.name)
    for f in fixture_dir.glob("*.xlsx"):
        shutil.copy2(f, raw_dir / f.name)

    metadata = load_json(fixture_dir / "engagement_metadata.json")
    return engagement_dir, engagement_id, metadata


def run_pipeline_through(engagement_dir, engagement_id, metadata, through_stage, auto_approve):
    """Synchronous wrapper for the async pipeline."""
    doc_paths = list((engagement_dir / "raw").glob("*"))
    return asyncio.run(run_pipeline(
        engagement_dir, engagement_id, metadata, doc_paths,
        through_stage=through_stage,
        auto_approve_high_confidence=auto_approve,
    ))


@pytest.mark.asyncio
async def test_firstbank_end_to_end():
    """FirstBank golden test — both errors present, both compliant, 2.854x variance."""
    import os
    os.environ["LLM_PROVIDER"] = "mock_replay"
    os.environ["MOCK_REPLAY_FIXTURE"] = "firstbank"
    from app.llm_providers.mock_replay import reset_mock_usage
    reset_mock_usage("firstbank")

    truth = load_json(TRUTH_FILE)
    engagement_dir, engagement_id, metadata = create_engagement_from_fixture(FIXTURE_DIR)

    # Simulate human gate 2 decision: FirstBank EBITDA bridge uses Q4-2024 column
    # as the LTM total (fixture design). Human confirms this at gate 2.
    metadata["_ebitda_total_column_override"] = "Q4-2024"

    doc_paths = list((engagement_dir / "raw").glob("*"))
    results = await run_pipeline(
        engagement_dir, engagement_id, metadata, doc_paths,
        through_stage="stage_5",
        auto_approve_high_confidence=True,
    )

    stage3 = results["stage3"]
    stage4 = results["stage4"]

    # Find the leverage covenant result
    cov = next(
        (r for r in stage3.results if "LEVERAGE" in r.covenant_id.upper()),
        None
    )
    assert cov is not None, "COV-NET-LEVERAGE not found in stage3 results"

    # Platform ratio must be ≈1.374x (within 0.005)
    expected_ratio = truth["correct_calculation"]["net_leverage_ratio"]
    assert abs(cov.ratio_float - expected_ratio) < 0.005, (
        f"Expected ratio ≈{expected_ratio}, got {cov.ratio_float}"
    )

    # Must be compliant
    assert cov.is_compliant is True, f"Expected compliant=True, got {cov.is_compliant}"
    assert truth["correct_calculation"]["compliant"] is True

    # Find reconciliation for leverage covenant
    recon = next(
        (r for r in stage4.covenant_reconciliations if "LEVERAGE" in r.covenant_id.upper()),
        None
    )
    assert recon is not None, "No reconciliation for COV-NET-LEVERAGE"
    assert recon.verdict == "DISCLOSURE_MISMATCH", f"Expected DISCLOSURE_MISMATCH, got {recon.verdict}"

    # Variance ≈2.854x
    expected_variance = truth["correct_calculation"]["variance"]
    if recon.pairwise_variances:
        actual_variance = recon.pairwise_variances[0].variance
        assert abs(actual_variance - expected_variance) < 0.01, (
            f"Expected variance ≈{expected_variance}, got {actual_variance}"
        )

    # Both root causes identified
    assert recon.root_cause is not None
    err_types = {e.get("kind", "") for e in recon.root_cause.identified_errors}
    assert "circular_cap_misapplication" in err_types, f"ERR-001 not found in {err_types}"
    assert "unsupported_debt_exclusion" in err_types, f"ERR-002 not found in {err_types}"

    # EBITDA delta
    if "ebitda" in recon.root_cause.components:
        ebitda_comp = recon.root_cause.components["ebitda"]
        expected_borrower_ebitda = truth["known_errors"]["ERR-001"]["borrower_ebitda"]
        expected_correct_ebitda = truth["known_errors"]["ERR-001"]["correct_ebitda"]
        assert abs(ebitda_comp.borrower - expected_borrower_ebitda) < 1000, (
            f"Borrower EBITDA mismatch: {ebitda_comp.borrower} vs {expected_borrower_ebitda}"
        )
        assert abs(ebitda_comp.platform - expected_correct_ebitda) < 1000, (
            f"Platform EBITDA mismatch: {ebitda_comp.platform} vs {expected_correct_ebitda}"
        )

    # Net debt delta
    if "net_debt" in recon.root_cause.components:
        nd_comp = recon.root_cause.components["net_debt"]
        expected_borrower_nd = truth["known_errors"]["ERR-002"]["borrower_net_debt"]
        expected_correct_nd = truth["known_errors"]["ERR-002"]["correct_net_debt"]
        assert abs(nd_comp.borrower - expected_borrower_nd) < 1000
        assert abs(nd_comp.platform - expected_correct_nd) < 1000

    # Exceptions raised
    assert len(stage4.exceptions) > 0, "No exceptions raised"

    # Chain integrity
    chain = verify_chain(engagement_dir)
    assert chain.is_intact, f"Chain broken: {chain.violations}"
    assert chain.total_events >= 20, f"Too few events: {chain.total_events}"

    print(f"\nPASS FirstBank: ratio={cov.ratio_float:.3f}x, compliant={cov.is_compliant}, "
          f"variance={recon.pairwise_variances[0].variance if recon.pairwise_variances else 'N/A'}x, "
          f"chain_events={chain.total_events}")
