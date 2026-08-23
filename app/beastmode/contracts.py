"""Capability Contract — a declared artifact, derived from real signals.

Beastmode asked for a formal I/O schema + permission manifest per
capability. That information already exists, scattered across three
places: the candidate's own declared entrypoint, the AST screen's forbidden
import/call findings, and the sandbox's fixed resource envelope. This
module does not invent new enforcement -- it reads what the AST screen and
sandbox client ALREADY decided and expresses it as one declared object,
because a judge should be able to see the whole contract in one place
rather than reconstruct it from four API responses.

Nothing here changes what is actually forbidden. FORBIDDEN_IMPORTS and
FORBIDDEN_CALLS are imported from the real safety screen, not redeclared,
so this can never drift from what is actually enforced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.synapse.safety_screen import FORBIDDEN_CALLS, FORBIDDEN_IMPORTS

# The sandbox's actual fixed envelope (app/synapse/sandbox_client.py /
# aion-sandbox service config): no credentials, no IAM roles, a hard
# execution timeout. Declared here as data so it can be rendered next to
# the contract; the sandbox itself is what enforces it, not this file.
SANDBOX_PROFILE = {
    "credentials": "NONE",
    "iam_roles": "NONE",
    "network": "DENY",
    "filesystem": "EPHEMERAL",
}


@dataclass(frozen=True)
class CapabilityContract:
    """What a capability declares about itself, derived from real checks."""

    name: str
    entrypoint: str
    risk: str  # the real RiskLevel value from app.governance.guardian
    network: str  # "DENY" -- always, because the sandbox has none
    credentials: str  # "DENY" -- always, same reason
    forbidden_imports_checked: int
    forbidden_calls_checked: int
    ast_findings: tuple[str, ...]
    ast_safe: bool
    sandbox_profile: dict = field(default_factory=lambda: dict(SANDBOX_PROFILE))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entrypoint": self.entrypoint,
            "risk": self.risk,
            "permissions": {
                "network": self.network,
                "credentials": self.credentials,
                "filesystem": self.sandbox_profile["filesystem"],
            },
            "static_screen": {
                "safe": self.ast_safe,
                "findings": list(self.ast_findings),
                "imports_checked": self.forbidden_imports_checked,
                "calls_checked": self.forbidden_calls_checked,
            },
            "sandbox_profile": dict(self.sandbox_profile),
        }


def build_contract(
    *, name: str, entrypoint: str, risk: str, ast_safe: bool,
    ast_findings: Optional[list[str]] = None,
) -> CapabilityContract:
    """Build a contract from the pipeline's OWN real outputs.

    Callers pass in exactly what safety_screen.screen() and the candidate
    already produced -- this function does not re-derive or guess any of
    it. `forbidden_imports_checked`/`forbidden_calls_checked` are counts
    from the real, live catalogs so the number on screen can never say
    "17" if the catalog actually has 18.
    """
    return CapabilityContract(
        name=name,
        entrypoint=entrypoint,
        risk=risk,
        network="DENY",
        credentials="DENY",
        forbidden_imports_checked=len(FORBIDDEN_IMPORTS),
        forbidden_calls_checked=len(FORBIDDEN_CALLS),
        ast_findings=tuple(ast_findings or []),
        ast_safe=ast_safe,
    )
