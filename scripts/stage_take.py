"""Stage a take: reopen the gap, run the mission, leave an approval pending.

One command between takes. Rolls the capability back so the gap returns,
dispatches the demo mission, runs the acquisition, and stops exactly where
the camera wants it -- with a real request sitting in the approval queue.

    python -m scripts.stage_take

Why a script rather than three curls: the acquisition's evaluator call
fails intermittently, returning no score at all. SYNAPSE correctly refuses
rather than guessing ("missing data never produces a confident verdict"),
but that costs a take. Observed twice in one session. This retries the
acquire ONCE on the same mission, which reuses the planning already paid
for and has recovered every time so far.

Costs roughly 5 Gemini calls, or ~7 if the retry fires.
"""
import os
import sys
import time

import requests

CORE = "https://aion-core-638298765129.asia-south1.run.app"
TIMEOUT = 300

CAPABILITY = os.getenv("AXON_DEMO_CAPABILITY", "calculate_birth_volatility")

REQUEST = (
    "Pull the yearly US birth totals from 2005 onward out of the public "
    "BigQuery dataset, then work out the median and the standard deviation "
    "of those yearly totals so I can see how volatile the series is."
)


def main() -> int:
    token = os.getenv("AXON_OWNER_TOKEN", "").strip()
    if not token:
        print("AXON_OWNER_TOKEN is not set in this shell.")
        print()
        print('  $env:AXON_OWNER_TOKEN = (gcloud secrets versions access '
              'latest --secret=axon-owner-token --project=aion-axon-2026)')
        return 1

    headers = {"X-Axon-Token": token, "Content-Type": "application/json"}

    # 1. Reopen the gap, but only if something is actually installed. The
    #    endpoint writes a ledger event even for a no-op, and that count is
    #    on screen during the demo.
    passport = requests.get(
        f"{CORE}/capabilities/{CAPABILITY}/passport", timeout=TIMEOUT
    ).json()

    if passport.get("implemented"):
        requests.post(
            f"{CORE}/synapse/rollback/{CAPABILITY}",
            json={"reason": "Reset between camera takes — restoring the gap."},
            headers=headers,
            timeout=TIMEOUT,
        )
        print(f"[1/3] rolled back {CAPABILITY} — gap reopened")
    else:
        print(f"[1/3] {CAPABILITY} not installed — gap already open")

    # 2. The mission. It must BLOCK; if it completes, the gap did not exist
    #    and there is nothing to acquire.
    print("[2/3] running the mission…")
    mission = requests.post(
        f"{CORE}/missions/planned",
        json={"request": REQUEST},
        headers=headers,
        timeout=TIMEOUT,
    ).json()

    mission_id = mission.get("mission_id")
    status = mission.get("status")

    if status != "BLOCKED":
        print(f"      mission came back {status}, not BLOCKED.")
        print(f"      {str(mission.get('error') or mission)[:300]}")
        return 1

    gap = mission.get("blocked_on") or {}
    print(f"      BLOCKED on: "
          f"{(gap.get('capability_description') or gap.get('description') or '')[:80]}")

    # 3. Acquire, with one retry for the flaky evaluator.
    for attempt in (1, 2):
        print(f"[3/3] acquiring (attempt {attempt})…")
        record = requests.post(
            f"{CORE}/missions/{mission_id}/acquire",
            json={},
            headers=headers,
            timeout=TIMEOUT,
        ).json()

        if record.get("status") == "AWAITING_APPROVAL":
            evaluation = record.get("evaluation") or {}
            print()
            print("  READY FOR THE TAKE")
            print(f"  candidate : {(record.get('candidate') or {}).get('name')}")
            print(f"  sandbox   : {(record.get('tests') or {}).get('status')} "
                  f"exit {(record.get('tests') or {}).get('exit_code')}")
            print(f"  evaluator : {evaluation.get('verdict')} "
                  f"{evaluation.get('score')}")
            print(f"  approval  : {record.get('approval_request_id')}")
            print()
            print("  Open aion-axon-2026.web.app/v4, press Send, and")
            print("  'STOPPED - 1 WAITING ON YOU' will be there.")
            return 0

        evaluation = record.get("evaluation") or {}
        score = evaluation.get("score")

        # CORRECTED, after testing this directly against the engine: an
        # evaluation that genuinely comes back UNSCORED does NOT reject --
        # app/synapse/engine.py lets it through to AWAITING_APPROVAL,
        # clearly marked, exactly like the "READY FOR THE TAKE" branch
        # above. So if we are in THIS branch with an empty `evaluation`
        # dict, evaluation never ran at all -- something upstream
        # (research or generation) failed first, which prints identically
        # (score=None) but is a different fact. The earlier version of
        # this script blamed "the evaluator" for exactly this case, which
        # was wrong; see tests/test_evaluator_unscored_escalates.py.
        if evaluation:
            # Evaluation DID run and produced a real, scored verdict below
            # the floor. That is governance working correctly, not a
            # transient, and must not be retried away.
            print(f"      REJECTED — evaluator genuinely scored this "
                  f"{score}, below the floor")
            print()
            print("  The evaluator scored this candidate and it failed on")
            print("  the merits. That is the governance working, not a bug.")
            print(f"  reason: {(evaluation.get('reason') or '')[:160]}")
            return 1

        print(f"      {record.get('status')} — evaluation never ran: "
              f"{str(record.get('reason') or record.get('error') or '')[:160]}")

        if attempt == 1:
            time.sleep(2)

    print()
    print("  Failed twice before evaluation ever ran. Not retrying further —")
    print("  a third attempt would spend quota on the same transient.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
