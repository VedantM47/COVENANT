"""Chain verifier script + tamper detection tests."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.audit import append_event, verify_chain, EventType


async def _build_chain(eng_dir: Path, n: int = 5):
    (eng_dir / "audit").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        await append_event(
            eng_dir, "ENG-TAMPER-TEST", EventType.ENGAGEMENT_CREATED,
            actor={"type": "SYSTEM", "id": "test"},
            payload_summary={"seq": i, "data": "x" * 100},
        )


@pytest.mark.asyncio
async def test_verify_chain_script_clean(tmp_path):
    """verify_chain.py exits 0 on clean chain."""
    eng_dir = tmp_path / "ENG-CLEAN"
    await _build_chain(eng_dir, 10)

    import os
    result = subprocess.run(
        [sys.executable, "scripts/verify_chain.py", str(eng_dir)],
        capture_output=True, text=True, cwd="D:\\covenant",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0
    assert "Chain intact: True" in result.stdout
    assert "Total events: 10" in result.stdout


@pytest.mark.asyncio
async def test_verify_chain_script_tampered(tmp_path):
    """verify_chain.py exits 1 and identifies broken event on tamper."""
    eng_dir = tmp_path / "ENG-TAMPER"
    await _build_chain(eng_dir, 5)

    events_path = eng_dir / "audit" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()

    # Corrupt the payload_summary in line 2 (change a digit)
    event = json.loads(lines[1])
    event["payload_summary"]["seq"] = 999  # change value but keep hash unchanged
    lines[1] = json.dumps(event, sort_keys=True)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/verify_chain.py", str(eng_dir)],
        capture_output=True, text=True, cwd="D:\\covenant",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1
    assert "VIOLATIONS" in result.stdout


@pytest.mark.asyncio
async def test_single_byte_mutation_detected(tmp_path):
    """Mutation in events.jsonl is caught and broken event identified."""
    eng_dir = tmp_path / "ENG-SINGLE-BYTE"
    await _build_chain(eng_dir, 8)

    events_path = eng_dir / "audit" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()

    # Corrupt event at index 3: change a digit in payload_summary
    event = json.loads(lines[3])
    event["payload_summary"]["seq"] = 9999
    lines[3] = json.dumps(event, sort_keys=True)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_chain(eng_dir)
    assert not result.is_intact
    assert len(result.violations) > 0
    broken_indices = [v["event_index"] for v in result.violations]
    assert any(idx >= 3 for idx in broken_indices)


@pytest.mark.asyncio
async def test_chain_append_after_verify(tmp_path):
    """Chain remains intact after appending more events post-verify."""
    eng_dir = tmp_path / "ENG-APPEND"
    await _build_chain(eng_dir, 3)

    r1 = verify_chain(eng_dir)
    assert r1.is_intact

    # Append more events
    await _build_chain(eng_dir, 2)

    r2 = verify_chain(eng_dir)
    assert r2.is_intact
    assert r2.total_events == 5


@pytest.mark.asyncio
async def test_chain_empty_engagement(tmp_path):
    """Empty engagement (no events) verifies as intact."""
    eng_dir = tmp_path / "ENG-EMPTY"
    (eng_dir / "audit").mkdir(parents=True)

    result = verify_chain(eng_dir)
    assert result.is_intact
    assert result.total_events == 0
