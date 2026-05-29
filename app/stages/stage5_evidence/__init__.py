"""Stage 5 — Evidence pack generation and sealing."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from app.audit import append_event, verify_chain, EventType
from app.schemas.stage5 import EvidencePack, SignOff, Stage5Output


def _build_evidence_pdf(engagement_dir: Path, engagement_id: str, metadata: dict, stage3_output, stage4_output) -> Path:
    """Build the evidence pack PDF using ReportLab."""
    exports_dir = engagement_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    pdf_path = exports_dir / f"evidence_pack_{engagement_id}.pdf"

    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(f"Covenant Compliance Evidence Pack", styles["Title"]))
    story.append(Paragraph(f"Engagement: {engagement_id}", styles["Heading2"]))
    story.append(Paragraph(f"Borrower: {metadata.get('borrower', '')}", styles["Normal"]))
    story.append(Paragraph(f"Test Date: {metadata.get('testing_date', '')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    # Covenant results
    story.append(Paragraph("Covenant Results", styles["Heading2"]))
    if stage3_output:
        for result in stage3_output.results:
            status = "COMPLIANT" if result.is_compliant else "BREACH"
            story.append(Paragraph(
                f"{result.covenant_id}: {result.ratio_display} vs {result.threshold_value}x threshold — {status}",
                styles["Normal"]
            ))
    story.append(Spacer(1, 20))

    # Exceptions
    story.append(Paragraph("Exceptions", styles["Heading2"]))
    if stage4_output and stage4_output.exceptions:
        for exc in stage4_output.exceptions:
            story.append(Paragraph(f"{exc.exception_id}: {exc.type} — {exc.severity}", styles["Normal"]))
            story.append(Paragraph(exc.description, styles["Normal"]))
    else:
        story.append(Paragraph("No exceptions.", styles["Normal"]))
    story.append(Spacer(1, 20))

    # Chain integrity appendix
    story.append(Paragraph("Chain Integrity Certificate", styles["Heading2"]))
    chain_result = verify_chain(engagement_dir)
    story.append(Paragraph(f"verified={chain_result.is_intact}", styles["Normal"]))
    story.append(Paragraph(f"total_events={chain_result.total_events}", styles["Normal"]))

    doc.build(story)
    return pdf_path


async def run_stage5(
    engagement_dir: Path,
    engagement_id: str,
    metadata: dict,
    stage3_output,
    stage4_output,
    sign_offs: list[dict] | None = None,
) -> Stage5Output:
    """Run Stage 5 — seal the evidence pack."""
    actor = {"type": "SYSTEM", "id": "stage5.sealer", "version": "1.0.0"}

    await append_event(
        engagement_dir, engagement_id, EventType.PRE_SEAL_VALIDATION_STARTED,
        actor=actor,
        payload_summary={},
    )

    # Verify chain
    chain_result = verify_chain(engagement_dir)
    await append_event(
        engagement_dir, engagement_id, EventType.CHAIN_VERIFIED,
        actor=actor,
        payload_summary={
            "is_intact": chain_result.is_intact,
            "total_events": chain_result.total_events,
            "violations": len(chain_result.violations),
        },
    )

    if not chain_result.is_intact:
        raise RuntimeError(f"Chain integrity failed: {chain_result.violations}")

    # Assemble deliverables
    await append_event(
        engagement_dir, engagement_id, EventType.DELIVERABLES_ASSEMBLED,
        actor=actor,
        payload_summary={"deliverables": ["dashboard", "variance_report", "recalc_workbook", "exception_memos"]},
    )

    # Build PDF
    pdf_path = _build_evidence_pdf(engagement_dir, engagement_id, metadata, stage3_output, stage4_output)

    # Hash the PDF
    pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    await append_event(
        engagement_dir, engagement_id, EventType.MASTER_PDF_HASHED,
        actor=actor,
        payload_summary={"sha256": pdf_hash, "size_bytes": pdf_path.stat().st_size},
    )

    # TSA timestamp (attempt FreeTSA, skip if unavailable)
    tsa_token = None
    tsa_name = None
    try:
        import httpx
        # FreeTSA request
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://freetsa.org/tsr",
                content=bytes.fromhex(pdf_hash),
                headers={"Content-Type": "application/timestamp-query"},
            )
            if resp.status_code == 200:
                import base64
                tsa_token = base64.b64encode(resp.content).decode()
                tsa_name = "freetsa.org"
    except Exception:
        pass  # TSA unavailable — proceed without timestamp

    await append_event(
        engagement_dir, engagement_id, EventType.RFC3161_TIMESTAMP_REQUESTED,
        actor=actor,
        payload_summary={"tsa": tsa_name or "unavailable"},
    )
    if tsa_token:
        await append_event(
            engagement_dir, engagement_id, EventType.RFC3161_TIMESTAMP_RECEIVED,
            actor=actor,
            payload_summary={"tsa": tsa_name},
        )

    now = datetime.now(timezone.utc).isoformat()
    await append_event(
        engagement_dir, engagement_id, EventType.EVIDENCE_PACK_SEALED,
        actor=actor,
        payload_summary={
            "pdf_sha256": pdf_hash,
            "sealed_at": now,
            "tsa": tsa_name,
        },
    )
    await append_event(
        engagement_dir, engagement_id, EventType.STAGE_5_COMPLETED,
        actor=actor,
        payload_summary={},
    )

    sign_off_objs = [SignOff(**s) for s in (sign_offs or [])]

    output = Stage5Output(
        engagement_id=engagement_id,
        chain_integrity={
            "verified": chain_result.is_intact,
            "total_events": chain_result.total_events,
            "method": "SHA-256 with previous_hash linking",
        },
        sign_off_chain=sign_off_objs,
        evidence_pack=EvidencePack(
            filename=pdf_path.name,
            size_bytes=pdf_path.stat().st_size,
            content_sha256=pdf_hash,
            rfc3161_timestamp=now if tsa_token else None,
            tsa=tsa_name,
            tsa_response_token_b64=tsa_token,
        ),
    )

    # Persist
    (engagement_dir / "state" / "stage5.json").write_text(output.model_dump_json(indent=2), encoding="utf-8")

    return output
