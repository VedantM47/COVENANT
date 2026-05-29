"""API request/response models."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class BorrowerInfo(BaseModel):
    name: str
    cik: str | None = None
    rssd_id: str | None = None
    fdic_cert: str | None = None


class LenderInfo(BaseModel):
    name: str


class AuditTeamMember(BaseModel):
    role: str
    email: str
    name: str


class CreateEngagementRequest(BaseModel):
    engagement_code: str
    borrower: BorrowerInfo
    lender: LenderInfo
    loan_id: str = ""
    test_date: date
    audit_team: list[AuditTeamMember] = Field(default_factory=list)
    external_egress_enabled: bool = True
    llm_provider_override: str | None = None


class EngagementResponse(BaseModel):
    engagement_id: str
    engagement_code: str
    borrower: BorrowerInfo
    lender: LenderInfo
    loan_id: str = ""
    test_date: str
    status: str = "created"
    pipeline_stage: str = "not_started"
    audit_team: list[AuditTeamMember] = Field(default_factory=list)
    external_egress_enabled: bool = True
    llm_provider: str = "mock"
    created_at: str = ""
    gates: dict[str, Any] = Field(default_factory=dict)


class GateApproveRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    approver_email: str
    notes: str = ""


class GateEditRequest(BaseModel):
    item_id: str
    field_path: str
    new_value: Any
    reason: str


class GateRejectRequest(BaseModel):
    item_id: str
    reason: str
    escalate_to: str | None = None


class GateSignOffRequest(BaseModel):
    signer_email: str
    confirmations: list[str] = Field(default_factory=list)


class ScaleConfirmRequest(BaseModel):
    scale: str  # actuals | thousands | millions


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    filter: dict = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    stage: str = ""
    engagement_id: str = ""
    trace_id: str = ""
    details: dict = Field(default_factory=dict)
    remediation: str = ""


class ErrorResponse(BaseModel):
    error: ErrorDetail
