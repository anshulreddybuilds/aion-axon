"""Test-session guard: no test may ever touch production Firestore.

`app.memory.firestore_store` picks its backend ONCE, at import time, from
`AXON_FIRESTORE_MODE` -- memory store if "memory", the real `AxonFirestore`
otherwise. That makes the choice a property of *import order*, which is not
something a test file can control.

Every file under `tests/` sets the variable itself, but that only protects
the suite if a test module is the first thing to import the store. It was
not: `scripts/test_approval_resume.py` is a manual probe, not a test, and
it matched pytest's `test_*.py` pattern. `scripts/` sorts before `tests/`,
so on a bare `pytest -q` that script was imported first, built a real
`AxonFirestore`, and every later test that expected the in-memory store
died with `AttributeError: 'AxonFirestore' object has no attribute
'capabilities'` -- 121 errors from one import.

pytest loads the rootdir conftest before any test module, so setting the
variable here fixes the ordering problem at its root: the backend is chosen
correctly no matter what gets imported first, or how pytest is invoked.

This is a safety property, not just a convenience. The failure it prevents
is not a red suite -- it is a test run quietly reading and writing the
live project's Firestore.
"""
import os

# setdefault, not assignment: an integration run that deliberately exports
# AXON_FIRESTORE_MODE=real must still be able to.
os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
