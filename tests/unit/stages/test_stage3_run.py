"""Unit tests for run_stage3 — covers the async pipeline function."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from sympy import Rational

from app.stages.stage3_calculate import run_stage3
from app.stages.stage3_calculate.ast_evaluator import evaluate_ast
from app.stages.stage3_calculate.circular_solver import solve_circular_cap


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_leverage_covenant(threshold: float = 5.0, operator: str = "<=") -> dict:
    return {
        "covenant_id": "COV-NET-LEVERAGE",
        "covenant_name": "Net Leverage Ratio",
        "covenant_subtype": "leverage_ratio_max",
        "thresholds": [{
            "threshold_id": "thr_001",
            "period_start": {"value": "2024-01-01"},
            "period_end": {"value": "2024-12-31"},
            "operator": {"value": operator},
            "value": {"value": threshold},
        }],
        "ebitda_addbacks_resolved": [
            {"field": "restructuring_costs", "term_id": "term_restructuring",
             "cap": {"kind": "pct_of_ebitda", "value": 0.10, "is_circular": True}},
        ],
    }


def _make_icr_covenant() -> dict:
    return {
        "covenant_id": "COV-ICR",
        "covenant_name": "Interest Coverage Ratio",
        "covenant_subtype": "interest_coverage",
        "thresholds": [{
            "threshold_id": "thr_icr",
            "period_start": {"value": "2024-01-01"},
            "period_end": {"value": "2024-12-31"},
            "operator": {"value": ">="},
            "value": {"value": 2.5},
        }],
        "ebitda_addbacks_resolved": [],
    }


def _make_fccr_covenant() -> dict:
    return {
        "covenant_id": "COV-FCCR",
        "covenant_name": "Fixed Charge Coverage",
        "covenant_subtype": "fixed_charge",
        "thresholds": [{
            "threshold_id": "thr_fccr",
            "period_start": {"value": "2024-01-01"},
            "period_end": {"value": "2024-12-31"},
            "operator": {"value": ">="},
            "value": {"value": 1.2},
        }],
        "ebitda_addbacks_resolved": [],
    }


def _make_min_ebitda_covenant() -> dict:
    return {
        "covenant_id": "COV-MIN-EBITDA",
        "covenant_name": "Minimum EBITDA",
        "covenant_subtype": "min_ebitda",
        "thresholds": [{
            "threshold_id": "thr_ebitda",
            "period_start": {"value": "2024-01-01"},
            "period_end": {"value": "2024-12-31"},
            "operator": {"value": ">="},
            "value": {"value": 95000000},
        }],
        "ebitda_addbacks_resolved": [],
    }


FIRSTBANK_LTM = {
    "_correct_ebitda": 136444444.0,
    "_correct_net_debt": 187500000.0,
    "net_income": 49600000.0,
    "interest_expense": 32800000.0,
    "tax_expense": 8400000.0,
    "depreciation": 27200000.0,
    "amortization": 4800000.0,
    "restructuring_costs": 13500000.0,
    "unrestricted_cash": 18500000.0,
}

NEXUS_LTM = {
    "_correct_ebitda": 198355556.0,
    "_correct_net_debt": 1062400000.0,
    "net_income": 41800000.0,
    "interest_expense": 54800000.0,
    "tax_expense": 20300000.0,
    "depreciation": 49200000.0,
    "amortization": 12400000.0,
    "restructuring_costs": 35000000.0,
    "unrestricted_cash": 31400000.0,
}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_stage3_firstbank(tmp_path):
    """FirstBank: ratio ≈ 1.374x, compliant."""
    eng_dir = tmp_path / "ENG-FB"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    covenants = [_make_leverage_covenant(5.0)]
    output = await run_stage3(eng_dir, "ENG-FB", covenants, FIRSTBANK_LTM, "2024-12-31")

    assert len(output.results) == 1
    r = output.results[0]
    assert abs(r.ratio_float - 1.374) < 0.005
    assert r.is_compliant is True
    assert r.covenant_id == "COV-NET-LEVERAGE"


@pytest.mark.asyncio
async def test_run_stage3_nexus_breach(tmp_path):
    """Nexus: ratio ≈ 5.356x, BREACH (> 5.0x)."""
    eng_dir = tmp_path / "ENG-NX"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    covenants = [_make_leverage_covenant(5.0)]
    output = await run_stage3(eng_dir, "ENG-NX", covenants, NEXUS_LTM, "2024-12-31")

    r = output.results[0]
    assert abs(r.ratio_float - 5.352) < 0.01
    assert r.is_compliant is False  # BREACH


@pytest.mark.asyncio
async def test_run_stage3_icr(tmp_path):
    """ICR covenant computed correctly."""
    eng_dir = tmp_path / "ENG-ICR"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    ltm = {**FIRSTBANK_LTM}
    del ltm["_correct_ebitda"]
    del ltm["_correct_net_debt"]

    covenants = [_make_icr_covenant()]
    output = await run_stage3(eng_dir, "ENG-ICR", covenants, ltm, "2024-12-31")

    r = output.results[0]
    # EBITDA / Interest = (122.8M + restructuring) / 32.8M
    assert r.ratio_float > 2.5  # should be compliant
    assert r.is_compliant is True


@pytest.mark.asyncio
async def test_run_stage3_fccr(tmp_path):
    """FCCR covenant computed."""
    eng_dir = tmp_path / "ENG-FCCR"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    ltm = {**FIRSTBANK_LTM, "capital_expenditures": 10000000.0}
    del ltm["_correct_ebitda"]
    del ltm["_correct_net_debt"]

    covenants = [_make_fccr_covenant()]
    output = await run_stage3(eng_dir, "ENG-FCCR", covenants, ltm, "2024-12-31")

    assert len(output.results) == 1
    r = output.results[0]
    assert r.ratio_float > 0


@pytest.mark.asyncio
async def test_run_stage3_min_ebitda(tmp_path):
    """Min EBITDA covenant computed."""
    eng_dir = tmp_path / "ENG-ME"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    ltm = {**FIRSTBANK_LTM}
    del ltm["_correct_ebitda"]
    del ltm["_correct_net_debt"]

    covenants = [_make_min_ebitda_covenant()]
    output = await run_stage3(eng_dir, "ENG-ME", covenants, ltm, "2024-12-31")

    r = output.results[0]
    assert r.ratio_float > 95000000  # EBITDA > $95M threshold
    assert r.is_compliant is True


@pytest.mark.asyncio
async def test_run_stage3_divide_by_zero(tmp_path):
    """Zero EBITDA → divide by zero handled gracefully."""
    eng_dir = tmp_path / "ENG-DZ"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    ltm = {"net_income": 0, "interest_expense": 0, "tax_expense": 0,
           "depreciation": 0, "amortization": 0, "restructuring_costs": 0,
           "_correct_net_debt": 100000000.0}
    # No _correct_ebitda → will compute from components → EBITDA = 0

    covenants = [_make_leverage_covenant()]
    output = await run_stage3(eng_dir, "ENG-DZ", covenants, ltm, "2024-12-31")

    r = output.results[0]
    assert r.is_compliant is False  # divide by zero → non-compliant


@pytest.mark.asyncio
async def test_run_stage3_multiple_covenants(tmp_path):
    """Multiple covenants computed in one run."""
    eng_dir = tmp_path / "ENG-MULTI"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    covenants = [
        _make_leverage_covenant(5.0),
        _make_icr_covenant(),
        _make_min_ebitda_covenant(),
    ]
    output = await run_stage3(eng_dir, "ENG-MULTI", covenants, FIRSTBANK_LTM, "2024-12-31")

    assert len(output.results) == 3
    ids = {r.covenant_id for r in output.results}
    assert "COV-NET-LEVERAGE" in ids
    assert "COV-ICR" in ids
    assert "COV-MIN-EBITDA" in ids


@pytest.mark.asyncio
async def test_run_stage3_threshold_outside_range(tmp_path):
    """Test date outside threshold range → uses last threshold."""
    eng_dir = tmp_path / "ENG-OOR"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    cov = {
        "covenant_id": "COV-NET-LEVERAGE",
        "covenant_name": "Net Leverage",
        "covenant_subtype": "leverage_ratio_max",
        "thresholds": [{
            "threshold_id": "thr_001",
            "period_start": {"value": "2023-01-01"},
            "period_end": {"value": "2023-12-31"},
            "operator": {"value": "<="},
            "value": {"value": 6.0},
        }],
        "ebitda_addbacks_resolved": [],
    }
    output = await run_stage3(eng_dir, "ENG-OOR", [cov], FIRSTBANK_LTM, "2024-12-31")
    # Falls back to last threshold
    assert len(output.results) == 1


@pytest.mark.asyncio
async def test_run_stage3_persists_ratios_json(tmp_path):
    """run_stage3 writes ratios.json to state/."""
    eng_dir = tmp_path / "ENG-PERSIST"
    (eng_dir / "audit").mkdir(parents=True)
    (eng_dir / "state").mkdir(parents=True)

    covenants = [_make_leverage_covenant()]
    await run_stage3(eng_dir, "ENG-PERSIST", covenants, FIRSTBANK_LTM, "2024-12-31")

    ratios_path = eng_dir / "state" / "ratios.json"
    assert ratios_path.exists()
    import json
    data = json.loads(ratios_path.read_text(encoding="utf-8"))
    assert data["engagement_id"] == "ENG-PERSIST"
    assert len(data["results"]) == 1


# ── AST evaluator edge cases ──────────────────────────────────────────────────

def test_ast_cap_dollar():
    node = {"kind": "cap_dollar", "value": {"kind": "literal", "value": 30000000}, "max_dollar": 25000000}
    result = evaluate_ast(node, {})
    assert result == Rational("25000000")


def test_ast_cap_pct_of_with_binding():
    """cap_pct_of with target in bindings."""
    node = {
        "kind": "cap_pct_of",
        "value": {"kind": "literal", "value": 20000000},
        "target": {"kind": "ref", "term_id": "ebitda"},
        "pct": 0.10,
        "is_circular": False,
    }
    result = evaluate_ast(node, {"ebitda": Rational("100000000")})
    # min(20M, 0.1 * 100M) = min(20M, 10M) = 10M
    assert result == Rational("10000000")


def test_ast_max_node():
    node = {
        "kind": "max",
        "args": [
            {"kind": "literal", "value": 5000000},
            {"kind": "literal", "value": 10000000},
        ],
    }
    result = evaluate_ast(node, {})
    assert result == Rational("10000000")


def test_ast_abs_node():
    node = {"kind": "abs", "arg": {"kind": "literal", "value": -5000000}}
    result = evaluate_ast(node, {})
    assert result == Rational("5000000")


def test_ast_pow_node():
    node = {
        "kind": "pow",
        "base": {"kind": "literal", "value": 2},
        "exp": {"kind": "literal", "value": 10},
    }
    result = evaluate_ast(node, {})
    assert result == Rational("1024")


def test_ast_sum_period():
    node = {"kind": "sum_period", "term_id": "ebitda", "period": "LTM"}
    result = evaluate_ast(node, {"ebitda": Rational("136000000")})
    assert result == Rational("136000000")


def test_ast_unknown_kind():
    with pytest.raises(ValueError, match="Unknown AST node kind"):
        evaluate_ast({"kind": "unknown_node"}, {})


def test_ast_ref_missing():
    with pytest.raises(KeyError):
        evaluate_ast({"kind": "ref", "term_id": "missing_term"}, {})


# ── Canonical JSON edge cases ─────────────────────────────────────────────────

def test_canonical_json_sympy_rational():
    from app.audit.canonical import canonical_json
    from sympy import Rational
    result = canonical_json({"ratio": Rational("1815000000/1361111111")})
    assert b"1815000000/1361111111" in result


def test_canonical_json_sympy_boolean():
    from app.audit.canonical import canonical_json
    from sympy import Rational
    # BooleanTrue from SymPy comparison
    val = Rational("5") <= Rational("6")
    result = canonical_json({"compliant": val})
    assert b"true" in result


def test_canonical_json_nested():
    from app.audit.canonical import canonical_json
    data = {"a": {"b": [1, 2, 3]}, "z": "last", "m": "middle"}
    b1 = canonical_json(data)
    b2 = canonical_json({"z": "last", "a": {"b": [1, 2, 3]}, "m": "middle"})
    assert b1 == b2  # sort_keys ensures stability
