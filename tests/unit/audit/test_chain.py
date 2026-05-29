"""Unit tests for audit chain."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.audit import append_event, verify_chain, EventType
from app.audit.canonical import canonical_json


@pytest.fixture
def tmp_engagement(tmp_path):
    eng_dir = tmp_path / "ENG-TEST"
    (eng_dir / "audit").mkdir(parents=True)
    return eng_dir


@pytest.mark.asyncio
async def test_chain_genesis(tmp_engagement):
    """First event has previous_hash=GENESIS."""
    await append_event(
        tmp_engagement, "ENG-TEST", EventType.ENGAGEMENT_CREATED,
        actor={"type": "SYSTEM", "id": "test"},
        payload_summary={"test": True},
    )
    events_path = tmp_engagement / "audit" / "events.jsonl"
    events = [json.loads(l) for l in events_path.read_text().splitlines() if l.strip()]
    assert events[0]["previous_hash"] == "GENESIS"


@pytest.mark.asyncio
async def test_chain_links(tmp_engagement):
    """N events form a valid chain."""
    for i in range(5):
        await append_event(
            tmp_engagement, "ENG-TEST", EventType.ENGAGEMENT_CREATED,
            actor={"type": "SYSTEM", "id": "test"},
            payload_summary={"i": i},
        )
    result = verify_chain(tmp_engagement)
    assert result.is_intact
    assert result.total_events == 5
    assert result.violations == []


@pytest.mark.asyncio
async def test_chain_tamper_detected(tmp_engagement):
    """Single-byte mutation is detected."""
    for i in range(3):
        await append_event(
            tmp_engagement, "ENG-TEST", EventType.ENGAGEMENT_CREATED,
            actor={"type": "SYSTEM", "id": "test"},
            payload_summary={"i": i},
        )

    events_path = tmp_engagement / "audit" / "events.jsonl"
    content = events_path.read_bytes()

    # Mutate one byte in the middle of the file
    mid = len(content) // 2
    mutated = content[:mid] + bytes([content[mid] ^ 0x01]) + content[mid+1:]
    events_path.write_bytes(mutated)

    result = verify_chain(tmp_engagement)
    assert not result.is_intact
    assert len(result.violations) > 0


def test_canonical_json_stable():
    """canonical_json produces identical bytes for same dict regardless of insertion order."""
    d1 = {"b": 2, "a": 1, "c": [3, 1, 2]}
    d2 = {"a": 1, "c": [3, 1, 2], "b": 2}
    assert canonical_json(d1) == canonical_json(d2)


def test_canonical_json_datetime():
    """Datetime serializes to ISO 8601 with Z suffix."""
    from datetime import datetime, timezone
    dt = datetime(2025, 5, 28, 14, 23, 18, 214000, tzinfo=timezone.utc)
    result = canonical_json({"ts": dt})
    assert b"2025-05-28T14:23:18.214000Z" in result
