"""Stage 2 schemas — Financial normalization."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AccountMapping(BaseModel):
    row_id: str
    source_label: str
    source_account_code: str = ""
    mapped_to: str
    confidence: float
    method: str = "embedding_match"
    alternatives: list[dict] = Field(default_factory=list)
    exclusion_check_passed: bool = True
    requires_cap_check: bool = False
    needs_review: bool = False
    review_reason: str | None = None


class LTMValue(BaseModel):
    value: float
    method: str = "sum_of_4_quarters"
    per_quarter: list[float] = Field(default_factory=list)
    components: dict[str, float] = Field(default_factory=dict)


class LTMReconstruction(BaseModel):
    test_date: str
    ltm_period_start: str
    ltm_period_end: str
    quarters_used: list[str] = Field(default_factory=list)
    values: dict[str, LTMValue] = Field(default_factory=dict)
    missing_data_warnings: list[str] = Field(default_factory=list)


class Stage2Output(BaseModel):
    stage: str = "stage_2_financial_normalization"
    engagement_id: str
    status: str = "awaiting_human_gate_2"
    fields_required: list[str] = Field(default_factory=list)
    mappings: list[AccountMapping] = Field(default_factory=list)
    unmapped_rows: list[dict] = Field(default_factory=list)
    ltm_reconstruction: LTMReconstruction | None = None
