"""P1 (distributed Firestore concurrency) — real emulator test path.

This file exists specifically so a future session (or another agent, per
the project's own continuation policy) does not have to re-derive this
scaffolding. It is SKIPPED, not faked, when no emulator is reachable --
never silently downgraded to a MemoryFirestore/threading test dressed up
as proof of distributed atomicity. Those already exist separately in
tests/test_concurrency.py, with their own honest scope statement.

Why this couldn't be exercised: the Firestore emulator requires a JVM
(`gcloud emulators firestore start` shells out to a bundled jar). `java`
is not on PATH in this environment -- confirmed across multiple sessions,
not assumed. Installing a full JDK just to run one test session is a
heavyweight, one-way environment change disproportionate to a single
verification pass -- flagged for the human owner to decide, not done
silently.

A Docker-based alternative was genuinely attempted (not just considered)
in a later session: Docker Desktop (29.6.1) is installed, but its backend
process crashed on launch (`backend process exited` in Docker Desktop's
own log, ~20s after start, no container ever created) -- almost certainly
a sandboxed/VM environment where the virtualization (WSL2/Hyper-V) Docker
Desktop needs on Windows is restricted. Re-enabling that would mean
changing host virtualization/BIOS-level settings, which is a real system
configuration change, not a "safe and cheap" one -- out of scope here.
Do not re-attempt the Docker path in this same environment without first
confirming virtualization support changed.

To actually run this test for real, in an environment with EITHER a JDK
OR working Docker:

    Option A -- native JDK:
    1. Install a JDK (any recent LTS; the emulator just needs `java` on PATH).
    2. gcloud components install cloud-firestore-emulator
    3. gcloud emulators firestore start --host-port=localhost:8080
    4. In another shell: export FIRESTORE_EMULATOR_HOST=localhost:8080
    5. AXON_FIRESTORE_MODE=emulator python -m pytest tests/test_concurrency_firestore_emulator.py -v

    Option B -- Docker (if the daemon actually starts there):
    1. docker pull gcr.io/google.com/cloudsdktool/cloud-sdk:emulators
    2. docker run -p 8080:8080 gcr.io/google.com/cloudsdktool/cloud-sdk:emulators \
         gcloud emulators firestore start --host-port=0.0.0.0:8080
    3. export FIRESTORE_EMULATOR_HOST=localhost:8080
    4. python -m pytest tests/test_concurrency_firestore_emulator.py -v

The google-cloud-firestore SDK installed here (checked this session) does
expose `Client.transaction()` -- the real API to use for an atomic
install() read-check-write, IF this test proves it's actually needed
(i.e., if the naive multi-process version below shows a real race the
current idempotency guard in app/synapse/engine.py doesn't catch). Do not
add transaction code to engine.py speculatively before that's shown.

UPDATE -- run for real (a later session, with Java available): this test
PASSED, proving Firestore's transaction() API genuinely serializes ten
concurrent writers on one document (1 INSTALLED, 9 ALREADY_INSTALLED,
final version == 1) over a real network-separated Firestore emulator.
That in turn motivated actually checking the "IF" above against
engine.py's real code -- see
tests/test_concurrency_firestore_emulator_engine.py and
AION_AXON_CONTINUATION_HANDOFF.md's P1 section for the answer (a real
race was found and fixed with a new claim_install() transaction).

Also observed this same session: on this specific local single-JVM
emulator, ten threads racing ONE transaction on the SAME document
occasionally exhausts the SDK's default 5-attempt commit retry budget
(`ValueError: Failed to commit transaction in 5 attempts`), more often
once the emulator has been running under sustained load than on a
freshly-started one. That was originally dismissed as a liveness/retry
quirk of this one local emulator ("re-run on failure"), not fixed.

UPDATE -- a later session found that dismissal was premature: the SAME
exhausted-retries failure reproduced against `tests/
test_concurrency_firestore_emulator_engine.py` (the test exercising the
REAL production `claim_install()` code, not this reference test) on 2 of
5 runs -- not a one-off, and not exclusive to this hand-written test.
Raising `max_attempts` alone (tried up to 20) did not fix it, because the
client library's retry loop fires attempts back-to-back with no delay
(by its own design comment). What DID fix it, confirmed reliable across
5+ repeated runs: a real wall-clock sleep with jitter BETWEEN outer
attempts (each a fresh single-attempt transaction), giving the emulator's
lock queue actual time to drain. That fix now lives in both places: for
real in `app/memory/firestore_store.py`'s `AxonFirestore.claim_install()`
(with a new `InstallClaimContention` exception so `install()` fails
honestly instead of raising an unhandled 500 if even that's exhausted),
and mirrored in this reference test's `worker()` so it reflects the
production fix instead of drifting from it. See
`AION_AXON_BUG_AND_PROBLEM_REGISTER.md` BUG-003 for the full account.
"""
import os
import random
import time

