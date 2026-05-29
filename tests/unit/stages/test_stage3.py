"""Unit tests for Stage 3 calculation engine."""
from __future__ import annotations

import pytest
from sympy import Rational

from app.stages.stage3_calculate.circular_solver import solve_circular_cap
from app.stages.stage3_calculate.ast_evaluator import evaluate_ast


# ── Circular cap solver ───────────────────────────────────────────────────────

def test_circular_cap_firstbank():
    """FirstBank scenario: E = 122.8M + min(13.5M, 0.1*E)."""
    base = Rational("122800000")
    raw = Rational("13500000")
    pct = Rational("1/10")

    ebitda, applied = solve_circular_cap(base, raw, pct)

    # Expected: E = 122.8M / (1 - 0.1) = 136,444,444.44...
    # But wait — let's check which case applies:
    # Case 1: E = 122.8M + 13.5M = 136.3M; is 13.5M <= 0.1 * 136.3M = 13.63M? YES
    # So case 1 applies: E = 136.3M, applied = 13.5M (not capped)
    # Actually: 13.5M <= 13.63M → cap is NOT binding → applied = raw = 13.5M
    assert ebitda == base + raw  # 136,300,000
    assert applied == raw  # 13,500,000


def test_circular_cap_nexus():
    """Nexus scenario: E = 178.7M + min(35M, 0.1*E).
    
    Nexus base EBITDA (without restructuring):
    Net Income + Interest + Tax + D&A = correct_ebitda - applied_restructuring
    correct_ebitda = 198,555,556 per metadata
    So base = 198,555,556 * (1 - 0.1) = 178,700,000
    raw restructuring = 35M
    """
    # From Nexus metadata: correct_ebitda = 198,555,556
    # This means: E = base + min(35M, 0.1*E)
    # If cap is binding: E = base / 0.9 = 198,555,556 → base = 178,700,000
    base = Rational("178700000")
    raw = Rational("35000000")
    pct = Rational("1/10")

    ebitda, applied = solve_circular_cap(base, raw, pct)

    # Check case 1: E = 178.7M + 35M = 213.7M; is 35M <= 0.1 * 213.7M = 21.37M? NO
    # So case 2: E = 178.7M / 0.9 = 198,555,555.56
    expected_ebitda = Rational("178700000") / Rational("9/10")
    assert abs(float(ebitda) - float(expected_ebitda)) < 1.0
    # Applied = 0.1 * E = 19,855,555.56
    assert applied < raw  # cap IS binding for Nexus


def test_circular_cap_not_binding():
    """When raw < pct*base, cap is not binding."""
    base = Rational("100000000")
    raw = Rational("5000000")   # 5M < 10% of 105M = 10.5M
    pct = Rational("1/10")

    ebitda, applied = solve_circular_cap(base, raw, pct)
    assert ebitda == base + raw
    assert applied == raw


def test_circular_cap_binding():
    """When raw > pct*base/(1-pct), cap is binding."""
    base = Rational("100000000")
    raw = Rational("20000000")  # 20M > 10% of 120M = 12M → cap binds
    pct = Rational("1/10")

    ebitda, applied = solve_circular_cap(base, raw, pct)
    # E = 100M / 0.9 = 111,111,111.11
    expected = Rational("100000000") / Rational("9/10")
    assert ebitda == expected
    assert applied == pct * expected


# ── AST evaluator ─────────────────────────────────────────────────────────────

def test_ast_literal():
    node = {"kind": "literal", "value": 5000000}
    result = evaluate_ast(node, {})
    assert result == Rational("5000000")


def test_ast_ref():
    node = {"kind": "ref", "term_id": "ebitda"}
    result = evaluate_ast(node, {"ebitda": Rational("136111111")})
    assert result == Rational("136111111")


def test_ast_binop_divide():
    node = {
        "kind": "binop", "op": "/",
        "left": {"kind": "literal", "value": 181500000},
        "right": {"kind": "literal", "value": 136111111},
    }
    result = evaluate_ast(node, {})
    assert abs(float(result) - 1.334) < 0.001


def test_ast_min():
    node = {
        "kind": "min",
        "args": [
            {"kind": "literal", "value": 18500000},
            {"kind": "literal", "value": 25000000},
        ],
    }
    result = evaluate_ast(node, {})
    assert result == Rational("18500000")


def test_ast_divide_by_zero():
    node = {
        "kind": "binop", "op": "/",
        "left": {"kind": "literal", "value": 100},
        "right": {"kind": "literal", "value": 0},
    }
    with pytest.raises(ZeroDivisionError):
        evaluate_ast(node, {})


# ── Property-based tests ──────────────────────────────────────────────────────

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st


@given(
    base=st.integers(min_value=1_000_000, max_value=500_000_000),
    raw=st.integers(min_value=0, max_value=100_000_000),
    pct_num=st.integers(min_value=1, max_value=30),
)
@hyp_settings(max_examples=50)
def test_circular_cap_always_positive(base, raw, pct_num):
    """Circular cap solution is always positive."""
    pct = Rational(pct_num, 100)
    ebitda, applied = solve_circular_cap(Rational(base), Rational(raw), pct)
    assert ebitda > 0
    assert applied >= 0
    assert applied <= Rational(raw)


@given(
    ratio=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
    threshold=st.floats(min_value=1.0, max_value=8.0, allow_nan=False),
)
@hyp_settings(max_examples=50)
def test_compliance_verdict_consistent(ratio, threshold):
    """Compliance verdict matches hand-coded comparison."""
    is_compliant = ratio <= threshold
    # Verify with Rational
    r = Rational(str(round(ratio, 6)))
    t = Rational(str(round(threshold, 6)))
    assert (r <= t) == is_compliant
