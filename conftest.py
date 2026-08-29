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


# The same guard, for the model API.
#
# Firestore was fenced off; the Gemini key was not. So the suite's behaviour
# depended on whether a real key happened to be exported in the shell that
# ran it:
#
#     no key   ->  280 passed in 4.5s, zero network
#     key set  ->  ~4 MINUTES of real billed calls, and non-deterministic --
#                  one run produced 14 failures, the next produced 280 passes
#                  from the identical commit
#
# Found 23 Aug, when a key was exported to probe which models a new API key
# could see and the very next `pytest -q` in that same terminal came back
# red. Half the diagnosis was spent looking for a regression that did not
# exist.
#
# Three separate problems, not one:
#   1. Running tests silently spent daily quota -- the scarcest resource on
#      this project, and the one the demo depends on.
#   2. `.githooks/pre-push` runs this suite. A push from a terminal holding a
#      key would burn quota and could be blocked by an unrelated network
#      blip, on a repo whose whole discipline is that a red suite means a
#      real defect.
#   3. Green stopped meaning anything fixed, because it depended on ambient
#      environment rather than on the code.
#
# No test in this suite is written to need a live model: there are no live
# markers and nothing skips on a missing key. Reaching the network was never
# intended, so the fix is to make it impossible by default.
#
# Opt back in deliberately with AXON_LIVE_MODEL_TESTS=1 for a genuine
# integration run. That is an explicit, quota-spending choice -- which is
# what it always should have been.
if not os.environ.get("AXON_LIVE_MODEL_TESTS"):
    for _key_var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(_key_var, None)
