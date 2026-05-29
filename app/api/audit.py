"""Audit trail endpoints."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from app.settings import get_settings
from app.audit import verify_chain

router = APIRouter(tags=["audit"])


@router.get("/engagements/{engagement_id}/audit/events")
async def get_audit_events(engagement_id: str, stage: str | None = None):
    settings = get_settings()
    events_path = settings.engagement_dir(engagement_id) / "audit" / "events.jsonl"
    if not events_path.exists():
        return []
    events = []
    with open(events_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ev = json.loads(line)
                if stage is None or stage in ev.get("event_category", ""):
                    events.append(ev)
    return events


@router.post("/engagements/{engagement_id}/audit/verify")
async def verify_audit_chain(engagement_id: str):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    result = verify_chain(engagement_dir)
    return {
        "is_intact": result.is_intact,
        "total_events": result.total_events,
        "violations": result.violations,
    }
