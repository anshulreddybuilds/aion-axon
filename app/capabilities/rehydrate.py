"""Restore acquired capabilities into the registry at startup.

Without this, capability acquisition is an illusion that lasts as long as
one container. The registry is process memory; Cloud Run scales to zero
and recycles on every deploy, so a capability acquired at 09:26 is gone by
09:40 even though Firestore still records it as READY.

Firestore is the durable record of WHAT was acquired. The registry is the
runtime index of what is CALLABLE. This module reconciles the second to
the first, and must run before the service accepts traffic.

Rehydration re-registers the same sandbox proxy the install created, so a
restored capability still executes in the sandbox. Restoring it as
anything else would quietly relocate generated code into aion-core on the
first restart -- the trust boundary would hold at install time and fail
silently afterwards.
"""
import logging
from typing import Any

from app.capabilities.registry import registry
from app.memory.firestore_store import firestore_store

logger = logging.getLogger("aion-core.rehydrate")


def rehydrate_capabilities() -> dict[str, Any]:
    """Re-register every READY acquired capability. Never raises.

    A rehydration failure must not stop the service booting: losing one
    acquired capability is bad, refusing to start at all is worse.
    """
    restored: list[str] = []
    skipped: list[dict[str, str]] = []

    try:
        stored = firestore_store.list_capabilities()
    except Exception as error:  # noqa: BLE001
        logger.error("Rehydration could not read capabilities: %s", error)
        return {"restored": [], "skipped": [], "error": str(error)}

    # Imported here to avoid a circular import: synapse.engine imports the
    # registry, and the registry must not import synapse.
    from app.synapse.engine import synapse

    for record in stored:
        name = record.get("name")

        if not name:
            continue

        if record.get("state") != "READY" or not record.get("implemented"):
            continue

        if registry.is_implemented(name):
            continue  # already present, e.g. a hand-written seed

        candidate = (record.get("passport") or {}).get("candidate") or {}

        if not candidate.get("code") or not candidate.get("entrypoint"):
            # Recorded as READY but missing the code to run. Say so rather
            # than registering something that would fail on first call.
            skipped.append({"name": name, "reason": "no candidate code"})
            continue

        try:
            registry.register(
                name,
                candidate.get("description", record.get("description", "")),
                candidate.get("risk", record.get("risk", "LOW")),
                synapse._sandbox_proxy(candidate),
            )
            restored.append(name)
        except Exception as error:  # noqa: BLE001
            skipped.append({"name": name, "reason": str(error)})

    if restored:
        logger.info("Rehydrated acquired capabilities: %s", restored)

    if skipped:
        logger.warning("Could not rehydrate: %s", skipped)

    return {"restored": restored, "skipped": skipped}
