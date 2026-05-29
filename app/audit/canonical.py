"""Canonical JSON encoding for hash-chain integrity.

Rules (from brief section 5.1):
- sort_keys=True
- separators=(",", ":")
- ensure_ascii=False
- datetime → ISO 8601 with microseconds, "Z" suffix for UTC
- Decimal/Rational → str(...)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal


def _default(obj):
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    if isinstance(obj, Decimal):
        return str(obj)
    # sympy types
    try:
        from sympy import Rational, Basic
        from sympy.logic.boolalg import BooleanAtom
        if isinstance(obj, BooleanAtom):
            return bool(obj)
        if isinstance(obj, Rational):
            return str(obj)
        if isinstance(obj, Basic):
            return str(obj)
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def canonical_json(obj: dict) -> bytes:
    """Return stable UTF-8 bytes for hashing."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    ).encode("utf-8")
