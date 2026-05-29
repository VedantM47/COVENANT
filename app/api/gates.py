"""Human gate endpoints."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from app.settings import get_settings
from app.audit import append_event, EventType
from app.schemas.api import GateApproveRequest, GateSignOffRequest

router = APIRouter(tags=["gates"])

VALID_GATES = [
    "gate_1_rule_review", "gate_2_mapping_review", "gate_3_exception_investigation",
    "gate_4_senior", "gate_5_manager", "gate_6_partner",
]


@router.get("/engagements/{engagement_id}/gates/{gate_id}")
async def get_gate(engagement_id: str, gate_id: str):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    eng_file = engagement_dir / "engagement.json"
    if not eng_file.exists():
        raise HTTPException(status_code=404)
    eng = json.loads(eng_file.read_text())
    return {"gate_id": gate_id, "status": eng.get("gates", {}).get(gate_id, "pending")}


@router.post("/engagements/{engagement_id}/gates/{gate_id}/approve")
async def approve_gate(engagement_id: str, gate_id: str, req: GateApproveRequest):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    eng_file = engagement_dir / "engagement.json"
    if not eng_file.exists():
        raise HTTPException(status_code=404)

    eng = json.loads(eng_file.read_text())
    eng["gates"][gate_id] = "approved"
    eng_file.write_text(json.dumps(eng, indent=2))

    await append_event(
        engagement_dir, engagement_id, EventType.RULE_APPROVED,
        actor={"type": "HUMAN", "id": req.approver_email},
        payload_summary={"gate_id": gate_id, "notes": req.notes},
    )
    return {"gate_id": gate_id, "status": "approved"}


@router.post("/engagements/{engagement_id}/gates/{gate_id}/sign-off")
async def sign_off_gate(engagement_id: str, gate_id: str, req: GateSignOffRequest):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    eng_file = engagement_dir / "engagement.json"
    if not eng_file.exists():
        raise HTTPException(status_code=404)

    if len(req.confirmations) < 4:
        raise HTTPException(status_code=400, detail="All 4 confirmations required for sign-off")

    eng = json.loads(eng_file.read_text())
    eng["gates"][gate_id] = "signed_off"
    eng_file.write_text(json.dumps(eng, indent=2))

    await append_event(
        engagement_dir, engagement_id, EventType.REVIEW_EVENT,
        actor={"type": "HUMAN", "id": req.signer_email},
        payload_summary={"gate_id": gate_id, "confirmations": req.confirmations},
    )
    return {"gate_id": gate_id, "status": "signed_off"}
