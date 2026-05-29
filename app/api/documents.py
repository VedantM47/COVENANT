"""Document upload and retrieval endpoints."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.settings import get_settings
from app.stages.stage0_ingest import ingest_document

router = APIRouter(tags=["documents"])


@router.post("/engagements/{engagement_id}/documents")
async def upload_documents(
    engagement_id: str,
    files: list[UploadFile] = File(...),
    declared_type: str | None = None,
):
    settings = get_settings()
    engagement_dir = settings.engagement_dir(engagement_id)
    if not engagement_dir.exists():
        raise HTTPException(status_code=404, detail="Engagement not found")

    results = []
    for upload in files:
        tmp_path = settings.tmp_dir / upload.filename
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)

        rec = await ingest_document(engagement_dir, engagement_id, tmp_path, declared_type)
        tmp_path.unlink(missing_ok=True)
        results.append({"document_id": rec.document_id, "filename": rec.filename, "status": rec.status})

    return results


@router.get("/engagements/{engagement_id}/documents")
async def list_documents(engagement_id: str):
    settings = get_settings()
    raw_dir = settings.engagement_dir(engagement_id) / "raw"
    if not raw_dir.exists():
        return []
    return [{"filename": f.name} for f in raw_dir.iterdir()]


@router.get("/engagements/{engagement_id}/documents/{doc_id}/raw")
async def get_document_raw(engagement_id: str, doc_id: str):
    settings = get_settings()
    raw_dir = settings.engagement_dir(engagement_id) / "raw"
    for f in raw_dir.iterdir():
        if doc_id in f.name:
            return FileResponse(str(f))
    raise HTTPException(status_code=404, detail="Document not found")
