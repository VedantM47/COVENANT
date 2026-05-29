"""Stage 5 schemas — Evidence pack."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SignOff(BaseModel):
    role: str
    name: str
    email: str
    signed_at: str


class EvidencePack(BaseModel):
    filename: str = ""
    size_bytes: int = 0
    content_sha256: str = ""
    rfc3161_timestamp: str | None = None
    tsa: str | None = None
    tsa_response_token_b64: str | None = None


class Stage5Output(BaseModel):
    stage: str = "stage_5_evidence"
    engagement_id: str
    status: str = "sealed"
    chain_integrity: dict = Field(default_factory=dict)
    sign_off_chain: list[SignOff] = Field(default_factory=list)
    evidence_pack: EvidencePack = Field(default_factory=EvidencePack)
