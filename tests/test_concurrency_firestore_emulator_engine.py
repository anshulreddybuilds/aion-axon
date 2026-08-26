"""P1 (distributed Firestore concurrency) -- does engine.py's ACTUAL
install() path race under real network-separated Firestore, not just
in-process threading against MemoryFirestore?

tests/test_concurrency_firestore_emulator.py (the sibling scaffold, now
run for real -- see AION_AXON_CONTINUATION_HANDOFF.md) proved Firestore's
own transaction() API correctly serializes concurrent writers. It did
NOT prove anything about engine.py itself, because engine.py's install()
does a plain read-check-write with no transaction() -- confirmed by
reading app/synapse/engine.py directly (lines ~362-441).

tests/test_concurrency.py already proves the idempotency guard holds
under 10 real OS threads racing against MemoryFirestore -- but its own
docstring is explicit that this cannot prove anything about a real
network round-trip gap between read and write, because MemoryFirestore
is a single in-process dict and CPython's GIL serializes the whole
critical section (no `await`/`time.sleep()` in the middle).

This file closes that exact gap: the SAME race, against the REAL
AxonFirestore client pointed at the emulator, where get_capability() and
save_capability() are genuine separate network round-trips.

Requires TWO things set in the shell BEFORE pytest starts (not settable
from inside a test module -- app.memory.firestore_store picks its
backend once, at import time):

    export FIRESTORE_EMULATOR_HOST=localhost:8080
    export AXON_FIRESTORE_MODE=emulator   # anything other than "memory"
    python -m pytest tests/test_concurrency_firestore_emulator_engine.py -v

Why AXON_FIRESTORE_MODE must be exported first, not just FIRESTORE_EMULATOR_HOST:
the root conftest.py does `os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")`
specifically so no test run ever touches production Firestore by accident.
setdefault() only fills in the variable if it is UNSET -- so it must
already be set, by the shell, before pytest (and therefore conftest.py)
even starts, for AxonFirestore (rather than MemoryFirestore) to be the
backend actually under test here.

Honest disclosure about this test's own reliability: ten threads racing
one real Firestore transaction on the SAME document is genuine, heavy
optimistic-concurrency contention, and the default retry budget
(google-cloud-firestore's `transaction()` gives up after 5 commit
attempts) is occasionally not enough against this specific local
single-JVM emulator -- observed directly this session, more often once
the emulator process had been running under sustained load for a while
than on a freshly-started one. When that happens the failure is a
`ValueError: Failed to commit transaction in 5 attempts` raised inside a
worker thread (a liveness/retry-budget limit), never a wrong result --
every run that DID complete produced exactly the invariant this test
asserts (1 INSTALLED, 9 ALREADY_INSTALLED, 1 evolution event), repeatedly,
including immediately after a failed run on the very same emulator
process. Re-run on failure before suspecting the fix; this is a known
characteristic of a single local emulator process under heavy contention,
not of Firestore's transaction semantics in production, which distributes
contention handling rather than serializing it through one JVM.

Run this file in ISOLATION, never mixed into a normal `pytest -q` /
`pytest tests/` run -- it deliberately makes the real AxonFirestore
backend active for the whole process, which every other test in this
suite assumes is never the case. Safe to do because FIRESTORE_EMULATOR_HOST
redirects the underlying google-cloud-firestore SDK to the local emulator
regardless of the project id string AxonFirestore hardcodes -- confirmed
by the sibling scaffold test actually running successfully in an
environment with no GOOGLE_APPLICATION_CREDENTIALS / ADC configured at
all (a real call would have failed on missing credentials, not silently
succeeded against production).
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

from app.capabilities.registry import registry  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.synapse.engine import synapse  # noqa: E402


def test_ten_concurrent_installs_against_real_networked_firestore_produce_exactly_one_install():
    """The same race as test_concurrency.py's in-process version, this
    time with firestore_store as the real AxonFirestore client talking
    to the emulator over the network -- a genuine read/write gap is
    possible here in a way it structurally cannot be against a
    GIL-serialized in-process dict."""
    # Unique per test run, not hardcoded: claim_install() records its
    # claim permanently (by design -- a replayed request_id must always
    # see ALREADY_INSTALLED, even long after the original install). A
    # fixed name would make a second run against the same persistent
    # emulator see 10/10 ALREADY_INSTALLED and look like a regression
    # when it is actually the fix correctly recognizing a stale claim
    # from the previous run.
    suffix = uuid.uuid4().hex[:8]
    name = f"race_install_real_network_{suffix}"
    approval_id = f"race-install-real-network-appr-{suffix}"

    firestore_store.save_capability(name, {
        "name": name, "description": "x", "risk": "LOW", "state": "VALIDATING",
        "implemented": False, "version": 0,
        "passport": {
            "need": "x", "approval_request_id": approval_id,
            "candidate": {
                "name": name, "description": "x", "risk": "LOW",
                "code": "def f(x):\n    return x\n", "entrypoint": "f",
            },
        },
    })
    firestore_store.create_approval(approval_id, {
        "action": "install", "risk": "LOW", "reason": "ok",
    })
    firestore_store.update_approval(approval_id, approved=True, decided_by="anshul")

    try:
        n = 10
        barrier = threading.Barrier(n)
        results: list[str] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            r = synapse.install(name)
            with lock:
                results.append(r["status"])

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("INSTALLED") == 1, (
            f"expected exactly one real install over the network, got {results}"
        )
        assert results.count("ALREADY_INSTALLED") == n - 1, (
            f"expected the rest to see ALREADY_INSTALLED, got {results}"
        )

        stored = firestore_store.get_capability(name)
        assert stored["version"] == 1, (
            f"version should have incremented exactly once, got {stored['version']}"
        )

        events = [
            e for e in firestore_store.list_evolution_events()
            if e.get("capability_id") == name
        ]
        assert len(events) == 1, (
            "concurrent installs over real networked Firestore must not "
            f"duplicate a ledger event, got {len(events)}"
        )
    finally:
        registry.unregister(name)
