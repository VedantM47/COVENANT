"""Stage 3 schemas — Calculation engine."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    step: int
    label: str
    value_exact: str  # string representation of Rational
    value_display: str = ""
    source_field: str = ""
    source_chunk_ids: list[str] = Field(default_factory=list)
    components: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class CircularCapTrace(BaseModel):
    step: int
    label: str
    method: str = "sympy.solve"
    equation: str = ""
    raw_value: str = ""
    cap_pct: str = ""
    solution_exact: str = ""
    applied_value_exact: str = ""
    applied_value_display: str = ""


class CovenantRatioResult(BaseModel):
    covenant_id: str
    covenant_name: str
    ratio_exact_rational: str  # e.g. "1815000000/1361111111"
    ratio_float: float
    ratio_display: str
    threshold_value: float
    threshold_operator: str
    threshold_period_start: str = ""
    threshold_period_end: str = ""
    threshold_source_chunk_id: str = ""
    is_compliant: bool
    z3_cross_check: str = ""
    trace: list[dict] = Field(default_factory=list)


class Stage3Output(BaseModel):
    stage: str = "stage_3_calculation"
    engagement_id: str
    status: str = "completed"
    test_date: str
    engine: dict = Field(default_factory=lambda: {"name": "SymPy", "version": "1.13.3"})
    input_snapshot_hash: str = ""
    results: list[CovenantRatioResult] = Field(default_factory=list)
