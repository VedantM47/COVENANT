"""Hash-chain verifier.

Re-walks events.jsonl, recomputes every hash, reports violations.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.audit.canonical import canonical_json


@dataclass
class ChainVerifyResult:
    is_intact: bool
    total_events: int
    violations: list[dict] = field(default_factory=list)


def verify_chain(engagement_dir: Path) -> ChainVerifyResult:
    path = engagement_dir / "audit" / "events.jsonl"
    if not path.exists():
        return ChainVerifyResult(is_intact=True, total_events=0)

    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    if not events:
        return ChainVerifyResult(is_intact=True, total_events=0)

    violations = []
    previous_hash = "GENESIS"

    for idx, event in enumerate(events):
        stored_hash = event.get("event_hash", "")
        stored_prev = event.get("previous_hash", "")

        # Check previous_hash linkage
        if stored_prev != previous_hash:
            violations.append({
                "event_index": idx,
                "event_id": event.get("event_id"),
                "error": "previous_hash_mismatch",
                "expected": previous_hash,
                "found": stored_prev,
            })

        # Recompute hash
        body = {k: v for k, v in event.items() if k != "event_hash"}
        expected_hash = hashlib.sha256(
            canonical_json(body) + b"|" + stored_prev.encode()
        ).hexdigest()

        if expected_hash != stored_hash:
            violations.append({
                "event_index": idx,
                "event_id": event.get("event_id"),
                "error": "hash_mismatch",
                "expected": expected_hash,
                "found": stored_hash,
            })

        previous_hash = stored_hash

    return ChainVerifyResult(
        is_intact=len(violations) == 0,
        total_events=len(events),
        violations=violations,
    )
