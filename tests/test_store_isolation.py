"""The test suite must never reach the live project's Firestore.

NOTE: this file deliberately does NOT set `AXON_FIRESTORE_MODE` itself.
Every other test file does, and that is exactly why the guard was missing
for so long -- the suite looked protected because each file protected
itself, while the actual backend is chosen once by whoever imports
`app.memory.firestore_store` first. On a bare `pytest -q` that turned out
to be `scripts/test_approval_resume.py`, a manual probe that merely
matched `test_*.py`, and the whole suite inherited a real Firestore
client.

By setting nothing, this file tests the rootdir `conftest.py` rather than
its own preamble. If the guard is ever removed, this fails.
"""
from app.memory.firestore_store import MemoryFirestore, firestore_store


def test_the_suite_runs_against_the_in_memory_store():
    """A red suite was the *symptom*. The danger was a test run silently
    reading and writing the live project's Firestore.
    """
    assert isinstance(firestore_store, MemoryFirestore), (
        "Tests are pointed at a REAL Firestore client. Something imported "
        "app.memory.firestore_store before AXON_FIRESTORE_MODE was set — "
        "check the rootdir conftest.py, and check whether a non-test file "
        "matching test_*.py has been added outside tests/."
    )


def test_the_memory_store_exposes_the_collections_fixtures_clear():
    """Fixtures across the suite call `.capabilities.clear()` and friends.
    The real client has no such attributes, which is how the original
    failure surfaced: AttributeError, 121 times, from one stray import.
    """
    for collection in (
        "approvals", "audit_events", "missions", "capabilities",
        "evolution_events", "monitors", "ground_truth",
    ):
        assert hasattr(firestore_store, collection), collection
