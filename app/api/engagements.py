"""Engagement CRUD endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.audit import append_event, EventType
from app.schemas.api import CreateEngagementRequest, EngagementResponse
from app.settings import get_settings

router = APIRouter(tags=["engagements"])


def _engagement_path(engagement_id: str) -> Path:
    return get_settings().engagement_dir(engagement_id) / "engagement.json"


def _load_engagement(engagement_id: str) -> dict:
    path = _engagement_path(engagement_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    return json.loads(path.read_text())


@router.post("/engagements", response_model=EngagementResponse)
async def create_engagement(req: CreateEngagementRequest):
    settings = get_settings()
    engagement_id = f"ENG-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "engagement_id": engagement_id,
        "engagement_code": req.engagement_code,
        "borrower": req.borrower.model_dump(),
        "lender": req.lender.model_dump(),
        "loan_id": req.loan_id,
        "test_date": str(req.test_date),
        "status": "created",
        "pipeline_stage": "not_started",
        "audit_team": [m.model_dump() for m in req.audit_team],
        "external_egress_enabled": req.external_egress_enabled,
        "llm_provider": req.llm_provider_override or settings.llm_provider,
        "created_at": now,
        "gates": {
            "gate_1_rule_review": "pending",
            "gate_2_mapping_review": "pending",
            "gate_3_exception_investigation": "pending",
            "gate_4_senior": "pending",
            "gate_5_manager": "pending",
            "gate_6_partner": "pending",
        },
    }

    (engagement_dir / "engagement.json").write_text(json.dumps(data, indent=2))

    await append_event(
        engagement_dir, engagement_id, EventType.ENGAGEMENT_CREATED,
        actor={"type": "HUMAN", "id": req.audit_team[0].email if req.audit_team else "system"},
        payload_summary={"engagement_code": req.engagement_code, "borrower": req.borrower.name},
    )

    return EngagementResponse(**data)


@router.get("/engagements/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(engagement_id: str):
    return EngagementResponse(**_load_engagement(engagement_id))


@router.get("/engagements")
async def list_engagements():
    settings = get_settings()
    results = []
    for eng_dir in settings.engagements_dir.iterdir():
        eng_file = eng_dir / "engagement.json"
        if eng_file.exists():
            results.append(json.loads(eng_file.read_text()))
    return results
