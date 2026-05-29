"""Append-only hash-chained audit log writer.

Chain rule (brief section 5.2):
  event_hash = hex(sha256(canonical_json(event_minus_hash) + b"|" + previous_hash.encode()))

First event: previous_hash = "GENESIS"
Writes are serialized per engagement via asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.canonical import canonical_json
from app.audit.events import EventType

# Per-engagement locks
_locks: dict[str, asyncio.Lock] = {}
_locks_meta: asyncio.Lock = asyncio.Lock()


async def _get_lock(engagement_id: str) -> asyncio.Lock:
    async with _locks_meta:
        if engagement_id not in _locks:
            _locks[engagement_id] = asyncio.Lock()
        return _locks[engagement_id]


def _events_path(engagement_dir: Path) -> Path:
    return engagement_dir / "audit" / "events.jsonl"


def _compute_hash(event_body: dict, previous_hash: str) -> str:
    body_bytes = canonical_json(event_body)
    return hashlib.sha256(body_bytes + b"|" + previous_hash.encode()).hexdigest()


def _read_last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "GENESIS"
    with open(path, "rb") as f:
        # Read last non-empty line
        lines = [l.strip() for l in f.read().splitlines() if l.strip()]
    if not lines:
        return "GENESIS"
    last = json.loads(lines[-1])
    return last["event_hash"]


async def append_event(
    engagement_dir: Path,
    engagement_id: str,
    event_type: EventType,
    actor: dict,
    payload_summary: dict | None = None,
    input_references: list[str] | None = None,
    output_references: list[str] | None = None,
    event_category: str | None = None,
) -> dict:
    """Append one hash-chained event. Returns the full event dict."""
    lock = await _get_lock(engagement_id)
    path = _events_path(engagement_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with lock:
        previous_hash = _read_last_hash(path)

        event_id = f"evt_{uuid.uuid4().hex[:20]}"
        now = datetime.now(timezone.utc)

        # Build event body (without event_hash)
        body: dict[str, Any] = {
            "event_id": event_id,
            "engagement_id": engagement_id,
            "event_type": str(event_type),
            "event_category": event_category or str(event_type).lower(),
            "event_timestamp": now,
            "actor": actor,
            "input_references": input_references or [],
            "output_references": output_references or [],
            "payload_summary": payload_summary or {},
            "previous_hash": previous_hash,
        }

        event_hash = _compute_hash(body, previous_hash)
        body["event_hash"] = event_hash

        # Append to JSONL — use canonical_json encoding so verifier can recompute
        with open(path, "a", encoding="utf-8") as f:
            f.write(canonical_json(body).decode("utf-8") + "\n")

        return body
