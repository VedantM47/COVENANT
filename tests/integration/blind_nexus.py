"""Phase 0 — Blind test for Nexus Industrial Holdings.

Strips engagement_metadata.json to identity-only fields. Runs full pipeline.
The pipeline must independently detect the HARD BREACH at 5.352x > 5.00x threshold
by extracting covenants from the credit agreement PDF and computing from the Excel files.

This test MUST FAIL until Phase 1 is complete.
"""
from __future__ import annotations

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

IDENTITY_FIELDS = {
    "engagement_id", "engagement_type", "audit_firm", "applicable_standards",
    "round", "lender", "borrower", "borrower_ein", "borrower_state",
    "loan_amount_usd", "currency", "testing_date", "testing_period",
    "ltm_period", "engagement_date", "delivery_deadline",
    "auditor_name", "senior_reviewer", "cfo_name",
    "_ebitda_total_column_override",
}

FORBIDDEN_FIELDS = {
    "covenants", "known_errors", "correct_calculation", "borrower_reported",
    "breach", "breach_covenant", "breach_detail", "notes", "input_files",
    "output_evidence_pack", "covenant_ids_to_test",
}


def _make_stripped_metadata(truth: dict) -> dict:
    stripped = {k: v for k, v in truth.items() if k in IDENTITY_FIELDS}
    stripped["_ebitda_total_column_override"] = "LTM Total"
    for field in FORBIDDEN_FIELDS:
        assert field not in stripped, f"Forbidden field '{field}' in stripped metadata"
    return stripped


@pytest.mark.asyncio
async def test_blind_nexus():
    """Blind test: pipeline must detect the hidden breach independently.

    Expected outcome (from truth file):
    - COV-NET-LEVERAGE ratio ≈ 5.352x (within 0.005)
    - is_compliant = False  (BREACH — this is the falsifiability gate)
    - verdict includes BREACH
    - At least one HIGH severity HARD_BREACH exception
    - Both root causes identified independently
    """
    import os
    os.environ["LLM_PROVIDER"] = "mock_replay"
    os.environ["MOCK_REPLAY_FIXTURE"] = "nexus"
    from app.llm_providers.mock_replay import reset_mock_usage
    reset_mock_usage("nexus")
    truth = json.loads(TRUTH_FILE.read_text())
    stripped = _make_stripped_metadata(truth)

    for field in FORBIDDEN_FIELDS:
        assert field not in stripped, f"Test setup error: '{field}' leaked into stripped metadata"

    settings = get_settings()
    engagement_id = f"ENG-BLIND-NX-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    raw_dir = engagement_dir / "raw"
    for f in FIXTURE_DIR.glob("*.pdf"):
        shutil.copy2(f, raw_dir / f.name)
    for f in FIXTURE_DIR.glob("*.xlsx"):
        shutil.copy2(f, raw_dir / f.name)

    doc_paths = list(raw_dir.glob("*"))

    results = await run_pipeline(
        engagement_dir, engagement_id, stripped, doc_paths,
        through_stage="stage_5",
        auto_approve_high_confidence=True,
    )

    stage3 = results["stage3"]
    stage4 = results["stage4"]

    # ── Assert against truth ──────────────────────────────────────────────────

    cov = next(
        (r for r in stage3.results if "LEVERAGE" in r.covenant_id.upper()),
        None,
    )
    assert cov is not None, (
        f"COV-NET-LEVERAGE not found. Covenants: {[r.covenant_id for r in stage3.results]}"
    )

    expected_ratio = truth["correct_calculation"]["net_leverage_ratio"]
    assert abs(cov.ratio_float - expected_ratio) < 0.005, (
        f"Ratio {cov.ratio_float:.4f}x differs from expected {expected_ratio}x"
    )

    # THE BREACH — must be non-compliant
    assert cov.is_compliant is False, (
        f"BREACH NOT DETECTED: ratio={cov.ratio_float:.3f}x > 5.00x threshold "
        f"but is_compliant={cov.is_compliant}. "
        f"This is the falsifiability gate — the platform is incomplete."
    )
    assert truth["breach"] is True

    recon = next(
        (r for r in stage4.covenant_reconciliations if "LEVERAGE" in r.covenant_id.upper()),
        None,
    )
    assert recon is not None
    assert recon.verdict in ("BREACH_WITH_DISCLOSURE_MISMATCH", "BREACH"), (
        f"Expected BREACH verdict, got {recon.verdict}"
    )

    assert any(e.severity == "HIGH" for e in stage4.exceptions), (
        f"No HIGH severity exception: {[(e.type, e.severity) for e in stage4.exceptions]}"
    )
    assert any(e.type == "HARD_BREACH" for e in stage4.exceptions), (
        f"No HARD_BREACH exception: {[e.type for e in stage4.exceptions]}"
    )

    # Both root causes identified independently
    assert recon.root_cause is not None
    err_kinds = {e.get("kind", "") for e in recon.root_cause.identified_errors}
    assert "circular_cap_misapplication" in err_kinds, f"ERR-001 not found: {err_kinds}"
    assert "unsupported_debt_exclusion" in err_kinds, f"ERR-002 not found: {err_kinds}"

    # Borrower overstates EBITDA on Nexus
    if "ebitda" in recon.root_cause.components:
        ebitda_comp = recon.root_cause.components["ebitda"]
        assert ebitda_comp.borrower > ebitda_comp.platform, (
            f"Expected borrower EBITDA > platform on Nexus "
            f"(borrower overstates). Got borrower={ebitda_comp.borrower}, platform={ebitda_comp.platform}"
        )

    # Chain integrity
    chain = verify_chain(engagement_dir)
    assert chain.is_intact, f"Chain broken: {chain.violations}"

    # Confirm real LLM calls
    events_path = engagement_dir / "audit" / "events.jsonl"
    events = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    llm_events = [e for e in events if e.get("event_type") == "LLM_CALL_MADE"]
    real_llm = [e for e in llm_events if e.get("payload_summary", {}).get("provider") != "mock"]
    assert len(real_llm) >= 1, f"No real LLM calls. Events: {[e['payload_summary'] for e in llm_events]}"

    print(f"\nBlind Nexus BREACH: ratio={cov.ratio_float:.4f}x, compliant={cov.is_compliant}, "
          f"exceptions={[(e.type, e.severity) for e in stage4.exceptions]}, "
          f"llm_calls={len(real_llm)}, chain_events={chain.total_events}")
