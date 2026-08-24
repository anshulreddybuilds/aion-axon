"""Security Coverage Report -- derived, read-only, judge-facing.

Same doctrine as the rest of this package: no new write path, no second
source of truth. Where a number can be computed from the real running
code, it is (the red-team result comes from calling the actual _run(),
not a cached figure; the forbidden-list sizes come from importing
safety_screen's real constants, not copies). Where a number cannot be
safely computed inside an HTTP request -- the regression test count
requires actually running pytest, which this endpoint will never do --
it is a labeled STATIC snapshot with its source commit, never presented
as live.

STATUS VALUES, used consistently and never blurred:
  BLOCKED          -- a real, tested control exists and is enforced today.
  TESTED           -- investigated with real payloads; no exploitable
                       path found (this is evidence of absence, weaker
                       than a positive block, and labeled as such).
  PARTIAL          -- protected in the common case, by a mechanism with
                       a known, disclosed edge.
  KNOWN_LIMITATION -- a real, disclosed gap. Not a euphemism for
                       "insecure" -- a euphemism for "insecure" would be
                       calling this BLOCKED.
  UNVERIFIED       -- genuinely not checked this session. Not claimed
                       either way.
  NOT_APPLICABLE   -- the category does not describe a real risk in
                       this architecture.

This module NEVER writes to FORBIDDEN_IMPORTS/FORBIDDEN_CALLS or any
other real control -- it only reads them, plus a curated historical
record of what was found and fixed. See app/synapse/safety_screen.py
and app/beastmode/red_team.py for the actual controls this describes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.beastmode.red_team import _run
from app.synapse.safety_screen import FORBIDDEN_CALLS, FORBIDDEN_IMPORTS


@dataclass(frozen=True)
class Bypass:
    """A real vulnerability found and fixed this development session --
    not a hypothetical. Every entry here has a real commit, a real
    regression test, and was confirmed exploitable with a direct repro
    BEFORE the fix landed (see each commit message for the exact repro)."""
    name: str
    found: str
    fixed_in_commit: str
    before: str
    after: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "found": self.found,
            "fixed_in_commit": self.fixed_in_commit,
            "before": self.before,
            "after": self.after,
        }


BYPASSES_FOUND_AND_FIXED = (
    Bypass(
        name="Forbidden builtin aliasing",
        found="red-team review",
        fixed_in_commit="930aeda",
        before="`x = eval; x(...)` and `imp = __import__; imp('os').system(...)` "
               "produced zero findings -- the screen only checked the literal "
               "name at the call site.",
        after="Any bare reference to a forbidden builtin is flagged, not only "
              "a direct call by its real name.",
    ),
    Bypass(
        name="__builtins__ capture",
        found="red-team review, same session, immediately after the aliasing fix",
        fixed_in_commit="8a15a12",
        before="`b = __builtins__; b.eval(...)` reached real execution via zero "
               "tokens the aliasing fix flagged -- __builtins__ is dunder-shaped "
               "but is a Name, not an Attribute.",
        after="The dunder check now covers bare Name nodes, not only "
              "ast.Attribute.attr.",
    ),
    Bypass(
        name="Network-capable stdlib beyond socket",
        found="systematic network-egress review",
        fixed_in_commit="1d45c2d",
        before="urllib, http, ftplib, smtplib, xmlrpc, telnetlib and asyncio "
               "were all standard library and all unblocked -- only `socket` "
               "was on the list.",
        after="All seven added to FORBIDDEN_IMPORTS. Sandbox-process-layer "
              "network egress was also independently tested and found to "
              "provide no isolation of its own -- see KNOWN LIMITATIONS.",
    ),
    Bypass(
        name="format-string dunder traversal",
        found="investigation into type()-based indirect callable construction",
        fixed_in_commit="15cc7c7",
        before="'{0.__class__.__bases__[0].__subclasses__}'.format(x) resolved "
               "the full class-hierarchy chain via str.format()'s own runtime "
               "mini-language -- zero ast.Attribute/ast.Name nodes exist for a "
               "chain embedded in a string literal.",
        after="Any .format()/.format_map() call on a string literal containing "
              "'__' is flagged. f-strings were confirmed already safe (their "
              "{expr} fields parse into real ast.Attribute nodes).",
    ),
    Bypass(
        name="Frame / object-graph reflection",
        found="systematic security-category audit (Phase 26)",
        fixed_in_commit="626bb0a",
        before="inspect.currentframe().f_back.f_globals and gc.get_objects() "
               "both passed the screen clean -- frame objects expose "
               "f_globals/f_back/f_locals under ORDINARY, non-dunder "
               "attribute names, invisible to every dunder-based check.",
        after="inspect and gc added to FORBIDDEN_IMPORTS. contextvars was "
              "investigated in the same pass and correctly left unblocked "
              "(no comparable capability) -- a negative-control test proves "
              "this wasn't a reflexive ban on anything reflection-adjacent.",
    ),
)


@dataclass(frozen=True)
class CategoryStatus:
    category: str
    status: str  # BLOCKED | TESTED | PARTIAL | UNVERIFIED | KNOWN_LIMITATION | NOT_APPLICABLE
    layer: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "status": self.status,
            "layer": self.layer,
            "detail": self.detail,
        }


def _static_categories() -> tuple[CategoryStatus, ...]:
    return (
        CategoryStatus("Forbidden imports", "BLOCKED", "AST",
                        f"{len(FORBIDDEN_IMPORTS)} modules blocklisted (see app/synapse/safety_screen.py)."),
        CategoryStatus("Forbidden builtins", "BLOCKED", "AST",
                        f"{len(FORBIDDEN_CALLS)} builtins blocklisted."),
        CategoryStatus("Alias-based bypass", "BLOCKED", "AST",
                        "Bare references to forbidden builtins are flagged, not only direct calls."),
        CategoryStatus("Dunder attribute access", "BLOCKED", "AST", "ast.Attribute.attr checked."),
        CategoryStatus("Bare dunder names", "BLOCKED", "AST", "ast.Name.id checked, not only attributes."),
        CategoryStatus("__builtins__ capture", "BLOCKED", "AST", "Covered by the bare-dunder-name check."),
        CategoryStatus("eval / exec / compile", "BLOCKED", "AST", "Forbidden calls, including aliased."),
        CategoryStatus("globals / locals / vars", "BLOCKED", "AST", "Forbidden calls."),
        CategoryStatus("getattr / setattr", "BLOCKED", "AST", "Forbidden calls."),
        CategoryStatus("Filesystem access", "BLOCKED", "AST",
                        "`open` forbidden; `pathlib`, `shutil` forbidden imports."),
        CategoryStatus("Subprocess", "BLOCKED", "AST", "Forbidden import."),
        CategoryStatus("os / system", "BLOCKED", "AST", "`os` forbidden import."),
        CategoryStatus("Environment variables", "PARTIAL", "AST + SANDBOX",
                        "Needs `os` (blocked); sandbox child process also runs a hardcoded env allowlist, verified live in tests/test_sandbox_service.py."),
        CategoryStatus("Network-capable imports", "BLOCKED", "AST",
                        "socket, urllib, http, ftplib, smtplib, xmlrpc, telnetlib, asyncio."),
        CategoryStatus("Sandbox network egress", "KNOWN_LIMITATION", "SANDBOX",
                        "Empirically tested (tests/test_sandbox_service.py): the sandbox process does NOT independently block a network connection once made. AST is the only control against this vector today."),
        CategoryStatus("Serialization", "PARTIAL", "AST + DEPENDENCY-ABSENCE",
                        "pickle/marshal blocked by AST. yaml is not installed in the sandbox container (ModuleNotFoundError, not a deliberate rule) -- fragile if that ever changes."),
        CategoryStatus("Format-string traversal", "BLOCKED", "AST",
                        ".format()/.format_map() on a dunder-shaped string literal is flagged."),
        CategoryStatus("Resource exhaustion", "BLOCKED", "SANDBOX",
                        "10s CPU / 256MB memory / 1MB file / zero-fork rlimits, plus a real subprocess wall-clock timeout -- non-mocked tests in tests/test_sandbox_service.py. Explicitly NOT an AST-layer control."),
        CategoryStatus("Callable construction / type()", "TESTED", "AST",
                        "A battery of type()/functools.reduce/super()-based payloads found no independently exploitable path beyond the existing dunder checks. Evidence of absence, not a positive block -- not exhaustive."),
        CategoryStatus("Ledger tampering", "TESTED", "LEDGER",
                        "17 attack classes (modify/delete/insert/duplicate/replace/reorder/replay/edge-cases) all correctly detected. Seal storage itself is a disclosed trust-boundary limitation -- see KNOWN LIMITATIONS."),
        CategoryStatus("Provenance / READY-state writes", "TESTED", "PROVENANCE",
                        "Exactly one code path writes state=READY (engine.py install()), gated by a real re-read of the approval record from Firestore."),
        CategoryStatus("Owner authorization", "BLOCKED", "AUTHORIZATION",
                        "16 write endpoints, each individually regression-tested for 401 without a valid token."),
        CategoryStatus("Quarantine", "TESTED", "PROVENANCE",
                        "Derived from real audit events; a quarantined capability is never recommended for reuse by Capability Memory (tested)."),
        CategoryStatus("Approval gate", "BLOCKED", "AUTHORIZATION",
                        "install() never trusts the proposal record's own approval claim -- always re-reads the real approval from Firestore."),
        CategoryStatus("Cloud Run / VPC egress", "KNOWN_LIMITATION", "DEPLOYMENT",
                        "Confirmed via `gcloud run services describe`: no vpc-access-connector annotation on the aion-core service, and the Serverless VPC Access API itself has never been enabled on this GCP project (a live gcloud call to list connectors returned SERVICE_DISABLED). This is positive evidence of ABSENCE, not merely an unchecked box: Cloud Run's default unrestricted internet egress applies, with no VPC-level control layered on top. AST screening (see network-capable imports, above) is the ONLY control against this vector in production today."),
    )


KNOWN_LIMITATIONS = (
    "The sandbox process does not independently block network egress once a "
    "connection is attempted -- AST screening is the only control against "
    "this vector today.",
    "Confirmed (not merely unchecked): the deployed aion-core Cloud Run "
    "service has no VPC connector, and the Serverless VPC Access API has "
    "never been enabled on this GCP project -- egress is Cloud Run's "
    "unrestricted default, with no network-level control layered on top.",
    "YAML containment relies on the dependency being absent from the sandbox "
    "container, not on a deliberate AST rule.",
    "AST screening is fundamentally a blocklist. A sufficiently indirect or "
    "dynamically-constructed payload not yet enumerated could still evade "
    "it -- this is disclosed as an architectural property, not a bug.",
    "The evolution ledger's seal is a local file: an actor with both direct "
    "Firestore write access and local disk write access to it could edit "
    "an event and re-seal over the edit. Tamper-evident, not tamper-proof, "
    "by the module's own stated design.",
)


def build_report() -> dict[str, Any]:
    """Assembles the full report. Read-only: calls _run() (the real,
    live red-team suite) and reads two real module constants. Writes
    nothing, approves nothing, installs nothing."""
    red_team_results, contained = _run()

    return {
        "red_team": {
            "contained": contained,
            "total": len(red_team_results),
            "note": "Computed live by calling the real red-team suite on this request.",
        },
        "bypasses_found_and_fixed": {
            "count": len(BYPASSES_FOUND_AND_FIXED),
            "items": [b.to_dict() for b in BYPASSES_FOUND_AND_FIXED],
        },
        "categories": [c.to_dict() for c in _static_categories()],
        "known_limitations": list(KNOWN_LIMITATIONS),
        "regression_tests": {
            "latest_known": {"value": 454, "as_of_commit": "3a68bfa"},
            "history": [
                {"value": 432, "as_of_commit": "15cc7c7"},
                {"value": 439, "as_of_commit": "10037a2"},
            ],
            "note": "STATIC snapshots, manually recorded when this file was last "
                    "edited -- NEVER computed live. This endpoint does not run "
                    "pytest inside an HTTP request, so it cannot know the true "
                    "current count; 'latest_known' can go stale the moment a "
                    "commit lands that this file wasn't updated alongside. "
                    "Treat this field as historical evidence, never as a live "
                    "claim about the current suite -- the red_team field above "
                    "IS live (it just ran), this field is not.",
        },
        "methodology_note": (
            "Every BLOCKED/TESTED claim above is backed by a real regression "
            "test in the repository -- this report does not introduce a "
            "second source of truth, it reads the same real constants and "
            "runs the same real red-team suite the rest of Beastmode uses."
        ),
    }
