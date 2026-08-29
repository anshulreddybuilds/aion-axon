"""Real-emulator regression test for the approval-decide race fixed
alongside this file: ApprovalManager.decide() used to do a plain read
(get()) then a separate write (update_approval()) -- the exact
read-check-write shape that test_concurrency_firestore_emulator_engine.py
proved races for real on installs before claim_install() existed, and
which decide() never got the same fix for. Two concurrent decide() calls
on the same request_id could both pass the "still PENDING" check before
either wrote, and the second .update() would silently overwrite the
first's status/approved/decided_by/decided_at -- an approval recorded as
APPROVED could flip to REJECTED (or vice versa) with no error to either
caller.

firestore_store.decide_approval() closes this the same way
claim_install() closes the install race: a real `@firestore.transactional`
check-and-set on the approval_requests/{id} document, kept in its own
method so ApprovalManager.decide() and this test both exercise the exact
production code path -- no separate scaffold in this file, unlike the
paired test_concurrency_firestore_emulator.py.

Requires TWO things set in the shell BEFORE pytest starts, same reasoning
as test_concurrency_firestore_emulator_engine.py's own docstring:

    export FIRESTORE_EMULATOR_HOST=localhost:8080
    export AXON_FIRESTORE_MODE=emulator   # anything other than "memory"
    python -m pytest tests/test_concurrency_firestore_emulator_approval.py -v

Run this file in ISOLATION, never mixed into a normal `pytest -q` run --
same reasoning as the sibling emulator files: it makes the real
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

from app.governance.approval import approval_manager  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402


def test_ten_concurrent_decisions_against_real_networked_firestore_produce_exactly_one_winner():
    """Ten real OS threads race decide() on the SAME approval_request_id
    over the real emulator (a genuine network round trip between the
    transaction's read and write, unlike MemoryFirestore/threading which
    tests/test_concurrency.py already covers and which cannot exercise
    this gap -- see that file's own docstring). Exactly one decision
    must win; every other caller must observe ALREADY_DECIDED, never a
    corrupted or overwritten record."""
    suffix = uuid.uuid4().hex[:8]
    approval_id = f"race-decide-real-network-{suffix}"

    firestore_store.create_approval(approval_id, {
        "action": "install capability: race_test",
        "risk": "MEDIUM",
        "reason": "test",
        "policy_id": "INSTALL",
        "capability": "race_test",
    })

    n = 10
    barrier = threading.Barrier(n)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(i: int):
        barrier.wait()
        try:
            # Alternate approve/reject so a real race would be visible
            # as a mixed final state, not just a duplicate of the same
            # decision.
            approval_manager.decide(approval_id, approved=(i % 2 == 0), decided_by=f"racer-{i}")
            outcome = "WON"
        except ValueError:
            outcome = "ALREADY_DECIDED"
        except KeyError:
            outcome = "NOT_FOUND"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("WON") == 1, (
        f"expected exactly one real decision to win over the network, got {outcomes}"
    )
    assert outcomes.count("ALREADY_DECIDED") == n - 1, (
        f"expected the rest to see ALREADY_DECIDED, got {outcomes}"
    )
    assert "NOT_FOUND" not in outcomes

    stored = firestore_store.get_approval(approval_id)
    assert stored["status"] in ("APPROVED", "REJECTED")
    # The winner's own approved flag must match its recorded status --
    # proof the transaction committed one coherent, uncorrupted decision
    # rather than a torn write from two racers.
    assert stored["approved"] == (stored["status"] == "APPROVED")
