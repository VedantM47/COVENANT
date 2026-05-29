"""Phase 0 — Blind test for FirstBank.

Strips engagement_metadata.json to identity-only fields (no covenants, no known_errors,
no correct_calculation, no borrower_reported). Runs the full pipeline against raw files only.
Asserts outputs against the original truth file.

This test MUST FAIL until Phase 1 is complete (Stage 1 currently reads metadata["covenants"]).
When Phase 1 is done, this test must pass with ratio ≈ 1.374x and disclosure mismatch surfaced.
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

FIXTURE_DIR = Path("D:/covenant/test_inputs/firstbank")
TRUTH_FILE = FIXTURE_DIR / "engagement_metadata.json"

# Identity-only fields allowed in the stripped metadata
IDENTITY_FIELDS = {
    "engagement_id", "engagement_type", "audit_firm", "applicable_standards",
    "round", "lender", "borrower", "borrower_ein", "borrower_state",
    "loan_amount_usd", "currency", "testing_date", "testing_period",
    "ltm_period", "engagement_date", "delivery_deadline",
    "auditor_name", "senior_reviewer", "cfo_name",
    # Column override for EBITDA bridge ambiguity resolution (gate 2 decision)
    "_ebitda_total_column_override",
}

# Fields that are FORBIDDEN in the stripped metadata (pipeline must not see these)
FORBIDDEN_FIELDS = {
    "covenants", "known_errors", "correct_calculation", "borrower_reported",
    "breach", "breach_covenant", "breach_detail", "notes", "input_files",
    "output_evidence_pack", "covenant_ids_to_test",
}


def _make_stripped_metadata(truth: dict) -> dict:
    """Return metadata with only identity fields. Raises if forbidden fields remain."""
    stripped = {k: v for k, v in truth.items() if k in IDENTITY_FIELDS}
    # Inject gate-2 column override (simulates human decision at gate 2)
    stripped["_ebitda_total_column_override"] = "Q4-2024"
    # Verify no forbidden fields leaked through
    for field in FORBIDDEN_FIELDS:
        assert field not in stripped, f"Forbidden field '{field}' in stripped metadata"
    return stripped


@pytest.mark.asyncio
async def test_blind_firstbank():
    """Blind test: pipeline must extract covenants from PDFs, not from metadata.

    Expected outcome (from truth file):
    - COV-NET-LEVERAGE ratio ≈ 1.374x (within 0.005)
    - is_compliant = True
    - verdict = DISCLOSURE_MISMATCH
    - variance ≈ 2.854x
    - Both root causes identified: circular_cap_misapplication + unsupported_debt_exclusion
    """
    import os
    os.environ["LLM_PROVIDER"] = "mock_replay"
    os.environ["MOCK_REPLAY_FIXTURE"] = "firstbank"
    from app.llm_providers.mock_replay import reset_mock_usage
    reset_mock_usage("firstbank")
    truth = json.loads(TRUTH_FILE.read_text())
    stripped = _make_stripped_metadata(truth)

    # Verify the stripped metadata truly has no forbidden fields
    for field in FORBIDDEN_FIELDS:
        assert field not in stripped, f"Test setup error: '{field}' leaked into stripped metadata"

    settings = get_settings()
    engagement_id = f"ENG-BLIND-FB-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    # Copy only raw input files — no metadata
    raw_dir = engagement_dir / "raw"
    for f in FIXTURE_DIR.glob("*.pdf"):
        shutil.copy2(f, raw_dir / f.name)
    for f in FIXTURE_DIR.glob("*.xlsx"):
        shutil.copy2(f, raw_dir / f.name)

    doc_paths = list(raw_dir.glob("*"))

    # Run pipeline with stripped metadata (no covenant truth, no known_errors)
    results = await run_pipeline(
        engagement_dir, engagement_id, stripped, doc_paths,
        through_stage="stage_5",
        auto_approve_high_confidence=True,
    )

    stage3 = results["stage3"]
    stage4 = results["stage4"]

    # ── Assert against truth (loaded from truth file, never passed to pipeline) ──

    # Find leverage covenant
    cov = next(
        (r for r in stage3.results if "LEVERAGE" in r.covenant_id.upper()),
        None,
    )
    assert cov is not None, (
        f"COV-NET-LEVERAGE not found. Covenants computed: "
        f"{[r.covenant_id for r in stage3.results]}"
    )

    expected_ratio = truth["correct_calculation"]["net_leverage_ratio"]
    assert abs(cov.ratio_float - expected_ratio) < 0.005, (
        f"Ratio {cov.ratio_float:.4f}x differs from expected {expected_ratio}x by "
        f"{abs(cov.ratio_float - expected_ratio):.4f} (tolerance 0.005)"
    )

    assert cov.is_compliant is True, f"Expected compliant=True, got {cov.is_compliant}"

    # Reconciliation
    recon = next(
        (r for r in stage4.covenant_reconciliations if "LEVERAGE" in r.covenant_id.upper()),
        None,
    )
    assert recon is not None, "No reconciliation for COV-NET-LEVERAGE"
    assert recon.verdict == "DISCLOSURE_MISMATCH", f"Expected DISCLOSURE_MISMATCH, got {recon.verdict}"

    expected_variance = truth["correct_calculation"]["variance"]
    if recon.pairwise_variances:
        actual_variance = recon.pairwise_variances[0].variance
        assert abs(actual_variance - expected_variance) < 0.01, (
            f"Variance {actual_variance:.4f}x differs from expected {expected_variance}x"
        )

    # Both root causes identified independently (not from metadata["known_errors"])
    assert recon.root_cause is not None
    err_kinds = {e.get("kind", "") for e in recon.root_cause.identified_errors}
    assert "circular_cap_misapplication" in err_kinds, (
        f"ERR-001 (circular_cap_misapplication) not found. Found: {err_kinds}"
    )
    assert "unsupported_debt_exclusion" in err_kinds, (
        f"ERR-002 (unsupported_debt_exclusion) not found. Found: {err_kinds}"
    )

    # Chain integrity
    chain = verify_chain(engagement_dir)
    assert chain.is_intact, f"Chain broken: {chain.violations}"
    assert chain.total_events >= 20

    # Confirm at least one real LLM call was made (not mock)
    events_path = engagement_dir / "audit" / "events.jsonl"
    events = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    llm_events = [e for e in events if e.get("event_type") == "LLM_CALL_MADE"]
    assert len(llm_events) >= 1, "No LLM_CALL_MADE events found — extraction did not call LLM"
    real_llm = [e for e in llm_events if e.get("payload_summary", {}).get("provider") != "mock"]
    assert len(real_llm) >= 1, (
        f"All LLM calls used mock provider. Events: "
        f"{[e['payload_summary'] for e in llm_events]}"
    )

    print(f"\nBlind FirstBank: ratio={cov.ratio_float:.4f}x, compliant={cov.is_compliant}, "
          f"variance={recon.pairwise_variances[0].variance if recon.pairwise_variances else 'N/A'}x, "
          f"llm_calls={len(real_llm)}, chain_events={chain.total_events}")
