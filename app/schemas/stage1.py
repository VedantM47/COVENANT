"""Stage 1 schemas — Covenant extraction."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ConfidenceField


# ── Formula AST nodes (closed grammar from brief section 6) ──────────────────

class LiteralNode(BaseModel):
    kind: Literal["literal"] = "literal"
    value: Any
    unit: str | None = None


class RefNode(BaseModel):
    kind: Literal["ref"] = "ref"
    term_id: str


class BinopNode(BaseModel):
    kind: Literal["binop"] = "binop"
    op: Literal["+", "-", "*", "/"]
    left: "ASTNode"
    right: "ASTNode"


class MinNode(BaseModel):
    kind: Literal["min"] = "min"
    args: list["ASTNode"]


class MaxNode(BaseModel):
    kind: Literal["max"] = "max"
    args: list["ASTNode"]


class AbsNode(BaseModel):
    kind: Literal["abs"] = "abs"
    arg: "ASTNode"


class PowNode(BaseModel):
    kind: Literal["pow"] = "pow"
    base: "ASTNode"
    exp: "ASTNode"


class IfNode(BaseModel):
    kind: Literal["if"] = "if"
    cond: dict  # condition node
    then: "ASTNode"
    else_: "ASTNode" = Field(alias="else")

    model_config = {"populate_by_name": True}


class SumPeriodNode(BaseModel):
    kind: Literal["sum_period"] = "sum_period"
    term_id: str
    period: Literal["LTM", "QTD", "YTD"]


class CapPctOfNode(BaseModel):
    kind: Literal["cap_pct_of"] = "cap_pct_of"
    value: "ASTNode"
    target: RefNode
    pct: float
    is_circular: bool = False


class CapDollarNode(BaseModel):
    kind: Literal["cap_dollar"] = "cap_dollar"
    value: "ASTNode"
    max_dollar: float


class CapGreaterOfNode(BaseModel):
    kind: Literal["cap_greater_of"] = "cap_greater_of"
    value: "ASTNode"
    options: list["ASTNode"]


class CapLesserOfNode(BaseModel):
    kind: Literal["cap_lesser_of"] = "cap_lesser_of"
    value: "ASTNode"
    options: list["ASTNode"]


ASTNode = (
    LiteralNode | RefNode | BinopNode | MinNode | MaxNode | AbsNode |
    PowNode | IfNode | SumPeriodNode | CapPctOfNode | CapDollarNode |
    CapGreaterOfNode | CapLesserOfNode
)

# Update forward refs
for _cls in [BinopNode, MinNode, MaxNode, AbsNode, PowNode, IfNode,
             CapPctOfNode, CapDollarNode, CapGreaterOfNode, CapLesserOfNode]:
    _cls.model_rebuild()


# ── Defined term ──────────────────────────────────────────────────────────────

class TermReference(BaseModel):
    to_term_id: str
    edge_type: str = "depends_on"
    note: str | None = None


class DefinedTerm(BaseModel):
    term_id: str
    term_canonical: str
    term_aliases: list[str] = Field(default_factory=list)
    definition_text: str = ""
    definition_kind: str = ""
    source_chunk_id: str = ""
    page_number: int = 0
    section_path: list[str] = Field(default_factory=list)
    references: list[TermReference] = Field(default_factory=list)
    temporal_qualifier: str | None = None
    extraction_confidence: float = 1.0
    needs_review: bool = False
    amended_by: str | None = None


# ── Threshold ─────────────────────────────────────────────────────────────────

class Threshold(BaseModel):
    threshold_id: str
    period_start: ConfidenceField | None = None
    period_end: ConfidenceField | None = None
    operator: ConfidenceField  # value is "<=", ">=", etc.
    value: ConfidenceField


# ── EBITDA addback ────────────────────────────────────────────────────────────

class AddbackCap(BaseModel):
    kind: str  # pct_of_ebitda | dollar_cap | greater_of | lesser_of
    value: float | None = None
    is_circular: bool = False
    source_chunk_id: str = ""
    source_text_match: str = ""


class EBITDAAddback(BaseModel):
    field: str
    term_id: str
    cap: AddbackCap | None = None


# ── Covenant ──────────────────────────────────────────────────────────────────

class FormulaExpression(BaseModel):
    expression_ast: dict  # raw AST dict (validated separately)
    expression_human: str = ""
    source_chunk_id: str = ""
    source_text_match: str = ""


class CovenantFormula(BaseModel):
    kind: str = "ratio"
    numerator: FormulaExpression | None = None
    denominator: FormulaExpression | None = None


class AmendmentChange(BaseModel):
    change_id: str
    kind: str
    field_path: str
    before: Any
    after: Any
    source_chunk_id: str = ""
    source_text_match: str = ""


class AmendmentOverlay(BaseModel):
    applied: bool = False
    amendment_history: list[dict] = Field(default_factory=list)


class ExtractionMeta(BaseModel):
    model: str = ""
    provider: str = ""
    extracted_at: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    self_consistency_runs: int = 0
    self_consistency_score: float = 1.0
    fields_disagreeing: list[str] = Field(default_factory=list)
    overall_confidence: float = 1.0


class ValidationResult(BaseModel):
    schema_valid: bool = True
    all_sources_verified: bool = True
    ebitda_terms_resolved: bool = True
    formula_evaluable_with_dummy_inputs: bool = True
    z3_period_bracketing_valid: bool = True
    issues: list[str] = Field(default_factory=list)


class Covenant(BaseModel):
    covenant_id: str
    covenant_name: str
    covenant_type: str = "financial_maintenance"
    covenant_subtype: str = ""
    section_reference: str = ""
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_text_excerpt: str = ""
    testing_frequency: ConfidenceField | None = None
    testing_basis: ConfidenceField | None = None
    thresholds: list[Threshold] = Field(default_factory=list)
    formula: CovenantFormula | None = None
    ebitda_definition_reference: str | None = None
    ebitda_addbacks_resolved: list[EBITDAAddback] = Field(default_factory=list)
    extraction: ExtractionMeta = Field(default_factory=ExtractionMeta)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    amendment_overlay: AmendmentOverlay = Field(default_factory=AmendmentOverlay)
    needs_review: bool = False
    review_reason: str | None = None


class Stage1Output(BaseModel):
    stage: str = "stage_1_covenant_extraction"
    engagement_id: str
    status: str = "awaiting_human_gate_1"
    defined_terms_count: int = 0
    covenants_extracted: int = 0
    covenants_needing_review: int = 0
    covenants: list[Covenant] = Field(default_factory=list)
    defined_terms: list[DefinedTerm] = Field(default_factory=list)
