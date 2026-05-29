"""Stage 0 schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentIngestRecord(BaseModel):
    document_id: str
    engagement_id: str
    filename: str
    document_type: str
    file_hash_sha256: str
    file_size_bytes: int
    page_count: int = 0
    row_count: int = 0
    is_scanned: bool = False
    ocr_engine_used: str | None = None
    chunks_produced: int = 0
    tables_found: int = 0
    scale_detected: str | None = None
    currency: str = "USD"
    totals_balanced: bool | None = None
    warnings_count: int = 0
    reliability_tier: str = "borrower_provided"
    status: str = "pending"


class Stage0Output(BaseModel):
    stage: str = "stage_0_ingest"
    engagement_id: str
    status: str = "completed"
    documents: list[DocumentIngestRecord] = Field(default_factory=list)
    faiss_chunk_count: int = 0
    human_action_required: bool = False
