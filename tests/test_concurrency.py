"""CONCURRENCY (Batch 2 completion) — real races, honestly scoped.

Environment check performed before writing anything here: `java` is not
on PATH in this environment (`java: command not found`), and the
Firestore emulator requires a JVM to run. No Firestore emulator is
available. Per the remediation directive's own instruction for that
case, this file does NOT fake concurrency with sequential calls dressed
up as a race -- every test below launches real `threading.Thread`s
synchronized with a `threading.Barrier` so they call the code under test
at the same instant, and asserts on the actual interleaved outcome.

What this DOES prove: the existing guards (install()'s idempotency check
from the last Batch 2 pass, decide()'s already-decided check) hold under
real concurrent access to the MemoryFirestore backend this repo uses for
tests/CI -- and, by extension, to a SINGLE Cloud Run instance handling
concurrent requests where the critical section has no real I/O yield
point (CPython's GIL serializes a synchronous read-then-write sequence
with no `await`/`time.sleep()` in the middle, so two threads cannot
actually interleave mid-check the way two separate processes could).

What this does NOT and CANNOT prove: safety across MULTIPLE Cloud Run
instances writing to real, networked Firestore concurrently. There,
firestore_store.get_capability() and .save_capability() are separate
network round-trips, not atomic in-memory dict operations -- a second
instance's write could land in the gap between another instance's read
and write, a race no amount of Python-level threading can reproduce.
Verifying THAT would require the emulator (or real Firestore) and is
explicitly documented here as unverified, not silently assumed safe.
Firestore's own `transaction()` API is the correct tool for that gap if
it's ever closed; not added here without being able to test it against
a real Firestore connection.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import threading  # noqa: E402

from app.governance.approval import approval_manager  # noqa: E402
from app.governance.guardian import RiskLevel  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.memory.firestore_store import (  # noqa: E402
    InstallClaimContention,
    firestore_store,
)
from app.synapse.engine import synapse  # noqa: E402


def _install_and_approve(name: str, approval_id: str) -> None:
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
    firestore_store.approvals[approval_id] = {
        "status": "APPROVED", "decided_by": "anshul",
        "action": "install", "risk": "LOW", "reason": "ok",
    }


def test_ten_concurrent_installs_produce_exactly_one_real_install():
    """10 real OS threads call install() at the same synchronized instant
    against the same already-approved capability."""
    _install_and_approve("race_install", "race-install-appr")

    n = 10
    barrier = threading.Barrier(n)
    results: list[str] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        r = synapse.install("race_install")
        with lock:
            results.append(r["status"])

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("INSTALLED") == 1
    assert results.count("ALREADY_INSTALLED") == n - 1
    assert firestore_store.get_capability("race_install")["version"] == 1
    events = [
        e for e in firestore_store.list_evolution_events()
        if e.get("capability_id") == "race_install"
    ]
    assert len(events) == 1, "concurrent installs must not duplicate a ledger event"

    registry.unregister("race_install")


def test_concurrent_approve_and_reject_produce_exactly_one_winner():
    """Real threads racing decide(True) against decide(False) on the
    SAME request. Exactly one must win; the other must see the
    already-decided ValueError, never a silently overwritten decision."""
    request = approval_manager.create(
        action="install capability: race_decide", risk=RiskLevel.MEDIUM,
        reason="x",
    )

    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, str]] = []
    lock = threading.Lock()

    def approve():
        barrier.wait()
        try:
            approval_manager.decide(request.request_id, True, "anshul")
            with lock:
                outcomes.append(("approve", "OK"))
        except ValueError:
            with lock:
                outcomes.append(("approve", "REJECTED_AS_ALREADY_DECIDED"))

    def reject():
        barrier.wait()
        try:
            approval_manager.decide(request.request_id, False, "anshul")
            with lock:
                outcomes.append(("reject", "OK"))
        except ValueError:
            with lock:
                outcomes.append(("reject", "REJECTED_AS_ALREADY_DECIDED"))

    t1 = threading.Thread(target=approve)
    t2 = threading.Thread(target=reject)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    ok_count = sum(1 for _, status in outcomes if status == "OK")
    assert ok_count == 1, "exactly one decision must win the race, never zero or two"

    final = approval_manager.get(request.request_id)
    assert final.approved in (True, False)  # a real, single, non-null outcome


def test_concurrent_installs_of_two_different_capabilities_do_not_interfere():
    """A race on capability A must not affect capability B's own
    independent installation -- confirms the guard is keyed correctly,
    not accidentally global."""
    _install_and_approve("race_a", "race-a-appr")
    _install_and_approve("race_b", "race-b-appr")

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}
    lock = threading.Lock()

    def install(name: str):
        barrier.wait()
        r = synapse.install(name)
        with lock:
            results[name] = r["status"]

    t1 = threading.Thread(target=install, args=("race_a",))
    t2 = threading.Thread(target=install, args=("race_b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["race_a"] == "INSTALLED"
    assert results["race_b"] == "INSTALLED"

    registry.unregister("race_a")
    registry.unregister("race_b")


def test_killswitch_activated_mid_install_race_never_produces_a_ready_capability_without_a_real_install():
    """One thread flips the kill switch while another is mid-install --
    the capability must end either genuinely INSTALLED (the install won
    the race before the switch landed) or genuinely BLOCKED
    (state never reaches READY), never a torn/partial state."""
    _install_and_approve("race_ks", "race-ks-appr")

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}
    lock = threading.Lock()

    def install():
        barrier.wait()
        r = synapse.install("race_ks")
        with lock:
            results["install"] = r["status"]

    def flip_switch():
        barrier.wait()
        kill_switch.activate("race test")

    t1 = threading.Thread(target=install)
    t2 = threading.Thread(target=flip_switch)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    kill_switch.deactivate()

    stored = firestore_store.get_capability("race_ks")
    if results["install"] == "INSTALLED":
        assert stored["state"] == "READY"
    else:
        assert results["install"] == "BLOCKED"
        assert stored["state"] != "READY"

    registry.unregister("race_ks")


def test_install_fails_honestly_when_claim_is_genuinely_contended():
    """Found live against a real Firestore emulator (not in this
    MemoryFirestore-backed file): under heavy real lock contention,
    claim_install() can exhaust its own internal retry budget without
    ever determining a winner or loser, and now raises
    InstallClaimContention rather than letting an unhandled exception
    escape. install() must turn that into an honest FAILED status --
    never ALREADY_INSTALLED (that would fabricate a state nobody
    actually reached) and never a crash. This test cannot reproduce the
    real contention itself (MemoryFirestore's claim_install() cannot
    raise it), so it verifies the contract directly: patch claim_install
    to raise, and check install()'s response.
    """
    name = "contended_capability"
    approval_id = "contended-approval"
    _install_and_approve(name, approval_id)

    original_claim_install = firestore_store.claim_install

    def raise_contention(_name, _request_id):
        raise InstallClaimContention("simulated real lock contention")

    firestore_store.claim_install = raise_contention
    try:
        result = synapse.install(name)
    finally:
        firestore_store.claim_install = original_claim_install

    assert result["status"] == "FAILED"
    assert result["capability"] == name
    assert "retry" in result["error"].lower()

    audit = firestore_store.audit_events
    contended = [
        e for e in audit.values() if e.get("event_type") == "INSTALL_CLAIM_CONTENDED"
    ]
    assert len(contended) == 1
    assert contended[0]["capability"] == name

    registry.unregister(name)
