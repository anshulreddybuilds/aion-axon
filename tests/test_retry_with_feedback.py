"""synapse.propose(allow_retry=True) — bounded retry with real feedback.

Failure recovery was confirmed absent in docs/AXON_BEASTMODE_AUDIT.md.
This is the one change in the Beastmode pass that touches propose()
itself -- the exact path proven live, repeatedly, tonight -- so every
test here either proves the new behavior or proves the OLD behavior is
untouched by default.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from unittest.mock import patch

from app.synapse.engine import synapse
from app.synapse.generator import Candidate

_BAD_CANDIDATE = Candidate(
    name="bad_cap", description="fails its own test",
    code="def bad_cap(x): return x + 1",
    test="assert bad_cap(1) == 99",  # deliberately wrong
    entrypoint="bad_cap", risk="LOW",
)

_GOOD_CANDIDATE = Candidate(
    name="bad_cap", description="corrected candidate",
    code="def bad_cap(x): return x + 1",
    test="assert bad_cap(1) == 2",
    entrypoint="bad_cap", risk="LOW",
)

_FAILED_SANDBOX = {
    "status": "COMPLETED", "exit_code": 1, "passed": False,
    "stdout": "", "stderr": "AssertionError: bad_cap(1) == 99",
}

_PASSED_SANDBOX = {
    "status": "COMPLETED", "exit_code": 0, "passed": True,
    "stdout": "OK\n", "stderr": "",
}

_GOOD_EVAL = {
    "status": "SCORED", "model": "gemma-4-26b-a4b-it",
    "score": 90, "verdict": "PASS", "reason": "fine",
}


def test_default_behaviour_is_unchanged_one_failure_rejects_immediately():
    """allow_retry defaults to False. A candidate that fails its sandbox
    test must be REJECTED on the first failure, exactly as before this
    feature existed -- no second attempt, no extra generate_candidate call."""
    call_count = {"n": 0}

    def counting_generate(need, research=None):
        call_count["n"] += 1
        return _BAD_CANDIDATE, None

    with patch("app.synapse.engine.generate_candidate", side_effect=counting_generate), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAILED_SANDBOX):
        record = synapse.propose("a fake need")  # allow_retry NOT passed

    assert record.status == "REJECTED"
    assert call_count["n"] == 1, "default path must call generate_candidate exactly once"


def test_retry_recovers_when_the_second_candidate_passes():
    """allow_retry=True: first candidate fails, second (informed by the
    real stderr) passes -- the acquisition must proceed past sandbox
    rather than reject on the first failure."""
    attempts = []

    def sequenced_generate(need, research=None, prior_failure=None):
        attempts.append(prior_failure)
        if len(attempts) == 1:
            return _BAD_CANDIDATE, None
        return _GOOD_CANDIDATE, None

    def sequenced_sandbox(code, test):
        if len(attempts) == 1:
            return _FAILED_SANDBOX
        return _PASSED_SANDBOX

    with patch("app.synapse.engine.generate_candidate", side_effect=sequenced_generate), \
         patch("app.synapse.engine.execute_in_sandbox", side_effect=sequenced_sandbox), \
         patch("app.synapse.engine.evaluate", return_value=_GOOD_EVAL):
        record = synapse.propose("a fake need", allow_retry=True)

    assert len(attempts) == 2
    # The retry must carry the REAL stderr, not a placeholder.
    assert attempts[1] is not None
    assert "AssertionError" in attempts[1]
    assert record.status == "AWAITING_APPROVAL"
    assert record.tests["passed"] is True

    # The record must carry visible proof that attempt 1 failed and
    # attempt 2 succeeded -- this is what a UI needs to show the retry
    # ever happened, since `record.candidate`/`record.tests` only ever
    # hold the LAST attempt's data.
    assert len(record.attempts) == 2
    assert record.attempts[0]["attempt"] == 1
    assert record.attempts[0]["outcome"] == "SANDBOX_FAILED"
    assert "AssertionError" in record.attempts[0]["detail"]
    assert record.attempts[1]["attempt"] == 2
    assert record.attempts[1]["outcome"] == "SANDBOX_PASSED"


def test_retry_still_rejects_if_the_second_attempt_also_fails():
    """Bounded means bounded: two real failures in a row must reject, not
    try a third time."""
    call_count = {"n": 0}

    def always_bad(need, research=None, prior_failure=None):
        call_count["n"] += 1
        return _BAD_CANDIDATE, None

    with patch("app.synapse.engine.generate_candidate", side_effect=always_bad), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAILED_SANDBOX):
        record = synapse.propose("a fake need", allow_retry=True)

    assert record.status == "REJECTED"
    assert call_count["n"] == 2, "must attempt exactly twice, never a third time"
    assert "2 attempts" in record.reason
    assert len(record.attempts) == 2
    assert all(a["outcome"] == "SANDBOX_FAILED" for a in record.attempts)


def test_a_safety_screen_rejection_is_never_retried_even_with_allow_retry():
    """Retrying a policy refusal until it stops triggering would be
    indistinguishable from evading the screen. Must reject on attempt one
    regardless of allow_retry."""
    call_count = {"n": 0}
    unsafe = Candidate(
        name="unsafe_cap", description="reads env",
        code="import os\ndef unsafe_cap(): return os.environ",
        test="assert True", entrypoint="unsafe_cap", risk="LOW",
    )

    def counting_generate(need, research=None, prior_failure=None):
        call_count["n"] += 1
        return unsafe, None

    with patch("app.synapse.engine.generate_candidate", side_effect=counting_generate):
        record = synapse.propose("a fake need", allow_retry=True)

    assert record.status == "REJECTED"
    assert call_count["n"] == 1, "an unsafe candidate must never trigger a retry"
