"""Verify hash chain for an engagement.

Usage: python scripts/verify_chain.py D:\covenant\engagements\ENG-XXX
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.audit import verify_chain


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_chain.py <engagement_dir>")
        sys.exit(1)

    engagement_dir = Path(sys.argv[1])
    if not engagement_dir.exists():
        print(f"ERROR: {engagement_dir} does not exist")
        sys.exit(1)

    result = verify_chain(engagement_dir)

    print(f"Engagement: {engagement_dir.name}")
    print(f"Total events: {result.total_events}")
    print(f"Chain intact: {result.is_intact}")

    if result.violations:
        print(f"\nVIOLATIONS ({len(result.violations)}):")
        for v in result.violations:
            print(f"  Event #{v['event_index']} ({v.get('event_id', 'unknown')}): {v['error']}")
        sys.exit(1)
    else:
        print("PASS Chain verified -- no violations")
        sys.exit(0)


if __name__ == "__main__":
    main()
