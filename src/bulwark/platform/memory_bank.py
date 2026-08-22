"""Memory Bank: durable, per-vendor state that Drift Sentinel reads and
writes across weeks of otherwise-independent invocations.

This is deliberately distinct from Firestore's control-evidence graph
(platform/models.py): the graph is *what we know about the vendor's
controls*, Memory Bank is *what the fleet remembers about the ongoing
relationship with this vendor* -- negotiated exceptions, accepted-risk
decisions and when they expire, and a reviewer's historical posture
("this reviewer has twice accepted this vendor's compensating control for
CC6.1; don't re-flag it as a fresh gap every sweep"). Without this,
Drift Sentinel would re-litigate the same accepted risk every time it
wakes up.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from bulwark.platform.store import DocumentStore

_COLLECTION = "memory_bank_vendor_state"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VendorMemory:
    vendor_id: str
    last_assessment_at: str | None = None
    negotiated_exceptions: list[dict[str, Any]] = field(default_factory=list)
    accepted_risk_decisions: list[dict[str, Any]] = field(default_factory=list)
    reviewer_posture: dict[str, str] = field(default_factory=dict)  # control_ref -> last reviewer note


class MemoryBank:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore(_COLLECTION)

    def get(self, vendor_id: str) -> VendorMemory:
        data = self._store.get(vendor_id)
        if data is None:
            return VendorMemory(vendor_id=vendor_id)
        data.setdefault("vendor_id", vendor_id)  # tolerate docs written before this field existed
        return VendorMemory(**data)

    def record_assessment(self, vendor_id: str) -> VendorMemory:
        data = self._store.update(vendor_id, {"vendor_id": vendor_id, "last_assessment_at": _now()})
        return VendorMemory(**data)

    def add_negotiated_exception(self, vendor_id: str, control_ref: str, reason: str, expires_at: str) -> VendorMemory:
        self._store.update(vendor_id, {"vendor_id": vendor_id})
        entry = {"control_ref": control_ref, "reason": reason, "expires_at": expires_at, "recorded_at": _now()}
        data = self._store.append_to_list_field(vendor_id, "negotiated_exceptions", entry)
        data.setdefault("vendor_id", vendor_id)
        return VendorMemory(**data)

    def add_accepted_risk(self, vendor_id: str, control_ref: str, actor: str, expires_at: str) -> VendorMemory:
        self._store.update(vendor_id, {"vendor_id": vendor_id})
        entry = {"control_ref": control_ref, "actor": actor, "expires_at": expires_at, "recorded_at": _now()}
        data = self._store.append_to_list_field(vendor_id, "accepted_risk_decisions", entry)
        data.setdefault("vendor_id", vendor_id)
        return VendorMemory(**data)

    def has_active_exception(self, vendor_id: str, control_ref: str) -> bool:
        memory = self.get(vendor_id)
        now = _now()
        for entry in memory.negotiated_exceptions + memory.accepted_risk_decisions:
            if entry["control_ref"] == control_ref and entry["expires_at"] > now:
                return True
        return False

    def note_reviewer_posture(self, vendor_id: str, control_ref: str, note: str) -> VendorMemory:
        memory = self.get(vendor_id)
        posture = {**memory.reviewer_posture, control_ref: note}
        data = self._store.update(vendor_id, {"vendor_id": vendor_id, "reviewer_posture": posture})
        return VendorMemory(**data)


memory_bank = MemoryBank()
