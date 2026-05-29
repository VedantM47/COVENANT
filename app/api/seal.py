"""Seal endpoint."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.settings import get_settings
from app.stages.stage5_evidence import run_stage5
from app.schemas.stage3 import Stage3Output
from app.schemas.stage4 import Stage4Output

router = APIRouter(tags=["seal"])


@router.post("/engagements/{engagement_id}/seal")
async def seal_engagement(engagement_id: str):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    if not engagement_dir.exists():
        raise HTTPException(status_code=404)

    eng = json.loads((engagement_dir / "engagement.json").read_text())

    # Load stage outputs
    ratios_path = engagement_dir / "state" / "ratios.json"
    recon_path = engagement_dir / "state" / "reconciliation.json"

    stage3 = Stage3Output.model_validate_json(ratios_path.read_text()) if ratios_path.exists() else None
    stage4 = Stage4Output.model_validate_json(recon_path.read_text()) if recon_path.exists() else None

    result = await run_stage5(engagement_dir, engagement_id, eng, stage3, stage4)
    return result.model_dump()


@router.get("/engagements/{engagement_id}/evidence-pack")
async def get_evidence_pack(engagement_id: str):
    settings = get_settings()
    exports_dir = settings.engagement_dir(engagement_id) / "exports"
    for f in exports_dir.glob("evidence_pack_*.pdf"):
        return FileResponse(str(f), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Evidence pack not found")