import pytest
from google.api_core import exceptions

EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")

pytestmark = pytest.mark.skipif(
    not EMULATOR_HOST,
    reason=(
        "No Firestore emulator reachable (FIRESTORE_EMULATOR_HOST unset). "
        "This is an honest skip, not a fake pass -- see this file's "
        "module docstring for exactly how to run it for real."
    ),
)


@pytest.fixture
def emulator_db():
    """A real Firestore client pointed at the emulator, if one is up.
    Only constructed when the skip guard above has already passed."""
    from google.cloud import firestore

    client = firestore.Client(project="aion-axon-emulator-test")
    yield client

    # Clean up whatever this test session wrote, so re-runs against a
    # persistent local emulator start from a known state.
    for doc in client.collection("emulator_test_capabilities").stream():
        doc.reference.delete()


def test_concurrent_install_against_real_firestore_transaction_semantics(emulator_db):
    """The real test P1 asks for: two processes racing a read-check-write
    install sequence against ACTUAL Firestore (even if only the emulator),
    not an in-process dict. This is what tests/test_concurrency.py's
    threading tests explicitly cannot prove -- a real network-separated
    read/write gap between two independent writers.

    Written but not run this session (no emulator available) -- this is
    the concrete next P1 action for whichever environment has Java.
    """
    from google.cloud import firestore

    doc_ref = emulator_db.collection("emulator_test_capabilities").document("race_target")
    doc_ref.set({"state": "APPROVED", "installed": False, "version": 0})

    @firestore.transactional
    def install_if_not_installed(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict()

        if data.get("installed"):
            return "ALREADY_INSTALLED"

        transaction.update(ref, {"installed": True, "version": data.get("version", 0) + 1})
        return "INSTALLED"

    import concurrent.futures

    def worker():
        # Real behavior discovered running this against an actual
        # emulator (not assumed): under ~10 truly simultaneous
        # transactions on ONE document, the client's own built-in retry
        # (no delay between attempts, by the library's own design) can
        # exhaust its budget while every attempt hits
        # `Aborted: Transaction lock timeout`, even with max_attempts
        # raised as high as 20. What actually resolves it is a real
        # wall-clock sleep with jitter BETWEEN attempts, giving the lock
        # queue time to drain -- the same fix applied for real in
        # app/memory/firestore_store.py's AxonFirestore.claim_install()
        # after this exact test caught the gap. Mirrored here rather than
        # left on the library's bare default, so this reference test
        # reflects the production fix instead of drifting from it.
        last_error: Exception | None = None

        for _ in range(8):
            try:
                transaction = emulator_db.transaction(max_attempts=1)
                return install_if_not_installed(transaction, doc_ref)
            except (ValueError, exceptions.Aborted) as exc:
                last_error = exc
                time.sleep(0.05 + random.random() * 0.15)

        raise last_error

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: worker(), range(10)))

    assert results.count("INSTALLED") == 1
    assert results.count("ALREADY_INSTALLED") == 9

    final = doc_ref.get().to_dict()
    assert final["version"] == 1
