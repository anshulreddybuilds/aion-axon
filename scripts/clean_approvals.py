"""Reject stale PENDING approvals left over from testing.

Rejecting an approval is a recorded decision, not housekeeping, so this
DRY RUNS by default and writes nothing until you pass --apply.

Why it matters for the demo: a queue full of abandoned test requests makes
the approval card unreadable, and an owner who scrolls past six stale
items to find the real one is being trained to click without reading --
which is exactly the failure the approval gate exists to prevent.

    python -m scripts.clean_approvals              # show what would go
    python -m scripts.clean_approvals --apply      # actually reject them
    python -m scripts.clean_approvals --older-than 2 --apply
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

CORE = "https://aion-core-638298765129.asia-south1.run.app"

# Writes require the owner token. Reads do not.
HEADERS = {"X-Axon-Token": os.getenv("AXON_OWNER_TOKEN", "")}


def age_hours(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        return 0.0

    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    return (datetime.now(timezone.utc) - created).total_seconds() / 3600


def main() -> None:
    apply = "--apply" in sys.argv

    threshold = 1.0
    if "--older-than" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--older-than") + 1])

    pending = requests.get(f"{CORE}/approvals/pending", timeout=30).json()

    stale = [
        p for p in pending["pending"]
        if age_hours(p.get("created_at")) >= threshold
    ]

    print(f"PENDING: {pending['count']}  |  older than {threshold}h: "
          f"{len(stale)}")
    print()

    for item in stale:
        hours = age_hours(item.get("created_at"))
        print(f"  {item['request_id']}  {hours:5.1f}h  {item.get('action')}")

    if not stale:
        print("  nothing to clean")
        return

    if not apply:
        print("\nDRY RUN — nothing was changed. Re-run with --apply to "
              "reject these.")
        return

    print()

    for item in stale:
        response = requests.post(
            f"{CORE}/approvals/{item['request_id']}/decide",
            json={"approved": False, "decided_by": "anshul (stale cleanup)"},
            headers=HEADERS,
            timeout=30,
        )
        print(f"  rejected {item['request_id']}: "
              f"{response.json().get('status')}")

    print("\nRejections are recorded in the audit trail, not deleted.")


if __name__ == "__main__":
    main()
