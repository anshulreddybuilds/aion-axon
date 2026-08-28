"""Real-emulator regression test for the mission-resume race fixed
alongside this file (see tests/test_mission_resume_race.py for the full
account and the MemoryFirestore-backed proof). This file closes the same
gap the sibling emulator tests already closed for installs and
approvals: proving claim_mission_transition() actually serializes
concurrent callers over a REAL, network-separated Firestore connection,
not just an in-process GIL-protected dict.

Requires TWO things set in the shell BEFORE pytest starts, same
reasoning as the sibling emulator files' own docstrings:

    export FIRESTORE_EMULATOR_HOST=localhost:8080
    export AXON_FIRESTORE_MODE=emulator   # anything other than "memory"
    python -m pytest tests/test_concurrency_firestore_emulator_mission_resume.py -v

Run this file in ISOLATION, never mixed into a normal `pytest -q` run --
same reasoning as the other emulator files: it makes the real
AxonFirestore backend active for the whole process.
"""
import os
import threading
import uuid

import pytest

EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")
FIRESTORE_MODE = os.environ.get("AXON_FIRESTORE_MODE")

pytestmark = pytest.mark.skipif(
    not EMULATOR_HOST or not FIRESTORE_MODE or FIRESTORE_MODE == "memory",
    reason=(
        "Requires FIRESTORE_EMULATOR_HOST set AND AXON_FIRESTORE_MODE set "
        "to something other than 'memory', both exported in the shell "
        "BEFORE pytest starts (see this file's module docstring). An "
        "honest skip, not a fake pass."
    ),
)

from app.memory.firestore_store import firestore_store  # noqa: E402


def test_ten_concurrent_resume_claims_against_real_networked_firestore_produce_exactly_one_winner():
    """Ten real OS threads race claim_mission_transition() on the SAME
    mission document over the real emulator -- a genuine network round
    trip between the transaction's read and write, unlike
    MemoryFirestore/threading which cannot exercise this gap. Exactly one
    caller must win the claim; every other caller must see False, never a
    corrupted or double-claimed status."""
    mission_id = f"race-resume-real-network-{uuid.uuid4().hex[:8]}"

    firestore_store.save_mission(mission_id, {"status": "BLOCKED"})

    n = 10
    barrier = threading.Barrier(n)
    outcomes: list[bool] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        won = firestore_store.claim_mission_transition(mission_id, "BLOCKED", "RESUMING")
        with lock:
            outcomes.append(won)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count(True) == 1, (
        f"expected exactly one real claim to win over the network, got {outcomes}"
    )
    assert outcomes.count(False) == n - 1, (
        f"expected the rest to lose the claim cleanly, got {outcomes}"
    )

    stored = firestore_store.get_mission(mission_id)
    assert stored["status"] == "RESUMING"
