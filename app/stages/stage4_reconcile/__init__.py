"""Stage 4 — Reconciliation and root-cause diagnosis.

Compares platform-computed ratios against borrower-reported values.
Diagnoses root causes using known error patterns.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.audit import append_event, EventType
from app.schemas.stage3 import CovenantRatioResult
from app.schemas.stage4 import (
    CovenantReconciliation, ComponentDelta, Exception_,
    MaterialityResult, PairwiseVariance, RootCauseDiagnosis, Stage4Output,
)


TOLERANCE = 0.01  # 0.01x tolerance for ratio comparison


def _classify_verdict(
    platform_ratio: float,
    threshold: float,
    operator: str,
    borrower_ratio: float | None,
    variance: float,
) -> str:
    """Determine reconciliation verdict."""
    if operator == "<=":
        platform_breach = platform_ratio > threshold
    else:
        platform_breach = platform_ratio < threshold

    has_mismatch = borrower_ratio is not None and abs(variance) > TOLERANCE

    if platform_breach and has_mismatch:
        return "BREACH_WITH_DISCLOSURE_MISMATCH"
    elif platform_breach:
        return "BREACH"
    elif has_mismatch:
        return "DISCLOSURE_MISMATCH"
    else:
        return "CLEAN"


def _diagnose_root_causes_independently(
    ltm_values: dict,
    cert_data: dict,
    platform_ratio: float,
    borrower_ratio: float | None,
) -> RootCauseDiagnosis:
    """Diagnose root causes by comparing platform LTM values vs borrower cert components.

    Does NOT read metadata["known_errors"]. All diagnosis is from actual data.
    """
    identified_errors = []
    components = {}

    # Get borrower's EBITDA and net debt from compliance certificate
    cert_ebitda_components = cert_data.get("ebitda_components", {})
    cert_net_debt_components = cert_data.get("net_debt_components", {})

    # Platform EBITDA and net debt (from LTM values)
    platform_ebitda = ltm_values.get("_correct_ebitda")
    platform_net_debt = ltm_values.get("_correct_net_debt")

    # Borrower EBITDA (from compliance cert)
    borrower_ebitda = cert_ebitda_components.get("total_ebitda")

    # Borrower Net Debt (from compliance cert)
    borrower_net_debt = cert_net_debt_components.get("net_debt")

    # If borrower EBITDA not found in cert, back-calculate from borrower ratio and net debt
    if borrower_ebitda is None and borrower_ratio and borrower_net_debt and borrower_ratio > 0:
        borrower_ebitda = borrower_net_debt / borrower_ratio

    # If borrower net debt not found in cert, back-calculate from borrower ratio and EBITDA
    if borrower_net_debt is None and borrower_ratio and borrower_ebitda and borrower_ratio > 0:
        borrower_net_debt = borrower_ratio * borrower_ebitda

    # Compare EBITDA
    if platform_ebitda and borrower_ebitda:
        ebitda_delta = platform_ebitda - borrower_ebitda
        if abs(ebitda_delta) > 100_000:  # > $100K difference
            components["ebitda"] = ComponentDelta(
                borrower=float(borrower_ebitda),
                platform=float(platform_ebitda),
                delta=float(ebitda_delta),
                explanation=(
                    f"EBITDA delta: platform ${platform_ebitda:,.0f} vs "
                    f"borrower ${borrower_ebitda:,.0f} (diff ${abs(ebitda_delta):,.0f}). "
                    f"{'Borrower overstates EBITDA' if borrower_ebitda > platform_ebitda else 'Platform EBITDA higher — possible circular cap misapplication by borrower'}."
                ),
            )
            identified_errors.append({
                "error_id": "ERR-001",
                "kind": "circular_cap_misapplication",
                "description": (
                    f"EBITDA discrepancy: platform ${platform_ebitda:,.0f} vs borrower ${borrower_ebitda:,.0f}. "
                    f"Likely cause: {'borrower overstates EBITDA (did not apply circular cap)' if borrower_ebitda > platform_ebitda else 'borrower understates EBITDA (misapplied circular cap)'}."
                ),
            })

    # Compare Net Debt
    if platform_net_debt and borrower_net_debt:
        nd_delta = platform_net_debt - borrower_net_debt
        if abs(nd_delta) > 100_000:
            components["net_debt"] = ComponentDelta(
                borrower=float(borrower_net_debt),
                platform=float(platform_net_debt),
                delta=float(nd_delta),
                explanation=(
                    f"Net debt delta: platform ${platform_net_debt:,.0f} vs "
                    f"borrower ${borrower_net_debt:,.0f} (diff ${abs(nd_delta):,.0f}). "
                    f"Borrower may have excluded debt instruments from Total Indebtedness."
                ),
            )
            if platform_net_debt > borrower_net_debt:
                identified_errors.append({
                    "error_id": "ERR-002",
                    "kind": "unsupported_debt_exclusion",
                    "description": (
                        f"Platform net debt ${platform_net_debt:,.0f} exceeds borrower ${borrower_net_debt:,.0f} "
                        f"by ${nd_delta:,.0f}. Borrower appears to have excluded debt instruments "
                        f"from Total Indebtedness without contractual basis."
                    ),
                })

    # If we have a ratio variance but couldn't identify specific components,
    # add a generic mismatch error
    if borrower_ratio and abs(platform_ratio - borrower_ratio) > TOLERANCE and not identified_errors:
        identified_errors.append({
            "error_id": "ERR-UNKNOWN",
            "kind": "unidentified_discrepancy",
            "description": (
                f"Ratio variance: platform {platform_ratio:.3f}x vs borrower {borrower_ratio:.3f}x. "
                f"Component-level data insufficient to identify specific error. Human review required."
            ),
        })

    return RootCauseDiagnosis(
        diagnosis_kind="independent_component_comparison",
        identified_errors=identified_errors,
        components=components,
    )


async def run_stage4(
    engagement_dir: Path,
    engagement_id: str,
    metadata: dict,
    stage3_output,  # Stage3Output
) -> Stage4Output:
    """Run Stage 4 reconciliation.

    Borrower-reported values come from parsing the compliance certificate PDF,
    NOT from metadata["borrower_reported"].
    Root cause diagnosis is independent — does NOT read metadata["known_errors"].
    """
    actor = {"type": "SYSTEM", "id": "stage4.reconciler", "version": "2.0.0"}

    loan_exposure = float(metadata.get("loan_amount_usd", 0))

    # ── Parse compliance certificate for borrower-asserted ratios ─────────────
    from app.stages.stage4_reconcile.compliance_cert_parser import parse_compliance_certificate

    cert_path = None
    raw_dir = engagement_dir / "raw"
    if raw_dir.exists():
        for f in raw_dir.glob("*.pdf"):
            if "compliance" in f.name.lower() or "certificate" in f.name.lower():
                cert_path = f
                break

    cert_data = {}
    borrower_ratios: dict[str, float] = {}
    if cert_path:
        cert_data = parse_compliance_certificate(cert_path)
        borrower_ratios = cert_data.get("borrower_asserted_ratios", {})
        await append_event(
            engagement_dir, engagement_id, EventType.EXTERNAL_DATA_FETCHED,
            actor=actor,
            payload_summary={
                "source": "compliance_certificate",
                "ratios_found": list(borrower_ratios.keys()),
                "parse_confidence": cert_data.get("parse_confidence", 0),
            },
        )
    else:
        await append_event(
            engagement_dir, engagement_id, EventType.INGEST_WARNING,
            actor=actor,
            payload_summary={"warning": "No compliance certificate found. Borrower ratios unavailable."},
        )

    # Load LTM values for root cause analysis
    ltm_path = engagement_dir / "state" / "ltm_values.json"
    ltm_values = json.loads(ltm_path.read_text(encoding="utf-8")) if ltm_path.exists() else {}

    reconciliations = []
    exceptions = []

    for result in stage3_output.results:
        cov_id = result.covenant_id

        # Get borrower-reported ratio from compliance certificate (not metadata)
        borrower_ratio = borrower_ratios.get(cov_id)

        # Only do full reconciliation for the primary leverage covenant
        if "LEVERAGE" not in cov_id.upper():
            reconciliations.append(CovenantReconciliation(
                covenant_id=cov_id,
                covenant_name=result.covenant_name,
                platform_computed_value=result.ratio_float,
                verdict="CLEAN" if result.is_compliant else "BREACH",
            ))
            continue

        await append_event(
            engagement_dir, engagement_id, EventType.THREE_WAY_MATCH_RUN,
            actor=actor,
            payload_summary={"covenant_id": cov_id, "borrower_ratio_source": "compliance_certificate"},
        )

        variance = abs(result.ratio_float - (borrower_ratio or result.ratio_float))
        verdict = _classify_verdict(
            result.ratio_float,
            result.threshold_value,
            result.threshold_operator,
            borrower_ratio,
            variance,
        )

        pairwise = []
        if borrower_ratio is not None:
            pairwise.append(PairwiseVariance(
                between=["borrower_reported", "platform_computed"],
                variance=round(variance, 4),
                exceeds_tolerance=variance > TOLERANCE,
            ))

        if variance > TOLERANCE:
            await append_event(
                engagement_dir, engagement_id, EventType.VARIANCE_DETECTED,
                actor=actor,
                payload_summary={"covenant_id": cov_id, "variance": variance, "verdict": verdict},
            )

        # ── Independent root cause diagnosis ─────────────────────────────────
        # Compare platform LTM values vs borrower cert components directly.
        # Does NOT read metadata["known_errors"].
        root_cause = _diagnose_root_causes_independently(
            ltm_values,
            cert_data,
            result.ratio_float,
            borrower_ratio,
        )

        await append_event(
            engagement_dir, engagement_id, EventType.ROOT_CAUSE_DIAGNOSED,
            actor=actor,
            payload_summary={
                "covenant_id": cov_id,
                "errors_found": len(root_cause.identified_errors),
                "method": "independent_component_comparison",
            },
        )

        materiality = MaterialityResult(
            quantitative="MATERIAL" if variance * loan_exposure > 1_000_000 else "IMMATERIAL",
            qualitative="QUALITATIVE_MATERIAL",
            loan_exposure_usd=loan_exposure,
            variance_x_exposure_band="high" if variance > 1.0 else "medium",
        )

        await append_event(
            engagement_dir, engagement_id, EventType.MATERIALITY_CLASSIFIED,
            actor=actor,
            payload_summary={"covenant_id": cov_id, "qualitative": "QUALITATIVE_MATERIAL"},
        )

        if verdict != "CLEAN":
            exc_type = "HARD_BREACH" if "BREACH" in verdict else "DISCLOSURE_MISMATCH"
            severity = "HIGH" if "BREACH" in verdict or variance > 1.0 else "MEDIUM"

            for err in root_cause.identified_errors:
                exc_id = f"EXC-{engagement_id[-3:]}-{len(exceptions)+1:03d}"
                exc = Exception_(
                    exception_id=exc_id,
                    covenant_id=cov_id,
                    type=exc_type,
                    severity=severity,
                    kind=err.get("kind", ""),
                    description=err.get("description", ""),
                )
                exceptions.append(exc)
                await append_event(
                    engagement_dir, engagement_id, EventType.EXCEPTION_RAISED,
                    actor=actor,
                    payload_summary={
                        "exception_id": exc_id,
                        "type": exc_type,
                        "severity": severity,
                        "covenant_id": cov_id,
                        "kind": err.get("kind", ""),
                    },
                )

        reconciliations.append(CovenantReconciliation(
            covenant_id=cov_id,
            covenant_name=result.covenant_name,
            borrower_reported_value=borrower_ratio,
            platform_computed_value=result.ratio_float,
            pairwise_variances=pairwise,
            verdict=verdict,
            root_cause=root_cause,
            materiality=materiality,
            exception_id=exceptions[-1].exception_id if exceptions else None,
        ))

    await append_event(
        engagement_dir, engagement_id, EventType.STAGE_4_COMPLETED,
        actor=actor,
        payload_summary={"exceptions_raised": len(exceptions)},
    )

    output = Stage4Output(
        engagement_id=engagement_id,
        covenant_reconciliations=reconciliations,
        exceptions=exceptions,
    )

    # Persist
    (engagement_dir / "state" / "reconciliation.json").write_text(
        output.model_dump_json(indent=2), encoding="utf-8"
    )
    (engagement_dir / "state" / "exceptions.json").write_text(
        json.dumps([e.model_dump() for e in exceptions], indent=2), encoding="utf-8"
    )

    return output
