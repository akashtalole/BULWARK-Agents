"""Rollback (section 8): "All L3 actions are reversible by construction.
Every action writes a compensating-action record; POST /runs/{id}/rollback
replays them in reverse."

Grouping key: the spec's endpoint is keyed by a run id, but the
identifier actually threaded through every action in a chain -- across
agents, across Pub/Sub hops -- is ``trace_id`` (it's what every Envelope
and every audit-log/reasoning-chain entry already correlates on), not the
Drift Sentinel-specific ``Run`` checkpoint records in platform/models.py
(those track one sweep's internal steps, not a whole causal chain). So
``trace_id`` is what this module groups compensating actions by, and
what ``POST /runs/{trace_id}/rollback`` takes as its path parameter.

Only genuinely reversible actions get a compensating-action record: the
two the spec calls out by name -- reopening an assessment (Drift
Sentinel) and opening a ticket (Remediation Router). Both are simple
field-level state changes, so "replay in reverse" here means literally
that: restore the field to its pre-action value.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from bulwark.platform.store import DocumentStore

SubjectType = Literal["vendor", "ticket"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CompensatingAction:
    action_id: str
    trace_id: str
    action_type: str  # e.g. "reopen_assessment", "open_ticket"
    subject_type: SubjectType
    subject_id: str
    field: str
    before_value: Any
    after_value: Any
    created_at: str = field(default_factory=_now)
    rolled_back: bool = False


class RollbackLedger:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("compensating_actions")

    def record(
        self, *, trace_id: str, action_type: str, subject_type: SubjectType, subject_id: str, field_name: str, before_value: Any, after_value: Any,
    ) -> CompensatingAction:
        action = CompensatingAction(
            action_id=f"comp_{uuid.uuid4().hex[:10]}", trace_id=trace_id, action_type=action_type,
            subject_type=subject_type, subject_id=subject_id, field=field_name, before_value=before_value, after_value=after_value,
        )
        self._store.set(action.action_id, asdict(action))
        return action

    def list_for_trace(self, trace_id: str) -> list[CompensatingAction]:
        items = [CompensatingAction(**d) for d in self._store.list(lambda d: d["trace_id"] == trace_id)]
        return sorted(items, key=lambda a: a.created_at)

    def mark_rolled_back(self, action_id: str) -> None:
        self._store.update(action_id, {"rolled_back": True})


rollback_ledger = RollbackLedger()


def rollback_trace(trace_id: str) -> list[dict[str, Any]]:
    """Replay every not-yet-rolled-back compensating action for a trace,
    most recent first, restoring each subject's field to its pre-action
    value. Returns a summary of what was reverted."""
    from bulwark.platform.models import vendor_repo
    from bulwark.agents.remediation_router import _tickets

    results: list[dict[str, Any]] = []
    for action in reversed(rollback_ledger.list_for_trace(trace_id)):
        if action.rolled_back:
            continue
        if action.subject_type == "vendor":
            vendor_repo.update(action.subject_id, **{action.field: action.before_value})
        elif action.subject_type == "ticket":
            _tickets.update(action.subject_id, {action.field: action.before_value})
        rollback_ledger.mark_rolled_back(action.action_id)
        results.append(
            {
                "action_id": action.action_id, "action_type": action.action_type, "subject_type": action.subject_type,
                "subject_id": action.subject_id, "field": action.field, "reverted_to": action.before_value,
            }
        )
    return results
