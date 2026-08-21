"""Owner authentication for the routes that can change something.

Discovered by curling the deployed service: every mutating endpoint was
publicly callable. A stranger could approve a capability, record a false
"fact" to demote one, or flip the kill switch mid-demo. For a system whose
whole claim is governed access, "anyone on the internet can approve a
capability" is the contradiction that undoes the rest of the argument.

An earlier note in this project claimed the CORS allowlist protected these
routes. It does not. CORS is a browser mechanism: it stops a webpage from
calling the API on a visitor's behalf, and does nothing at all against
curl, a script, or anything that is not a browser.

Design decisions worth stating:

- **Reads stay public.** Judges, the Holo-Deck and anyone curious can
  inspect every decision, every audit event and every Skill Passport. The
  transparency is the point; only the ability to CHANGE things is gated.

- **Fail closed.** If no token is configured, writes are refused rather
  than left open. A security control whose absence silently disables it is
  not a control -- and this hole existed precisely because "no auth" was
  the quiet default.

- **Constant-time comparison**, so the token cannot be recovered a
  character at a time from response timings.

This is a bearer token, not real authentication. The honest answer is
Firebase Auth or IAP; that is a bigger change than the remaining days
allow, and shipping the small correct thing beats shipping the ambitious
unfinished one. Recorded as a known limitation rather than dressed up.
"""
import os
import secrets

from fastapi import Header, HTTPException

TOKEN_ENV = "AXON_OWNER_TOKEN"
HEADER = "X-Axon-Token"


def configured_token() -> str:
    return os.getenv(TOKEN_ENV, "").strip()


def require_owner(x_axon_token: str = Header(default="")) -> None:
    """Reject any write that does not carry the owner token.

    Raises 503 rather than 401 when the server has no token configured:
    the caller did nothing wrong, the deployment is misconfigured, and
    saying so plainly is more useful than an authentication error that
    sends someone hunting for a credential that does not exist yet.
    """
    expected = configured_token()

    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "This deployment has no owner token configured, so writes "
                f"are refused. Set {TOKEN_ENV} (via Secret Manager) to "
                "enable them."
            ),
        )

    if not x_axon_token or not secrets.compare_digest(
        x_axon_token, expected
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                f"This action changes state and requires the {HEADER} "
                "header. Reads are public; writes are not."
            ),
        )
