"""Reset the demo to a clean pre-acquisition state, between camera takes.

Rolls back an acquired capability so its capability GAP returns, which is
what makes the acquisition act repeatable. Without this, the second take
has nothing to acquire -- the capability already exists, so the mission
never blocks and the whole story collapses.

Costs ZERO Gemini quota. Rollback is a registry operation; no model is
called. That matters when the free tier allows roughly four takes a day.

Usage, from the repo root:

    python -m scripts.reset_take
    python -m scripts.reset_take some_other_capability

Exists because the equivalent curl is an inline-JSON POST, and PowerShell
mangles inline JSON -- a trap already recorded in CLAUDE.md that cost a
failed command mid-session. A script has no quoting to get wrong.
"""
import os
import sys

import requests

CORE = "https://aion-core-638298765129.asia-south1.run.app"

# The capability the locked demo story acquires. Overridable by argument.
DEFAULT_CAPABILITY = "evaluate_birth_total_volatility"

TIMEOUT = 60


def main() -> int:
    token = os.getenv("AXON_OWNER_TOKEN", "").strip()

    if not token:
        print("AXON_OWNER_TOKEN is not set in this shell.")
        print()
        print("  $env:AXON_OWNER_TOKEN = (gcloud secrets versions access latest "
              "--secret=axon-owner-token --project=aion-axon-2026)")
        return 1

    capability = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CAPABILITY
    headers = {"X-Axon-Token": token, "Content-Type": "application/json"}

    before = requests.get(f"{CORE}/capabilities", timeout=TIMEOUT).json()
    print(f"before : {before.get('implemented')} of {before.get('total')} implemented")

    response = requests.post(
        f"{CORE}/synapse/rollback/{capability}",
        json={"reason": "Reset between camera takes — restoring the gap."},
        headers=headers,
        timeout=TIMEOUT,
    )

    body = response.json()
    status = body.get("status")

    if status != "ROLLED_BACK":
        # Reported, never smoothed over. A rollback that did not happen and
        # says nothing leaves the next take starting from the wrong state.
        print(f"ROLLBACK DID NOT COMPLETE: {status}")
        print(f"  {str(body)[:300]}")
        return 1

    after = requests.get(f"{CORE}/capabilities", timeout=TIMEOUT).json()
    pending = requests.get(f"{CORE}/approvals/pending", timeout=TIMEOUT).json()

    print(f"after  : {after.get('implemented')} of {after.get('total')} implemented")
    print(f"ledger event: {body.get('evolution_event_id')}")
    print(f"approval queue: {pending.get('count')} pending")
    print()

    # The server answers ROLLED_BACK even when the capability was ALREADY
    # rolled back -- it reports the end state, not whether anything moved.
    # Saying "gap restored" on a no-op would be the same class of lie this
    # project exists to avoid, and between takes it would let the operator
    # believe a reset happened when nothing did.
    if body.get("was_registered"):
        print(f"ROLLED BACK: {capability} was registered and has been removed.")
        print("Gap restored. The mission will block again on the next run.")
    else:
        print(f"NO CHANGE: {capability} was not registered — already rolled back.")
        print("The gap was already open. Safe to run the take.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
