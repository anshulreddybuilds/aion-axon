from datetime import datetime, timezone
from typing import Any, Optional
import os

from google.cloud import firestore


class MemoryFirestore:
    def __init__(self):
        self.approvals: dict[str, dict[str, Any]] = {}
        self.audit_events: dict[str, dict[str, Any]] = {}
        self.missions: dict[str, dict[str, Any]] = {}

    def create_approval(self, request_id: str, data: dict[str, Any]) -> None:
        self.approvals[request_id] = {
            **data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING",
        }

    def update_approval(
        self,
        request_id: str,
        approved: bool,
        decided_by: str = "human",
    ) -> None:
        self.approvals[request_id].update({
            "status": "APPROVED" if approved else "REJECTED",
            "approved": approved,
            "decided_by": decided_by,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_approval(self, request_id: str) -> Optional[dict[str, Any]]:
        return self.approvals.get(request_id)

    def write_audit_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> str:
        event_id = f"memory-{len(self.audit_events) + 1}"
        self.audit_events[event_id] = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        return event_id

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [
            {**data, "request_id": request_id}
            for request_id, data in self.approvals.items()
            if data.get("status") == "PENDING"
        ]

    def save_mission(self, mission_id: str, data: dict[str, Any]) -> None:
        self.missions[mission_id] = {
            **data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_mission(self, mission_id: str) -> Optional[dict[str, Any]]:
        return self.missions.get(mission_id)


class AxonFirestore:
    def __init__(self):
        self.db = firestore.Client(project="aion-axon-2026")

    def create_approval(self, request_id: str, data: dict[str, Any]) -> None:
        self.db.collection("approval_requests").document(request_id).set({
            **data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING",
        })

    def update_approval(
        self,
        request_id: str,
        approved: bool,
        decided_by: str = "human",
    ) -> None:
        self.db.collection("approval_requests").document(request_id).update({
            "status": "APPROVED" if approved else "REJECTED",
            "approved": approved,
            "decided_by": decided_by,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_approval(self, request_id: str) -> Optional[dict[str, Any]]:
        snapshot = (
            self.db
            .collection("approval_requests")
            .document(request_id)
            .get()
        )

        if not snapshot.exists:
            return None

        return snapshot.to_dict()

    def write_audit_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> str:
        reference = self.db.collection("audit_events").document()

        reference.set({
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        })

        return reference.id

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        query = (
            self.db
            .collection("approval_requests")
            .where("status", "==", "PENDING")
        )

        return [
            {**doc.to_dict(), "request_id": doc.id}
            for doc in query.stream()
        ]

    def save_mission(self, mission_id: str, data: dict[str, Any]) -> None:
        self.db.collection("missions").document(mission_id).set({
            **data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_mission(self, mission_id: str) -> Optional[dict[str, Any]]:
        snapshot = self.db.collection("missions").document(mission_id).get()

        if not snapshot.exists:
            return None

        return snapshot.to_dict()


if os.getenv("AXON_FIRESTORE_MODE") == "memory":
    firestore_store = MemoryFirestore()
else:
    firestore_store = AxonFirestore()
