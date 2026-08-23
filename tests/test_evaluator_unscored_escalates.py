"""An UNSCORED evaluation must escalate to a human, never auto-reject.

Written after a real mistake this session: a live acquisition came back
with no evaluator score and was assumed to be a bug in how the engine
handles UNSCORED verdicts. Direct testing showed the code was already
correct -- the actual cause was almost certainly generation or research
failing transiently before evaluation ever ran, which prints identically
(score=None) to a genuine UNSCORED verdict but means something very
different: "no evaluation happened" vs. "evaluation happened and honestly
reported no verdict".

This test locks in the CORRECT, existing behavior as a permanent
regression guard, and exists specifically so that distinction is never
misdiagnosed again: a real UNSCORED result must reach AWAITING_APPROVAL,
clearly marked, not be silently treated as a rejection worth retrying.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from unittest.mock import patch

from app.synapse.engine import synapse
from app.synapse.generator import Candidate

_FAKE_CANDIDATE = Candidate(
    name="fake_cap",
    description="test",
    code='def fake_cap(x): return {"ok": True}',
    test='assert fake_cap(1)["ok"]',
    entrypoint="fake_cap",
    risk="LOW",
)

_FAKE_SANDBOX_RESULT = {
    "status": "COMPLETED", "exit_code": 0, "passed": True,
    "stdout": "OK\n", "stderr": "",
}

_UNSCORED = {
    "status": "UNSCORED", "model": "gemma-4-26b-a4b-it",
    "score": None, "verdict": None,
    "reason": "Evaluator response could not be parsed into a score.",
}


def test_unscored_evaluation_reaches_awaiting_approval_not_rejection():
    with patch("app.synapse.engine.generate_candidate", return_value=(_FAKE_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAKE_SANDBOX_RESULT), \
         patch("app.synapse.engine.evaluate", return_value=_UNSCORED):
        record = synapse.propose("a fake need")

    assert record.status == "AWAITING_APPROVAL"
    assert record.approval_request_id is not None
    assert record.evaluation["status"] == "UNSCORED"
    assert record.evaluation["score"] is None


def test_unscored_is_distinguishable_from_a_genuine_low_score():
    """The two cases must never collapse into the same on-screen result:
    'no verdict available' and 'verdict says this is unsafe' are different
    facts and call for different human reactions."""
    low_score = {
        "status": "SCORED", "model": "gemma-4-26b-a4b-it",
        "score": 10, "verdict": "FAIL", "reason": "trivial test coverage",
    }

    with patch("app.synapse.engine.generate_candidate", return_value=(_FAKE_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAKE_SANDBOX_RESULT), \
         patch("app.synapse.engine.evaluate", return_value=low_score):
        rejected = synapse.propose("a fake need")

    assert rejected.status == "REJECTED"
    assert rejected.evaluation["score"] == 10

    with patch("app.synapse.engine.generate_candidate", return_value=(_FAKE_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAKE_SANDBOX_RESULT), \
         patch("app.synapse.engine.evaluate", return_value=_UNSCORED):
        unscored = synapse.propose("a fake need")

    assert unscored.status == "AWAITING_APPROVAL"
    assert unscored.evaluation["score"] is None
