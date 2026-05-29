"""Stress test — 10 concurrent synthetic engagements.

Runs FirstBank + Nexus + 8 perturbed variants concurrently.
Verifies no chain failures, no calculation errors, all ratios computed.
"""
from __future__ import annotations

import asyncio
import shutil
import time
import tracemalloc
import uuid
from pathlib import Path

import pytest

from app.audit import verify_chain
from app.settings import get_settings
from app.stages.runner import run_pipeline

FIRSTBANK_DIR = Path("D:/covenant/test_inputs/firstbank")
NEXUS_DIR = Path("D:/covenant/test_inputs/nexus")


def _make_perturbed_metadata(base_meta: dict, seed: int) -> dict:
    """Create a perturbed variant of the metadata for stress testing."""
    import copy
    meta = copy.deepcopy(base_meta)
    # Vary the loan amount slightly
    meta["loan_amount_usd"] = base_meta.get("loan_amount_usd", 200_000_000) + seed * 1_000_000
    meta["engagement_id"] = f"ENG-STRESS-{seed:03d}"
    return meta


async def _run_one_engagement(fixture_dir: Path, seed: int) -> dict:
    """Run one engagement end-to-end. Returns result summary."""
    import json
    settings = get_settings()
    engagement_id = f"ENG-STRESS-{uuid.uuid4().hex[:8].upper()}"
    engagement_dir = settings.ensure_engagement_dirs(engagement_id)

    # Copy fixture files
    raw_dir = engagement_dir / "raw"
    for f in fixture_dir.glob("*.pdf"):
        shutil.copy2(f, raw_dir / f.name)
    for f in fixture_dir.glob("*.xlsx"):
        shutil.copy2(f, raw_dir / f.name)

    metadata = json.loads((fixture_dir / "engagement_metadata.json").read_text())
    metadata = _make_perturbed_metadata(metadata, seed)
    # Inject column override so ambiguity is resolved (simulates gate 2 approval)
    if "firstbank" in str(fixture_dir).lower():
        metadata["_ebitda_total_column_override"] = "Q4-2024"
    else:
        metadata["_ebitda_total_column_override"] = "LTM Total"

    doc_paths = list(raw_dir.glob("*"))
    t0 = time.monotonic()
    results = await run_pipeline(
        engagement_dir, engagement_id, metadata, doc_paths,
        through_stage="stage_4",  # skip stage5 PDF generation for speed
        auto_approve_high_confidence=True,
    )
    duration_s = time.monotonic() - t0

    chain = verify_chain(engagement_dir)
    stage3 = results.get("stage3")
    stage4 = results.get("stage4")

    return {
        "engagement_id": engagement_id,
        "fixture": fixture_dir.name,
        "seed": seed,
        "duration_s": round(duration_s, 2),
        "chain_intact": chain.is_intact,
        "chain_events": chain.total_events,
        "ratios_computed": len(stage3.results) if stage3 else 0,
        "exceptions": len(stage4.exceptions) if stage4 else 0,
        "chain_violations": chain.violations,
    }


@pytest.mark.asyncio
async def test_10_concurrent_engagements():
    """10 synthetic engagements run concurrently without errors."""
    tracemalloc.start()
    wall_start = time.monotonic()

    # 5 FirstBank variants + 5 Nexus variants
    tasks = []
    for i in range(5):
        tasks.append(_run_one_engagement(FIRSTBANK_DIR, seed=i))
    for i in range(5, 10):
        tasks.append(_run_one_engagement(NEXUS_DIR, seed=i))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    wall_total = time.monotonic() - wall_start
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"\n\n=== STRESS TEST RESULTS ===")
    print(f"Wall-clock total: {wall_total:.1f}s")
    print(f"Memory peak: {peak_bytes / 1024 / 1024:.1f} MB")
    print(f"\nPer-engagement results:")
    print(f"{'#':<3} {'Engagement ID':<25} {'Fixture':<12} {'Duration':>10} {'Events':>8} {'Ratios':>8} {'Excepts':>8} {'Chain':>8}")
    print("-" * 90)

    errors = []
    chain_failures = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append(f"Engagement {i}: {type(r).__name__}: {r}")
            print(f"{i:<3} ERROR: {r}")
            continue
        chain_ok = "intact" if r["chain_intact"] else "BROKEN"
        print(f"{i:<3} {r['engagement_id']:<25} {r['fixture']:<12} {r['duration_s']:>9.1f}s {r['chain_events']:>8} {r['ratios_computed']:>8} {r['exceptions']:>8} {chain_ok:>8}")
        if not r["chain_intact"]:
            chain_failures.append(f"  {r['engagement_id']}: {r['chain_violations']}")

    print(f"\nErrors: {len(errors)}")
    print(f"Chain failures: {len(chain_failures)}")
    if chain_failures:
        print("Chain failure details:")
        for cf in chain_failures:
            print(cf)
    print("=== END STRESS TEST ===\n")

    assert not errors, f"Engagement errors:\n" + "\n".join(errors)
    assert not chain_failures, f"Chain failures:\n" + "\n".join(chain_failures)
    for i, r in enumerate(results):
        if not isinstance(r, Exception):
            assert r["ratios_computed"] > 0, f"Engagement {i}: no ratios computed"
