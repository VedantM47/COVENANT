"""Stage 4 schemas — Reconciliation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComponentDelta(BaseModel):
    borrower: float
    platform: float
    delta: float
    explanation: str = ""


class RootCauseDiagnosis(BaseModel):
    diagnosis_kind: str = "component_drilldown"
    identified_errors: list[dict] = Field(default_factory=list)
    components: dict[str, ComponentDelta] = Field(default_factory=dict)
    supporting_rag_queries: list[dict] = Field(default_factory=list)


class PairwiseVariance(BaseModel):
    between: list[str]
    variance: float
    exceeds_tolerance: bool


class MaterialityResult(BaseModel):
    quantitative: str = "MATERIAL"
    qualitative: str = "QUALITATIVE_MATERIAL"
    loan_exposure_usd: float = 0
    variance_x_exposure_band: str = "high"


class CovenantReconciliation(BaseModel):
    covenant_id: str
    covenant_name: str
    borrower_reported_value: float | None = None
    platform_computed_value: float
    regulatory_reference_value: float | None = None
    pairwise_variances: list[PairwiseVariance] = Field(default_factory=list)
    verdict: str = "CLEAN"  # CLEAN | DISCLOSURE_MISMATCH | BREACH | BREACH_WITH_DISCLOSURE_MISMATCH
    root_cause: RootCauseDiagnosis | None = None
    materiality: MaterialityResult | None = None
    exception_id: str | None = None


class Exception_(BaseModel):
    exception_id: str
    covenant_id: str
    type: str  # HARD_BREACH | DISCLOSURE_MISMATCH | REGULATORY_DATA_MISMATCH
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    kind: str = ""  # root cause kind for test assertions
    description: str = ""
    conclusion: str | None = None
    investigation_notes: str = ""


class Stage4Output(BaseModel):
    stage: str = "stage_4_reconciliation"
    engagement_id: str
    status: str = "awaiting_human_gate_3"
    covenant_reconciliations: list[CovenantReconciliation] = Field(default_factory=list)
    exceptions: list[Exception_] = Field(default_factory=list)
