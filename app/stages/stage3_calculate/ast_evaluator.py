"""AST evaluator — pure SymPy, no float, no LLM.

Evaluates the closed formula AST grammar from brief section 6.
All inputs are sympy.Rational. Returns exact Rational.
"""
from __future__ import annotations

from typing import Any

from sympy import Rational, Symbol, Min, Max, Abs, solve, S


def _r(v: Any) -> Rational:
    """Convert any numeric to exact Rational."""
    if isinstance(v, Rational):
        return v
    # Convert via string to avoid float imprecision
    return Rational(str(v))


def evaluate_ast(node: dict, bindings: dict[str, Rational]) -> Rational:
    """Recursively evaluate an AST node with the given term bindings.

    bindings: {term_id -> Rational value}
    """
    kind = node.get("kind") or node.get("op")  # support both field names

    if kind == "literal":
        return _r(node["value"])

    elif kind == "ref":
        term_id = node["term_id"]
        if term_id not in bindings:
            raise KeyError(f"Term '{term_id}' not in bindings")
        return bindings[term_id]

    elif kind == "binop":
        left = evaluate_ast(node["left"], bindings)
        right = evaluate_ast(node["right"], bindings)
        op = node["op"]
        if op == "+":
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            if right == 0:
                raise ZeroDivisionError("Division by zero in formula AST")
            return left / right
        else:
            raise ValueError(f"Unknown binop: {op}")

    elif kind == "min":
        args = [evaluate_ast(a, bindings) for a in node["args"]]
        result = args[0]
        for a in args[1:]:
            result = Min(result, a)
        return result

    elif kind == "max":
        args = [evaluate_ast(a, bindings) for a in node["args"]]
        result = args[0]
        for a in args[1:]:
            result = Max(result, a)
        return result

    elif kind == "abs":
        return Abs(evaluate_ast(node["arg"], bindings))

    elif kind == "pow":
        base = evaluate_ast(node["base"], bindings)
        exp = evaluate_ast(node["exp"], bindings)
        return base ** exp

    elif kind == "cap_dollar":
        val = evaluate_ast(node["value"], bindings)
        cap = _r(node["max_dollar"])
        return Min(val, cap)

    elif kind == "cap_pct_of":
        # If circular, caller must have already resolved and put result in bindings
        val = evaluate_ast(node["value"], bindings)
        target_id = node["target"]["term_id"] if isinstance(node["target"], dict) else node["target"]
        pct = _r(node["pct"])
        if target_id in bindings:
            cap = pct * bindings[target_id]
            return Min(val, cap)
        else:
            # Non-circular: target not yet resolved — return raw value
            return val

    elif kind == "cap_greater_of":
        val = evaluate_ast(node["value"], bindings)
        options = [evaluate_ast(o, bindings) for o in node["options"]]
        cap = options[0]
        for o in options[1:]:
            cap = Max(cap, o)
        return Min(val, cap)

    elif kind == "cap_lesser_of":
        val = evaluate_ast(node["value"], bindings)
        options = [evaluate_ast(o, bindings) for o in node["options"]]
        cap = options[0]
        for o in options[1:]:
            cap = Min(cap, o)
        return Min(val, cap)

    elif kind == "sum_period":
        term_id = node["term_id"]
        if term_id not in bindings:
            raise KeyError(f"Term '{term_id}' not in bindings for sum_period")
        return bindings[term_id]

    else:
        raise ValueError(f"Unknown AST node kind: {kind}")
