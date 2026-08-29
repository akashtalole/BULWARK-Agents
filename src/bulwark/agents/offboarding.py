"""Offboarding & Termination Assistance Agent (`offboarding-agent`):
deliberately deterministic, no LLM call -- same reasoning as Evidence
Collector, Concentration Analyzer, and Framework Crosswalk. Computing a
deadline from a playbook default (or a vendor's own contracted number,
once one exists) and comparing it to the current date is arithmetic, not
judgment.

The problem this solves: every vendor relationship ends eventually, and
every DPA this fleet reviews contains a `termination_assistance` clause
obligating the vendor to export your data and certify its deletion
within a fixed window. In practice that obligation is tracked in a
spreadsheet, if at all -- there's no system that actually watches the
clock and flags a vendor still holding your data past the date they were
contractually required to delete it, which is a real, auditable
data-retention and GDPR/CCPA exposure, not a hypothetical one. This
agent is what watches that clock: `initiate_offboarding` starts it (using
the vendor's own extracted playbook deadline, so `agents/contract_
intelligence.py`'s work and this agent's work compound rather than
duplicate), `confirm_data_deletion` stops it, and Drift Sentinel's fifth
signal (`offboarding_overdue`) is what actually surfaces a miss.

This also operationalizes `VendorStatus`'s `"offboarding"` value, which
existed in the type since the very first version of this schema but had
no code path that ever set or cleared it until now.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bulwark.agents.contract_playbook import termination_deadline_days
from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import (
    OffboardingRecord,
    contract_term_repo,
    offboarding_record_repo,
    vendor_repo,
)
from bulwark.platform.observability import audit_log
from bulwark.platform.rollback import rollback_ledger


_DAYS_PATTERN = re.compile(r"(\d+)[\s-]*day", re.IGNORECASE)


def _deadline_days_for(vendor_id: str) -> int:
    """Prefer the vendor's own extracted `termination_assistance` clause
    deadline if Contract Intelligence found one worth flagging as a
    deviation (e.g. "90-day window" where the playbook wants 30) --
    otherwise fall back to the playbook default. Deliberately
    conservative: this only overrides the default on a number that's
    actually adjacent to the word "day" (not just the first digits found
    anywhere in the sentence, which could just as easily be a dollar
    figure or a different clause's number entirely)."""
    default_days = termination_deadline_days()
    for term in contract_term_repo.list_for_vendor(vendor_id):
        if term.clause_type != "termination_assistance":
            continue
        match = _DAYS_PATTERN.search(term.deviation)
        if match:
            return int(match.group(1))
    return default_days


def initiate_offboarding(vendor_id: str, reason: str, trace_id: str) -> dict:
    """Start the offboarding clock for a vendor: sets `vendor.status =
    "offboarding"` and creates an `OffboardingRecord` with a deadline
    computed from the playbook (or the vendor's own contracted terms, if
    more specific). Fully reversible -- a compensating-action record is
    written the same way `reopen_assessment` writes one -- which is what
    justifies doing this at L3 without a human confirming first; nothing
    is deleted or sent to the vendor by this call itself.

    Args:
        vendor_id: The vendor whose relationship is ending.
        reason: Why (e.g. "contract not renewed", "replaced by Vendor X").
        trace_id: Correlation id for this action.
    """
    identity.require_grant("offboarding-agent", "vendors:write")
    identity.require_grant("offboarding-agent", "offboarding_records:write")
    policy.enforce_autonomy("offboarding-agent", 3)

    vendor = vendor_repo.get(vendor_id)
    if vendor is None:
        return {"error": "vendor_not_found", "vendor_id": vendor_id}

    previous_status = vendor.status
    vendor_repo.update(vendor_id, status="offboarding")
    rollback_ledger.record(
        trace_id=trace_id, action_type="initiate_offboarding", subject_type="vendor",
        subject_id=vendor_id, field_name="status", before_value=previous_status, after_value="offboarding",
    )

    deadline = (datetime.now(timezone.utc) + timedelta(days=_deadline_days_for(vendor_id))).isoformat()
    record = offboarding_record_repo.create(
        OffboardingRecord(
            record_id=f"off_{vendor_id[-6:]}",
            tenant=settings.default_tenant,
            vendor_id=vendor_id,
            reason=reason,
            initiated_at=datetime.now(timezone.utc).isoformat(),
            deadline=deadline,
        )
    )
    audit_log.record(
        agent_name="offboarding-agent", event="offboarding_initiated",
        detail=f"vendor={vendor_id} reason={reason} deadline={deadline}", trace_id=trace_id,
        vendor_id=vendor_id,
    )
    return {"record_id": record.record_id, "vendor_id": vendor_id, "deadline": deadline}


def confirm_data_deletion(vendor_id: str, evidence_note: str, trace_id: str) -> dict:
    """Close out an offboarding: marks the `OffboardingRecord` confirmed
    and the vendor `"offboarded"` -- a terminal state, not reversible by
    this codebase, deliberately: confirming a real-world fact (the data
    is gone) isn't something rolling back a database field should ever
    pretend to undo.

    Args:
        vendor_id: The vendor whose data deletion is now certified.
        evidence_note: What was reviewed to confirm it (e.g. "vendor's
            deletion certificate received and matches DPA data scope").
        trace_id: Correlation id for this action.
    """
    identity.require_grant("offboarding-agent", "vendors:write")
    identity.require_grant("offboarding-agent", "offboarding_records:write")
    policy.enforce_autonomy("offboarding-agent", 2)  # L2: closes out a compliance obligation, not silently reversible

    record = offboarding_record_repo.get_for_vendor(vendor_id)
    if record is None or record.status == "confirmed":
        return {"error": "no_pending_offboarding_record", "vendor_id": vendor_id}

    offboarding_record_repo.confirm(record.record_id, evidence_note)
    vendor_repo.update(vendor_id, status="offboarded")
    audit_log.record(
        agent_name="offboarding-agent", event="data_deletion_confirmed",
        detail=f"vendor={vendor_id} evidence={evidence_note}", trace_id=trace_id,
        vendor_id=vendor_id,
    )
    return {"record_id": record.record_id, "vendor_id": vendor_id, "status": "confirmed"}


def check_offboarding_overdue(trace_id: str | None = None) -> list[dict]:
    """Deterministic detection Drift Sentinel's sweep calls: every
    OffboardingRecord past its deadline and still unconfirmed is a
    vendor that may still be holding data they were contractually
    required to delete -- a real compliance exposure, surfaced the same
    way every other drift signal is."""
    identity.require_grant("offboarding-agent", "offboarding_records:read")
    policy.enforce_autonomy("offboarding-agent", 3)

    signals = []
    for record in offboarding_record_repo.list_overdue(settings.default_tenant):
        vendor = vendor_repo.get(record.vendor_id)
        signals.append(
            {
                "vendor_id": record.vendor_id,
                "signal_type": "offboarding_overdue",
                "detail": (
                    f"{vendor.name if vendor else record.vendor_id} was due to certify data deletion "
                    f"by {record.deadline} (reason: {record.reason}) and hasn't -- a live data-retention exposure."
                ),
                "severity": "critical",
            }
        )
        audit_log.record(
            agent_name="offboarding-agent", event="offboarding_overdue_detected",
            detail=f"vendor={record.vendor_id} deadline={record.deadline}", trace_id=trace_id,
            vendor_id=record.vendor_id,
        )
    return signals
