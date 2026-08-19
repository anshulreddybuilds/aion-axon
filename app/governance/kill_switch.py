from datetime import datetime, timezone

from google.cloud import firestore


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


kill_switch = KillSwitch()
