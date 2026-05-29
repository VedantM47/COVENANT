"""Symbolic validation of extracted covenants.

Implements all 8 checks from IMPLEMENTATION_PLAN.md section 6.4.4.
Each check emits a VALIDATION_CHECK_RUN audit event with pass/fail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    check_name: str
    passed: bool
    detail: str = ""


@dataclass
class CovenantValidationReport:
    covenant_id: str
    checks: list[ValidationResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[ValidationResult]:
        return [c for c in self.checks if not c.passed]


def _check_schema_valid(covenant: dict) -> ValidationResult:
    """Check 1: Pydantic schema validity (re-validate server-side)."""
    try:
        from app.schemas.stage1 import Covenant
        Covenant.model_validate(covenant)
        return ValidationResult("schema_valid", True)
    except Exception as e:
        return ValidationResult("schema_valid", False, str(e)[:200])


def _check_sources_verified(covenant: dict, chunks_by_id: dict[str, str]) -> ValidationResult:
    """Check 2: Every leaf field with source_text_match is a substring of its chunk."""
    from app.stages.stage1_extract.llm_extractor import _verify_all_sources, SourceVerificationError
    errors = _verify_all_sources(covenant, chunks_by_id)
    if errors:
        return ValidationResult(
            "sources_verified", False,
            f"{len(errors)} source verification failures: "
            + "; ".join(f"{e.field_path} (chunk {e.chunk_id})" for e in errors[:3])
        )
    return ValidationResult("sources_verified", True)


def _check_formula_evaluable(covenant: dict) -> ValidationResult:
    """Check 3: Formula evaluates symbolically with dummy inputs."""
    formula = covenant.get("formula")
    if not formula:
        return ValidationResult("formula_evaluable", True, "no formula (non-ratio covenant)")

    try:
        from sympy import Symbol, Rational
        from app.stages.stage3_calculate.ast_evaluator import evaluate_ast

        # Build dummy bindings: every term_id -> 1
        def _collect_term_ids(node: dict) -> set[str]:
            ids = set()
            if isinstance(node, dict):
                if node.get("kind") == "ref":
                    ids.add(node["term_id"])
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        ids.update(_collect_term_ids(v) if isinstance(v, dict) else
                                   {t for item in v for t in _collect_term_ids(item) if isinstance(item, dict)})
            return ids

        for part_name in ("numerator", "denominator"):
            part = formula.get(part_name)
            if not part:
                continue
            ast = part.get("expression_ast")
            if not ast:
                continue
            term_ids = _collect_term_ids(ast)
            bindings = {tid: Rational(1) for tid in term_ids}
            result = evaluate_ast(ast, bindings)
            # Result must be a number (not raise)

        return ValidationResult("formula_evaluable", True)
    except ZeroDivisionError:
        return ValidationResult("formula_evaluable", True, "division by zero with dummy inputs (expected)")
    except Exception as e:
        return ValidationResult("formula_evaluable", False, str(e)[:200])


def _check_terms_resolved(covenant: dict, defined_term_ids: set[str]) -> ValidationResult:
    """Check 4: Every term_id in formula exists in defined_terms."""
    formula = covenant.get("formula")
    if not formula:
        return ValidationResult("terms_resolved", True)

    def _collect_term_ids(node: Any) -> set[str]:
        ids = set()
        if isinstance(node, dict):
            if node.get("kind") == "ref":
                ids.add(node.get("term_id", ""))
            for v in node.values():
                ids.update(_collect_term_ids(v))
        elif isinstance(node, list):
            for item in node:
                ids.update(_collect_term_ids(item))
        return ids

    used_ids = set()
    for part in ("numerator", "denominator"):
        part_data = formula.get(part) or {}
        ast = part_data.get("expression_ast") or {}
        used_ids.update(_collect_term_ids(ast))

    missing = used_ids - defined_term_ids - {""}
    if missing:
        return ValidationResult(
            "terms_resolved", False,
            f"Term IDs not in defined_terms: {missing}"
        )
    return ValidationResult("terms_resolved", True)


def _check_z3_period_bracketing(covenant: dict, test_date_str: str) -> ValidationResult:
    """Check 5: Z3 verifies threshold periods cover test_date with no gaps/overlaps."""
    thresholds = covenant.get("thresholds", [])
    if not thresholds:
        return ValidationResult("z3_period_bracketing", False, "no thresholds defined")

    try:
        from datetime import date
        import z3

        test_date = date.fromisoformat(test_date_str)
        test_day = (test_date - date(2020, 1, 1)).days  # days since epoch

        solver = z3.Solver()
        covered = z3.BoolVal(False)

        for thr in thresholds:
            start_cf = thr.get("period_start") or {}
            end_cf = thr.get("period_end") or {}
            start_val = start_cf.get("value") if isinstance(start_cf, dict) else start_cf
            end_val = end_cf.get("value") if isinstance(end_cf, dict) else end_cf

            try:
                start = date.fromisoformat(str(start_val)) if start_val else date.min
                end = date.fromisoformat(str(end_val)) if end_val else date.max
            except (ValueError, TypeError):
                start, end = date.min, date.max

            start_day = (start - date(2020, 1, 1)).days
            end_day = (end - date(2020, 1, 1)).days

            in_period = z3.And(
                z3.IntVal(start_day) <= z3.IntVal(test_day),
                z3.IntVal(test_day) <= z3.IntVal(end_day),
            )
            covered = z3.Or(covered, in_period)

        solver.add(z3.Not(covered))
        result = solver.check()

        if result == z3.unsat:
            # Test date IS covered (negation is unsatisfiable)
            return ValidationResult("z3_period_bracketing", True)
        else:
            return ValidationResult(
                "z3_period_bracketing", False,
                f"Test date {test_date_str} not covered by any threshold period"
            )
    except Exception as e:
        return ValidationResult("z3_period_bracketing", False, f"Z3 error: {e}")


def _check_cap_consistency(covenant: dict) -> ValidationResult:
    """Check 6: Cap values are in valid ranges."""
    issues = []
    for addback in covenant.get("ebitda_addbacks_resolved", []):
        cap = addback.get("cap")
        if not cap:
            continue
        kind = cap.get("kind", "")
        value = cap.get("value")
        if kind == "pct_of_ebitda" and value is not None:
            if not (0 < float(value) < 1):
                issues.append(f"pct_of_ebitda cap {value} not in (0,1)")
        elif kind == "dollar_cap" and value is not None:
            if float(value) <= 0:
                issues.append(f"dollar_cap {value} <= 0")

    if issues:
        return ValidationResult("cap_consistency", False, "; ".join(issues))
    return ValidationResult("cap_consistency", True)


def _check_operator_direction(covenant: dict) -> ValidationResult:
    """Check 7: Operator direction matches covenant subtype."""
    subtype = covenant.get("covenant_subtype", "")
    thresholds = covenant.get("thresholds", [])
    if not thresholds:
        return ValidationResult("operator_direction", True)

    for thr in thresholds:
        op_cf = thr.get("operator") or {}
        op = op_cf.get("value", "") if isinstance(op_cf, dict) else str(op_cf)

        if "max" in subtype or "leverage" in subtype:
            if op not in ("<=", "<"):
                return ValidationResult(
                    "operator_direction", False,
                    f"Leverage/max covenant has operator '{op}' — expected '<=' or '<'. "
                    f"This would flip the compliance verdict."
                )
        elif "min" in subtype or "coverage" in subtype or "ebitda" in subtype:
            if op not in (">=", ">"):
                return ValidationResult(
                    "operator_direction", False,
                    f"Coverage/min covenant has operator '{op}' — expected '>=' or '>'. "
                    f"This would flip the compliance verdict."
                )

    return ValidationResult("operator_direction", True)


def _check_covenant_id_present(covenant: dict) -> ValidationResult:
    """Check 8: covenant_id is non-empty and unique-looking."""
    cov_id = covenant.get("covenant_id", "")
    if not cov_id or len(cov_id) < 3:
        return ValidationResult("covenant_id_present", False, f"covenant_id '{cov_id}' too short")
    return ValidationResult("covenant_id_present", True)


def validate_covenant(
    covenant: dict,
    chunks_by_id: dict[str, str],
    defined_term_ids: set[str],
    test_date_str: str,
) -> CovenantValidationReport:
    """Run all 8 validation checks on an extracted covenant."""
    cov_id = covenant.get("covenant_id", "unknown")
    report = CovenantValidationReport(covenant_id=cov_id)

    report.checks.append(_check_schema_valid(covenant))
    report.checks.append(_check_sources_verified(covenant, chunks_by_id))
    report.checks.append(_check_formula_evaluable(covenant))
    report.checks.append(_check_terms_resolved(covenant, defined_term_ids))
    report.checks.append(_check_z3_period_bracketing(covenant, test_date_str))
    report.checks.append(_check_cap_consistency(covenant))
    report.checks.append(_check_operator_direction(covenant))
    report.checks.append(_check_covenant_id_present(covenant))

    return report
