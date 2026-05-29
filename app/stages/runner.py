"""Pipeline orchestrator — runs stages 0-5 in order."""
from __future__ import annotations

import json
from pathlib import Path

from app.audit import append_event, EventType
from app.stages.stage0_ingest import run_stage0
from app.stages.stage1_extract import run_stage1
from app.stages.stage2_normalize import run_stage2
from app.stages.stage3_calculate import run_stage3
from app.stages.stage4_reconcile import run_stage4
from app.stages.stage5_evidence import run_stage5


async def run_pipeline(
    engagement_dir: Path,
    engagement_id: str,
    metadata: dict,
    document_paths: list[Path],
    through_stage: str = "stage_5",
    auto_approve_high_confidence: bool = False,
    sign_offs: list[dict] | None = None,
) -> dict:
    """Run the full pipeline. Returns a dict with all stage outputs."""
    actor = {"type": "SYSTEM", "id": "pipeline.runner", "version": "1.0.0"}

    await append_event(
        engagement_dir, engagement_id, EventType.PIPELINE_STARTED,
        actor=actor,
        payload_summary={"through_stage": through_stage},
    )

    results = {}

    # Stage 0 — Ingest
    stage0 = await run_stage0(engagement_dir, engagement_id, document_paths)
    results["stage0"] = stage0

    if through_stage == "stage_0":
        return results

    # Stage 1 — Extract
    stage1 = await run_stage1(engagement_dir, engagement_id, metadata)
    results["stage1"] = stage1

    if through_stage == "stage_1":
        return results

    # Gate 1 — auto-approve if requested
    if auto_approve_high_confidence:
        await append_event(
            engagement_dir, engagement_id, EventType.RULE_APPROVED,
            actor={"type": "HUMAN", "id": "auto_approve", "version": "1.0.0"},
            payload_summary={"auto_approved": True, "covenant_count": len(stage1.covenants)},
        )

    # Stage 2 — Normalize
    stage2, ltm_values = await run_stage2(
        engagement_dir, engagement_id, metadata,
        [c.model_dump() for c in stage1.covenants],
    )
    results["stage2"] = stage2

    if through_stage == "stage_2":
        return results

    # Gate 2 — auto-approve
    if auto_approve_high_confidence:
        await append_event(
            engagement_dir, engagement_id, EventType.MAPPING_APPROVED,
            actor={"type": "HUMAN", "id": "auto_approve", "version": "1.0.0"},
            payload_summary={"auto_approved": True},
        )

    # Stage 3 — Calculate
    stage3 = await run_stage3(
        engagement_dir, engagement_id,
        [c.model_dump() for c in stage1.covenants],
        ltm_values,
        metadata.get("testing_date", "2024-12-31"),
    )
    results["stage3"] = stage3

    if through_stage == "stage_3":
        return results

    # Stage 4 — Reconcile
    stage4 = await run_stage4(
        engagement_dir, engagement_id, metadata, stage3
    )
    results["stage4"] = stage4

    if through_stage == "stage_4":
        return results

    # Gate 3 — auto-approve
    if auto_approve_high_confidence:
        await append_event(
            engagement_dir, engagement_id, EventType.EXCEPTION_CONCLUSION_SET,
            actor={"type": "HUMAN", "id": "auto_approve", "version": "1.0.0"},
            payload_summary={"auto_approved": True},
        )

    # Stage 5 — Seal
    stage5 = await run_stage5(
        engagement_dir, engagement_id, metadata, stage3, stage4, sign_offs
    )
    results["stage5"] = stage5

    return results
