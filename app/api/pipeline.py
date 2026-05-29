"""Pipeline control endpoints."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.settings import get_settings
from app.stages.runner import run_pipeline

router = APIRouter(tags=["pipeline"])


@router.post("/engagements/{engagement_id}/pipeline/start")
async def start_pipeline(engagement_id: str, background_tasks: BackgroundTasks):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    if not engagement_dir.exists():
        raise HTTPException(status_code=404, detail="Engagement not found")

    eng_data = json.loads((engagement_dir / "engagement.json").read_text())
    doc_paths = list((engagement_dir / "raw").glob("*")) if (engagement_dir / "raw").exists() else []

    # Run in background
    background_tasks.add_task(
        _run_pipeline_bg, engagement_dir, engagement_id, eng_data, doc_paths
    )
    return {"status": "started", "engagement_id": engagement_id}


async def _run_pipeline_bg(engagement_dir, engagement_id, eng_data, doc_paths):
    try:
        await run_pipeline(
            engagement_dir, engagement_id, eng_data, doc_paths,
            auto_approve_high_confidence=True,
        )
    except Exception as e:
        from app.audit import append_event, EventType
        await append_event(
            engagement_dir, engagement_id, EventType.PIPELINE_FAILED,
            actor={"type": "SYSTEM", "id": "pipeline"},
            payload_summary={"error": str(e)},
        )


@router.get("/engagements/{engagement_id}/pipeline/status")
async def pipeline_status(engagement_id: str):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    state_dir = engagement_dir / "state"
    stages_done = [f.stem for f in state_dir.glob("*.json")] if state_dir.exists() else []
    return {"engagement_id": engagement_id, "stages_completed": stages_done}
