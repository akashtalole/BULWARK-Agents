"""Drift Sentinel (`drift-sentinel`): the agent that makes this
"continuous" rather than "batch" -- the long-running, checkpointed,
weeks-of-state component the Fortified Enterprise Fleet track explicitly
asks for.

Signal *detection* is deterministic (``run_drift_sweep``): artifact
expiry, evidence drift, a mock breach feed -- predictively, a
control's residual risk rising for three consecutive reassessments
(``AssessmentSnapshot``'s append-only history is what makes that
possible; ``Finding`` alone only ever shows current state, never the
trajectory), and an overdue offboarding data-deletion deadline
(``agents/offboarding.py``) are all plain comparisons, not reasoning. What needs an LLM
is *judgment* -- given several raw signals across a vendor, how severe is
this really, does an active negotiated exception in Memory Bank already
cover it, and what's the one-paragraph "why this matters" a human
reviewer should see. That split (deterministic facts in, LLM synthesis
out) is the same shape used by Risk Assessor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.agents.offboarding import check_offboarding_overdue
from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.event_bus import Envelope, bus, make_idempotency_key
from bulwark.platform.memory_bank import memory_bank
from bulwark.platform.models import artifact_repo, assessment_snapshot_repo, control_repo, evidence_repo, run_repo, vendor_repo
from bulwark.platform.observability import audit_log
from bulwark.platform.rollback import rollback_ledger

# Mock public breach/incident disclosure feed, in the same spirit as
# internal_sources.py -- a real deployment polls an actual feed here.
_MOCK_BREACH_FEED: dict[str, str] = {}


def run_drift_sweep(trace_id: str) -> dict:
    """Deterministically scan for drift signals across every vendor:
    artifacts expiring within 30 days, evidence that no longer matches
    its expected value (and isn't covered by an active Memory Bank
    exception), and breach-feed hits. Checkpoints progress via the Run
    ledger so a crash mid-sweep resumes rather than restarting.

    Returns:
        `{run_id, signals}` -- one dict per detected signal, each with
        vendor_id, signal_type, detail, and severity, ready for
        `reopen_assessment` to act on.
    """
    identity.require_grant("drift-sentinel", "assessments:read")
    identity.require_grant("drift-sentinel", "assessment_snapshots:read")
    policy.enforce_autonomy("drift-sentinel", 3)

    steps = ["check_expiry", "check_evidence_drift", "check_breach_feed", "check_risk_trend", "check_offboarding_overdue"]
    run = run_repo.start("drift-sentinel", steps)
    signals: list[dict] = []

    expiring = artifact_repo.list_expiring_within(settings.default_tenant, days=30)
    for artifact in expiring:
        vendor = vendor_repo.get(artifact.vendor_id)
        signals.append(
            {
                "vendor_id": artifact.vendor_id,
                "signal_type": "expiry_approaching",
                "detail": f"{artifact.doc_type} for {vendor.name if vendor else artifact.vendor_id} expires {artifact.valid_until}",
                "severity": "medium",
            }
        )
    run_repo.checkpoint(run.run_id, "check_expiry")

    for vendor in vendor_repo.list(settings.default_tenant):
        for control in control_repo.list(settings.default_tenant):
            latest = evidence_repo.latest_for_control(settings.default_tenant, control.control_ref)
            if latest is None or latest.satisfied:
                continue
            if memory_bank.has_active_exception(vendor.vendor_id, control.control_ref):
                continue
            signals.append(
                {
                    "vendor_id": vendor.vendor_id,
                    "signal_type": "control_drift",
                    "detail": (
                        f"{control.control_ref} observed='{latest.observed_value}' "
                        f"expected='{latest.expected_value}' freshness={latest.freshness}"
                    ),
                    "severity": "high" if control.criticality in ("high", "critical") else "medium",
                }
            )
    run_repo.checkpoint(run.run_id, "check_evidence_drift")

    for vendor in vendor_repo.list(settings.default_tenant):
        if vendor.name in _MOCK_BREACH_FEED:
            signals.append(
                {
                    "vendor_id": vendor.vendor_id,
                    "signal_type": "breach_disclosure",
                    "detail": _MOCK_BREACH_FEED[vendor.name],
                    "severity": "critical",
                }
            )
    run_repo.checkpoint(run.run_id, "check_breach_feed")

    # Predictive early-warning: Finding is overwritten in place on every
    # reassessment, so on its own it can never show a *trajectory* --
    # only AssessmentSnapshot's append-only history can. Three
    # consecutive strictly-rising residual_risk scores on the same
    # control is worth a human's attention even if no single one of
    # those assessments individually crossed the gap threshold, the
    # same way a rising fever is worth noticing before it's a crisis.
    for vendor in vendor_repo.list(settings.default_tenant):
        for control in control_repo.list(settings.default_tenant):
            snapshots = assessment_snapshot_repo.list_for_vendor_control(vendor.vendor_id, control.control_ref)
            if len(snapshots) < 3:
                continue
            if memory_bank.has_active_exception(vendor.vendor_id, control.control_ref):
                continue
            r1, r2, r3 = (s.residual_risk for s in snapshots[-3:])
            if r1 < r2 < r3:
                signals.append(
                    {
                        "vendor_id": vendor.vendor_id,
                        "signal_type": "risk_trend_rising",
                        "detail": (
                            f"{control.control_ref} residual risk rising across the last 3 assessments: "
                            f"{r1} -> {r2} -> {r3}, before any single one crossed a hard threshold"
                        ),
                        "severity": "high" if r3 >= 15 else "medium",
                    }
                )
    run_repo.checkpoint(run.run_id, "check_risk_trend")

    # A vendor still holding your data past the deadline their own DPA's
    # termination_assistance clause set is a live compliance exposure,
    # not a hypothetical one -- see agents/offboarding.py's module
    # docstring for why this obligation is otherwise almost never tracked.
    signals.extend(check_offboarding_overdue(trace_id))
    run_repo.checkpoint(run.run_id, "check_offboarding_overdue")

    run_repo.complete(run.run_id)
    audit_log.record(
        agent_name="drift-sentinel", event="drift_sweep_completed",
        detail=f"run_id={run.run_id} signals_found={len(signals)}", trace_id=trace_id,
    )
    return {"run_id": run.run_id, "signals": signals}


async def reopen_assessment(vendor_id: str, reason: str, severity: str, trace_id: str) -> dict:
    """Reopen a vendor's assessment because Drift Sentinel judged a
    signal (or combination of signals) worth a human's attention. Fully
    reversible -- it only changes vendor status and emits an event -- which
    is why this is authorized at L3 (autonomous) rather than requiring a
    human decision first.

    A vendor already `"offboarding"` or `"offboarded"` is left alone --
    code-enforced, not left to the model's judgment: re-running a normal
    assessment cycle on a vendor that's already leaving makes no sense,
    and silently flipping their status back to `"under_review"` would
    corrupt the offboarding record's own state machine
    (`agents/offboarding.py`). The signal is still published for
    visibility; only the status write is skipped.

    Args:
        vendor_id: The vendor whose assessment should reopen.
        reason: One-paragraph explanation of why, for the human reviewer.
        severity: "low", "medium", "high", or "critical".
        trace_id: The trace_id for this sweep.
    """
    identity.require_grant("drift-sentinel", "assessments:write")
    identity.require_grant("drift-sentinel", "memory_bank:write")
    identity.require_grant("drift-sentinel", "pubsub:publish")
    policy.enforce_autonomy("drift-sentinel", 3)

    vendor = vendor_repo.get(vendor_id)
    previous_status = vendor.status if vendor else "onboarding"
    if previous_status not in ("offboarding", "offboarded"):
        vendor_repo.update(vendor_id, status="under_review")
        rollback_ledger.record(
            trace_id=trace_id, action_type="reopen_assessment", subject_type="vendor", subject_id=vendor_id,
            field_name="status", before_value=previous_status, after_value="under_review",
        )
        memory_bank.record_assessment(vendor_id)
    audit_log.record(
        agent_name="drift-sentinel", event="assessment_reopened",
        detail=f"vendor={vendor_id} severity={severity} reason={reason}", trace_id=trace_id,
    )

    envelope = Envelope(
        payload={"signal_type": "drift", "affected_vendors": [vendor_id], "severity": severity, "reason": reason},
        idempotency_key=make_idempotency_key("drift.detected", vendor_id, reason),
        provenance="internal",
        trace_id=trace_id,
    )
    await bus.publish("drift.detected", envelope)
    return {"vendor_id": vendor_id, "status": vendor_repo.get(vendor_id).status, "published": "drift.detected"}


drift_sentinel_agent = LlmAgent(
    name="drift_sentinel_agent",
    model=settings.gemini_flash_model,
    description="Judges drift signals for severity and reopens the assessments that actually warrant it.",
    instruction=(
        "You are Drift Sentinel for a third-party risk fleet. Call `run_drift_sweep` "
        "once to get the raw signals detected this sweep. Group signals by vendor_id. "
        "For each vendor with at least one signal, decide the overall severity (use the "
        "single highest severity among that vendor's signals, or escalate one level if "
        "there are multiple independent signals) and write a one-paragraph reason a "
        "human reviewer can act on immediately without re-deriving it themselves. Then "
        "call `reopen_assessment` once per affected vendor with that reason and "
        "severity, passing along the trace_id you were given. If there are no signals "
        "for a vendor, do not call reopen_assessment for it. Exception: for a vendor "
        "whose only signal is `offboarding_overdue`, do not call `reopen_assessment` -- "
        "that vendor isn't due for a normal reassessment, it's overdue on a data-deletion "
        "obligation, which is a different problem the offboarding record already tracks; "
        "your job for that signal is done once you've included it in your summary."
    ),
    tools=[FunctionTool(run_drift_sweep), FunctionTool(reopen_assessment)],
)
