"""Remediation Router (`remediation-router`): turns a Finding into
action -- a ticket, a decision packet for a human, and (only after a
human decision already exists) a drafted vendor follow-up email.

The email step is the one place in this fleet with a hardcoded ceiling
below what the autonomy ladder alone would allow: even at global
autonomy_level 3, ``draft_vendor_email`` refuses to run unless the
Finding it's about already has a recorded ``human_decision``. There is
also, deliberately, no ``send_email`` function anywhere in this codebase
-- "never send autonomously" is enforced by the capability not existing,
not by a policy check that a future change could loosen.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import finding_repo
from bulwark.platform.observability import audit_log
from bulwark.platform.rollback import rollback_ledger
from bulwark.platform.store import DocumentStore

_tickets = DocumentStore("tickets")
_email_drafts = DocumentStore("vendor_email_drafts")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Ticket:
    ticket_id: str
    finding_id: str
    assignee: str
    summary: str
    trace_link: str
    status: str = "open"
    created_at: str = field(default_factory=_now)


def open_ticket(finding_id: str, assignee: str, summary: str) -> dict:
    """Open a tracking ticket (mock Jira/GitHub) for a finding, with a
    link back to its full reasoning-chain trace.

    Args:
        finding_id: The Finding this ticket addresses.
        assignee: Who it's assigned to.
        summary: A short, actionable ticket summary.
    """
    identity.require_grant("remediation-router", "tickets:write")
    policy.enforce_autonomy("remediation-router", 1)  # L1 Draft: appears in a queue, no external system touched for real

    finding = finding_repo.get(finding_id)
    ticket = Ticket(
        ticket_id=f"tix_{uuid.uuid4().hex[:8]}",
        finding_id=finding_id,
        assignee=assignee,
        summary=summary,
        trace_link=f"/traces/{finding.trace_id}" if finding else "",
    )
    _tickets.set(ticket.ticket_id, asdict(ticket))
    trace_id = finding.trace_id if finding else None
    if trace_id:
        rollback_ledger.record(
            trace_id=trace_id, action_type="open_ticket", subject_type="ticket", subject_id=ticket.ticket_id,
            field_name="status", before_value="not_opened", after_value="open",
        )
    audit_log.record(
        agent_name="remediation-router", event="ticket_opened",
        detail=f"ticket={ticket.ticket_id} finding={finding_id} assignee={assignee}",
        trace_id=trace_id,
    )
    return {"ticket_id": ticket.ticket_id}


def build_decision_packet(finding_id: str) -> dict:
    """Assemble the decision packet a human reviewer needs to act on a
    finding in one read: the finding itself, its citations, the
    reasoning chain trace, a recommendation, and alternatives.

    Args:
        finding_id: The Finding to build a packet for.
        recommended_action: The action you recommend (e.g. "request corrected evidence within 14 days").
        alternatives: 2-3 other actions considered and why they were not the top pick.
    """
    identity.require_grant("remediation-router", "tickets:write")
    policy.enforce_autonomy("remediation-router", 1)

    finding = finding_repo.get(finding_id)
    if finding is None:
        return {"error": f"unknown finding_id: {finding_id}"}
    return {
        "finding_id": finding.finding_id,
        "vendor_id": finding.vendor_id,
        "control_ref": finding.control_ref,
        "status": finding.status,
        "gap_description": finding.gap_description,
        "residual_risk": finding.residual_risk,
        "evidence_ids": finding.evidence_ids,
        "assertion_ids": finding.assertion_ids,
        "trace_link": f"/traces/{finding.trace_id}",
    }


def draft_vendor_email(finding_id: str, recipient_email: str, subject: str, body: str) -> dict:
    """Draft (never send) a follow-up email to a vendor about a finding.
    Requires the finding to already carry a recorded human_decision --
    this function will refuse to run otherwise, regardless of the global
    autonomy dial. There is no corresponding send function in this
    codebase; a human sends the draft through their own email client.

    Args:
        finding_id: The Finding this email is about. Must already have a human_decision recorded.
        recipient_email: The vendor contact's email address.
        subject: Email subject line.
        body: Email body.
    """
    identity.require_grant("remediation-router", "email:draft")
    policy.enforce_autonomy("remediation-router", 2)  # L2: this is the "act toward the outside world" step

    finding = finding_repo.get(finding_id)
    if finding is None:
        return {"error": f"unknown finding_id: {finding_id}"}
    if finding.human_decision is None:
        audit_log.record(
            agent_name="remediation-router", event="vendor_email_blocked_no_human_decision",
            detail=f"finding={finding_id}: refused to draft, no human_decision recorded", trace_id=finding.trace_id,
        )
        return {
            "error": "human_decision_required",
            "reason": "this finding has no recorded human_decision yet; record one before drafting outbound email",
        }

    draft_id = f"draft_{uuid.uuid4().hex[:8]}"
    _email_drafts.set(
        draft_id,
        {
            "draft_id": draft_id,
            "finding_id": finding_id,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "status": "drafted_pending_manual_send",
            "created_at": _now(),
        },
    )
    audit_log.record(
        agent_name="remediation-router", event="vendor_email_drafted",
        detail=f"draft={draft_id} finding={finding_id} recipient={recipient_email}", trace_id=finding.trace_id,
    )
    return {"draft_id": draft_id, "status": "drafted_pending_manual_send"}


remediation_router_agent = LlmAgent(
    name="remediation_router_agent",
    model=settings.gemini_flash_model,
    description="Opens tickets, builds decision packets, and (only after a human decision exists) drafts vendor email.",
    instruction=(
        "You are the Remediation Router for a third-party risk fleet. Given a "
        "finding_id for a finding with status \"gap\", call `open_ticket` to assign it "
        "for follow-up, and `build_decision_packet` to prepare what a human reviewer "
        "needs. If (and only if) you are told a human has already recorded a decision on "
        "this finding and asks you to follow up with the vendor, call "
        "`draft_vendor_email` with a professional, specific email citing the control gap "
        "-- if that call returns a human_decision_required error, tell the caller "
        "clearly that a human decision must be recorded first and stop."
    ),
    tools=[FunctionTool(open_ticket), FunctionTool(build_decision_packet), FunctionTool(draft_vendor_email)],
)
