"""What the owner sees BEFORE approving — the code, not a description.

Stage 10 of the audit. Until now an approval showed a capability name, a
one-line description, a risk level and a reason. None of that is the thing
being authorised. The thing being authorised is source code that a model
wrote and that will run on the owner's infrastructure.

For a project whose whole claim is accountable autonomy, approving a
description of code is a signature on an unread document. This assembles
the evidence a human actually needs: the source, a diff against the
installed version when there is one, what the sandbox did with it, and
what the evaluator thought.

It deliberately shows the FULL source for a first install rather than a
diff against nothing. "No previous version" is information, not an empty
diff to be skimmed past.
"""
import difflib
from typing import Any, Optional

from app.memory.firestore_store import firestore_store

MAX_CODE_CHARS = 20_000


def _capability_for(approval: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Find the capability an approval authorises.

    Prefers the explicit link. Falls back to scanning passports for the
    request id, so approvals created before the link existed still resolve
    rather than silently showing nothing.
    """
    named = approval.get("capability")

    if named:
        record = firestore_store.get_capability(named)

        if record is not None:
            return record

    request_id = approval.get("request_id")

    for record in firestore_store.list_capabilities():
        passport = record.get("passport") or {}

        if passport.get("approval_request_id") == request_id:
            return record

    return None


def build_diff(previous: str, proposed: str, name: str) -> list[str]:
    return list(
        difflib.unified_diff(
            (previous or "").splitlines(),
            (proposed or "").splitlines(),
            fromfile=f"{name} (installed)",
            tofile=f"{name} (proposed)",
            lineterm="",
            n=3,
        )
    )


def review_package(request_id: str) -> dict[str, Any]:
    """Everything a human needs to decide, in one response."""
    approval = firestore_store.get_approval(request_id)

    if approval is None:
        return {"status": "NOT_FOUND", "request_id": request_id}

    package: dict[str, Any] = {
        "status": "OK",
        "request_id": request_id,
        "action": approval.get("action"),
        "risk": approval.get("risk"),
        "reason": approval.get("reason"),
        "policy_id": approval.get("policy_id"),
        "decision_status": approval.get("status"),
        "capability": approval.get("capability"),
        "code": None,
        "diff": [],
        "is_first_version": None,
        "tests": None,
        "evaluation": None,
        "safety": None,
        "research": None,
    }

    record = _capability_for(approval)

    if record is None:
        # Not every approval concerns code -- a payment under G-02 has no
        # source to show. Say so rather than rendering an empty panel that
        # looks like a loading failure.
        package["note"] = (
            "This approval does not concern generated code, so there is "
            "nothing to review here."
        )
        return package

    passport = record.get("passport") or {}
    candidate = passport.get("candidate") or {}

    proposed = (candidate.get("code") or "")[:MAX_CODE_CHARS]

    package.update({
        "capability": record.get("name") or package["capability"],
        "description": candidate.get("description"),
        "entrypoint": candidate.get("entrypoint"),
        "code": proposed,
        "test_code": candidate.get("test"),
        "tests": passport.get("tests"),
        "evaluation": passport.get("evaluation"),
        "safety": passport.get("safety"),
        "research": passport.get("research"),
        "current_version": record.get("version", 0),
    })

    installed = record.get("installed_code")

    package["is_first_version"] = not installed

    if installed:
        package["diff"] = build_diff(
            installed, proposed, record.get("name", "capability"),
        )

    return package
