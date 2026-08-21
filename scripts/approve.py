"""Owner approval for a pending AION Axon request.

Deliberately a separate, explicit action. Nothing installs itself; the
agent proposes and the owner decides. Usage:

    python scripts/approve.py <request_id> [--reject]

Shows what is being decided BEFORE deciding it -- approving something you
have not read is not approval, it is a rubber stamp.
"""
import os
import sys

import requests

CORE = "https://aion-core-638298765129.asia-south1.run.app"

# Writes require the owner token. Reads do not.
HEADERS = {"X-Axon-Token": os.getenv("AXON_OWNER_TOKEN", "")}


def main() -> None:
    if len(sys.argv) < 2:
        pending = requests.get(f"{CORE}/approvals/pending", timeout=30).json()

        print(f"PENDING APPROVALS: {pending['count']}")

        for item in pending["pending"]:
            print(f"  {item['request_id']}  [{item.get('risk')}]  "
                  f"{item.get('action')}")

        print("\nUsage: python scripts/approve.py <request_id> [--reject]")
        return

    request_id = sys.argv[1]
    approved = "--reject" not in sys.argv

    pending = requests.get(f"{CORE}/approvals/pending", timeout=30).json()
    match = next(
        (p for p in pending["pending"] if p["request_id"] == request_id),
        None,
    )

    if match is None:
        print(f"Request {request_id} is not pending (already decided?).")
        return

    print("YOU ARE DECIDING:")
    print(f"  action : {match.get('action')}")
    print(f"  risk   : {match.get('risk')}")
    print(f"  reason : {match.get('reason')}")
    print(f"  decision: {'APPROVE' if approved else 'REJECT'}")
    print()

    response = requests.post(
        f"{CORE}/approvals/{request_id}/decide",
        json={"approved": approved, "decided_by": "anshul"},
        headers=HEADERS,
        timeout=30,
    )

    print("RESULT:", response.json())


if __name__ == "__main__":
    main()
