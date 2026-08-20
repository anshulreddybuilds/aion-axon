"""Client for the aion-sandbox service.

Two jobs, and the second is the architectural one:

1. Run candidate code during stage-2 testing.
2. Run INSTALLED generated capabilities, permanently.

That second point is deliberate. Generated code never executes inside
aion-core, not even after it is approved and installed. Approval means the
owner accepted the capability, not that the code became trustworthy enough
to sit beside the credentials. An installed capability is a proxy that
calls the sandbox; the trust boundary is permanent, not a testing phase.

Authentication uses the Cloud Run metadata server to mint an OIDC identity
token for the sandbox's audience. That keeps the sandbox deployable
WITHOUT --allow-unauthenticated while storing no shared secret in it --
identity, not a password, so rule 5 holds.
"""
import os
from typing import Any, Optional

import requests

SANDBOX_URL = os.getenv(
    "AION_SANDBOX_URL",
    "https://aion-sandbox-638298765129.asia-south1.run.app",
)

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/identity"
)

DEFAULT_TIMEOUT = 30


def _identity_token(audience: str) -> Optional[str]:
    """Mint an OIDC token for the sandbox, or None when not on Cloud Run.

    Returning None rather than raising keeps local development working
    against an unauthenticated sandbox without a second code path.
    """
    try:
        response = requests.get(
            METADATA_TOKEN_URL,
            params={"audience": audience},
            headers={"Metadata-Flavor": "Google"},
            timeout=3,
        )
        response.raise_for_status()
        return response.text
    except Exception:  # noqa: BLE001 - absence of metadata is not an error
        return None


def execute_in_sandbox(
    code: str,
    test: str = "",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Run code in the isolated service. Never raises.

    A sandbox outage and a failing candidate must stay distinguishable:
    `status` is UNREACHABLE for the former and COMPLETED for the latter.
    Collapsing them would let SYNAPSE install a capability it never
    actually tested.
    """
    headers = {"Content-Type": "application/json"}

    token = _identity_token(SANDBOX_URL)

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            f"{SANDBOX_URL}/execute",
            json={
                "code": code,
                "test": test,
                "timeout_seconds": timeout_seconds,
            },
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception as error:  # noqa: BLE001
        return {
            "status": "UNREACHABLE",
            "passed": False,
            "reason": f"{type(error).__name__}: {error}",
        }

    if response.status_code != 200:
        return {
            "status": "UNREACHABLE",
            "passed": False,
            "reason": f"Sandbox returned HTTP {response.status_code}.",
            "body": response.text[:500],
        }

    return response.json()


def env_proof() -> dict[str, Any]:
    """Read the sandbox's credential scan, authenticated.

    The sandbox is not publicly reachable, so this needs the same identity
    token as /execute. A 403 here means core lost its invoker role, which
    is a different failure from the service being down -- reporting them
    the same way would send someone debugging the wrong thing.
    """
    headers = {}

    token = _identity_token(SANDBOX_URL)

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            f"{SANDBOX_URL}/env-proof", headers=headers, timeout=10,
        )
    except Exception as error:  # noqa: BLE001
        return {"verdict": "UNREACHABLE", "error": str(error)}

    if response.status_code == 403:
        return {
            "verdict": "FORBIDDEN",
            "error": (
                "aion-core is not authorised to invoke aion-sandbox. "
                "Check the run.invoker binding on aion-core-sa."
            ),
        }

    if response.status_code != 200:
        return {
            "verdict": "UNREACHABLE",
            "error": f"Sandbox returned HTTP {response.status_code}.",
        }

    return response.json()
