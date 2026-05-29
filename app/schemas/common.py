"""Common cross-cutting Pydantic models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page_w: float = 612.0
    page_h: float = 792.0


class ChunkRef(BaseModel):
    chunk_id: str
    document_id: str
    document_type: str = ""
    page_number: int = 0
    section_path: list[str] = Field(default_factory=list)
    section_label_display: str = ""
    bbox: BBox | None = None
    text_excerpt: str = ""
    reliability_tier: str = "borrower_provided"


class ConfidenceField(BaseModel):
    value: Any
    value_display: str = ""
    type: str = ""
    unit: str = ""
    source_chunk_id: str = ""
    source_text_match: str = ""
    extraction_method: str = "llm"
    extraction_model: str = ""
    confidence: float = 1.0
    confidence_band: Literal["high", "medium", "low"] = "high"
    self_consistency_agreement: float = 1.0
    needs_review: bool = False
    review_reason: str | None = None


class AuditEventActor(BaseModel):
    type: Literal["SYSTEM", "HUMAN"] = "SYSTEM"
    id: str = ""
    version: str = "1.0.0"
    model_used: str | None = None


class AuditEvent(BaseModel):
    event_id: str
    engagement_id: str
    event_type: str
    event_category: str = ""
    event_timestamp: datetime
    actor: AuditEventActor
    input_references: list[str] = Field(default_factory=list)
    output_references: list[str] = Field(default_factory=list)
    payload_summary: dict = Field(default_factory=dict)
    previous_hash: str
    event_hash: str


class HumanGate(BaseModel):
    gate_id: str
    gate_name: str
    stage_id: str
    status: Literal["pending", "in_review", "approved", "rejected", "needs_escalation"] = "pending"
    required_role: str = "associate_or_above"
    current_assignee: str | None = None
    items_to_review: int = 0
    items_flagged: int = 0
    blocked_until_resolved: bool = True
    deadline_iso: str | None = None
    history: list[dict] = Field(default_factory=list)
