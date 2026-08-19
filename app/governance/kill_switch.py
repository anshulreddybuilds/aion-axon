from datetime import datetime, timezone
import os

from google.cloud import firestore


class MemoryKillSwitch:
    """In-memory kill switch for deterministic local/CI tests.

    Mirrors KillSwitch semantics: inactive until activated. Selected only
    by AXON_FIRESTORE_MODE=memory; production always uses KillSwitch.
    """

    def __init__(self):
        self.state: dict[str, object] = {"kill_switch": False, "reason": None}

    def is_active(self) -> bool:
        return bool(self.state.get("kill_switch", False))

    def activate(self, reason: str = "Human emergency stop") -> None:
        self.state.update({
            "kill_switch": True,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def deactivate(self) -> None:
        self.state.update({
            "kill_switch": False,
            "reason": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


class KillSwitch:
    def __init__(self):
        self.db = firestore.Client(project="aion-axon-2026")
        self.ref = self.db.collection("system").document("control")

    def is_active(self) -> bool:
        snapshot = self.ref.get()

        if not snapshot.exists:
            return False

        return bool(snapshot.to_dict().get("kill_switch", False))

    def activate(self, reason: str = "Human emergency stop") -> None:
        self.ref.set({
            "kill_switch": True,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, merge=True)

    def deactivate(self) -> None:
        self.ref.set({
            "kill_switch": False,
            "reason": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, merge=True)


if os.getenv("AXON_FIRESTORE_MODE") == "memory":
    kill_switch = MemoryKillSwitch()
else:
    kill_switch = KillSwitch()
