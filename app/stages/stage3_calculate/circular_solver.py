"""Circular cap solver using SymPy.

For a cap of the form: applied = min(raw_value, pct * E)
where E = base + applied (circular), solve for E symbolically.

The equation is:
  E = base_ebitda + min(raw_value, pct * E)

Two cases:
  Case 1: raw_value <= pct * E  →  applied = raw_value  →  E = base + raw_value
  Case 2: raw_value > pct * E   →  applied = pct * E    →  E = base + pct*E
                                                         →  E*(1-pct) = base
                                                         →  E = base / (1 - pct)

We pick the case that is self-consistent (i.e. the assumption holds).
"""
from __future__ import annotations

from sympy import Rational, Min


def solve_circular_cap(
    base_ebitda: Rational,
    raw_value: Rational,
    cap_pct: Rational,
) -> tuple[Rational, Rational]:
    """Return (ebitda_with_cap, applied_cap_value).

    base_ebitda: EBITDA before this circular addback
    raw_value: the uncapped addback amount
    cap_pct: the percentage cap (e.g. Rational(1, 10) for 10%)
    """
    # Case 1: cap is not binding (raw <= pct * E)
    e_case1 = base_ebitda + raw_value
    applied_case1 = raw_value
    # Check: raw_value <= cap_pct * e_case1?
    if raw_value <= cap_pct * e_case1:
        return e_case1, applied_case1

    # Case 2: cap is binding (raw > pct * E)
    # E = base / (1 - pct)
    if cap_pct >= 1:
        raise ValueError(f"cap_pct >= 1 ({cap_pct}) — no finite solution")
    e_case2 = base_ebitda / (1 - cap_pct)
    applied_case2 = cap_pct * e_case2

    # Verify self-consistency: raw_value > cap_pct * e_case2?
    # (should always hold if we got here)
    return e_case2, applied_case2
