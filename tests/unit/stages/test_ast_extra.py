"""Additional AST evaluator tests for uncovered paths."""
from __future__ import annotations

import pytest
from sympy import Rational

from app.stages.stage3_calculate.ast_evaluator import evaluate_ast


def test_ast_cap_greater_of():
    """cap_greater_of: min(value, max(options))."""
    node = {
        "kind": "cap_greater_of",
        "value": {"kind": "literal", "value": 30000000},
        "options": [
            {"kind": "literal", "value": 5000000},
            {"kind": "literal", "value": 10000000},
        ],
    }
    # min(30M, max(5M, 10M)) = min(30M, 10M) = 10M
    result = evaluate_ast(node, {})
    assert result == Rational("10000000")


def test_ast_cap_lesser_of():
    """cap_lesser_of: min(value, min(options))."""
    node = {
        "kind": "cap_lesser_of",
        "value": {"kind": "literal", "value": 30000000},
        "options": [
            {"kind": "literal", "value": 25000000},
            {"kind": "literal", "value": 20000000},
        ],
    }
    # min(30M, min(25M, 20M)) = min(30M, 20M) = 20M
    result = evaluate_ast(node, {})
    assert result == Rational("20000000")


def test_ast_binop_add():
    node = {
        "kind": "binop", "op": "+",
        "left": {"kind": "literal", "value": 100},
        "right": {"kind": "literal", "value": 200},
    }
    assert evaluate_ast(node, {}) == Rational("300")


def test_ast_binop_subtract():
    node = {
        "kind": "binop", "op": "-",
        "left": {"kind": "literal", "value": 500},
        "right": {"kind": "literal", "value": 200},
    }
    assert evaluate_ast(node, {}) == Rational("300")


def test_ast_binop_multiply():
    node = {
        "kind": "binop", "op": "*",
        "left": {"kind": "literal", "value": 10},
        "right": {"kind": "literal", "value": 20},
    }
    assert evaluate_ast(node, {}) == Rational("200")


def test_ast_binop_unknown_op():
    node = {
        "kind": "binop", "op": "%",
        "left": {"kind": "literal", "value": 10},
        "right": {"kind": "literal", "value": 3},
    }
    with pytest.raises(ValueError, match="Unknown binop"):
        evaluate_ast(node, {})


def test_ast_cap_pct_of_no_target():
    """cap_pct_of without target in bindings returns raw value."""
    node = {
        "kind": "cap_pct_of",
        "value": {"kind": "literal", "value": 15000000},
        "target": {"kind": "ref", "term_id": "ebitda_not_in_bindings"},
        "pct": 0.10,
        "is_circular": True,
    }
    # target not in bindings → return raw value
    result = evaluate_ast(node, {})
    assert result == Rational("15000000")


def test_ast_nested_binop():
    """Nested binop: (a + b) / c."""
    node = {
        "kind": "binop", "op": "/",
        "left": {
            "kind": "binop", "op": "+",
            "left": {"kind": "literal", "value": 100},
            "right": {"kind": "literal", "value": 200},
        },
        "right": {"kind": "literal", "value": 3},
    }
    result = evaluate_ast(node, {})
    assert result == Rational("100")


def test_ast_min_three_args():
    """min with 3 args."""
    node = {
        "kind": "min",
        "args": [
            {"kind": "literal", "value": 30},
            {"kind": "literal", "value": 10},
            {"kind": "literal", "value": 20},
        ],
    }
    assert evaluate_ast(node, {}) == Rational("10")


def test_ast_max_three_args():
    """max with 3 args."""
    node = {
        "kind": "max",
        "args": [
            {"kind": "literal", "value": 30},
            {"kind": "literal", "value": 10},
            {"kind": "literal", "value": 20},
        ],
    }
    assert evaluate_ast(node, {}) == Rational("30")
