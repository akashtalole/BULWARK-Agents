"""Executive Risk Digest Agent (`executive-digest`): the one agent whose
entire job is talking *to a human*, not acting on their behalf.

The problem this solves: this fleet exposes 30+ API endpoints -- findings,
concentration risks, framework coverage, offboarding deadlines, risk
trends -- and a genuinely thorough executive would have to click through
most of them to answer "what actually needs my attention this week."
Nobody does that every week, so the things that matter most (a
critical-tier vendor with an unreviewed gap finding, a concentration
cluster that just appeared, a data-deletion deadline about to be missed)
sit unread in a dashboard until something goes wrong. This agent does
the clicking-through for them: `gather_digest_inputs` pulls the same data
every other endpoint already exposes (nothing new is computed here, only
aggregated), and Gemini turns it into a short, prioritized narrative a
human can read in under a minute.

Split follows the same shape as Risk Assessor and Drift Sentinel:
gathering the facts is deterministic (`gather_digest_inputs`), and the
one place an LLM earns its cost is turning a pile of structured facts
into a prioritized, readable narrative -- genuine synthesis, not a
template fill.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import (
    Digest,
    concentration_risk_repo,
    digest_repo,
    finding_repo,
    fleet_config_repo,
    offboarding_record_repo,
    vendor_repo,
)
from bulwark.platform.observability import audit_log
from bulwark.platform.policy import AUTONOMY_LEVELS


def _vendor_name(vendor_id: str) -> str:
    """Findings/OffboardingRecords only carry `vendor_id` -- resolve it
    to the vendor's actual name here so the digest's narrative (and its
    `inputs` JSON, which the UI's "grounding inputs" panel renders
    verbatim) reads "Cloudy SaaS Inc", not "vendor_1f8395599f"."""
    vendor = vendor_repo.get(vendor_id)
    return vendor.name if vendor else vendor_id


def gather_digest_inputs() -> dict:
    """Pull the "needs a human's attention" slice of the fleet's current
    state -- deliberately not the full `/metrics` dashboard, which is
    built for completeness; this is built for triage. Every field here
    is already computed and exposed elsewhere (findings, concentration
    risks, offboarding records, the kill switch) -- this just puts them
    in one place."""
    identity.require_grant("executive-digest", "findings:read")
    identity.require_grant("executive-digest", "vendors:read")
    identity.require_grant("executive-digest", "concentration_risks:read")
    identity.require_grant("executive-digest", "offboarding_records:read")
    policy.enforce_autonomy("executive-digest", 3)

    tenant = settings.default_tenant
    vendors = vendor_repo.list(tenant)
    all_findings = finding_repo.list(tenant)

    critical_vendor_gaps = sorted(
        (
            f for f in all_findings
            if f.status == "gap" and f.requires_human
            and (v := vendor_repo.get(f.vendor_id)) and v.tier == "critical"
        ),
        key=lambda f: f.residual_risk, reverse=True,
    )[:5]
    top_gap_findings = sorted((f for f in all_findings if f.status == "gap"), key=lambda f: f.residual_risk, reverse=True)[:5]
    concentration_risks = concentration_risk_repo.list(tenant)[:5]
    offboarding_overdue = offboarding_record_repo.list_overdue(tenant)

    blind_windows = [d for v in vendors if (d := vendor_repo.blind_window_days(v)) is not None]
    blind_window_avg_days = round(sum(blind_windows) / len(blind_windows), 1) if blind_windows else None

    config = fleet_config_repo.get()

    return {
        "vendor_count": len(vendors),
        "blind_window_avg_days": blind_window_avg_days,
        "fleet_autonomy_level": f"L{config.autonomy_level} ({AUTONOMY_LEVELS[config.autonomy_level]})",
        "paused_agents": config.paused_agents,
        "critical_vendor_gap_findings": [
            {
                "vendor_id": f.vendor_id,
                "vendor_name": _vendor_name(f.vendor_id),
                "control_ref": f.control_ref,
                "residual_risk": f.residual_risk,
                "gap_description": f.gap_description,
            }
            for f in critical_vendor_gaps
        ],
        "top_gap_findings": [
            {
                "vendor_id": f.vendor_id,
                "vendor_name": _vendor_name(f.vendor_id),
                "control_ref": f.control_ref,
                "residual_risk": f.residual_risk,
            }
            for f in top_gap_findings
        ],
        "concentration_risks": [
            {"subprocessor_name": r.subprocessor_name, "vendor_count": len(r.vendor_ids), "severity": r.severity}
            for r in concentration_risks
        ],
        "offboarding_overdue": [
            {"vendor_id": r.vendor_id, "vendor_name": _vendor_name(r.vendor_id), "deadline": r.deadline, "reason": r.reason}
            for r in offboarding_overdue
        ],
    }


def publish_digest(narrative: str, highlights: list[str], trace_id: str) -> dict:
    """Persist the digest Gemini wrote, grounded in the exact inputs it
    saw -- so "what did the digest say" has a real, replayable answer
    later, not just whatever the model would say if asked again today.

    Args:
        narrative: The full digest text, a few short paragraphs.
        highlights: 3-6 short bullet strings, the "read this first" list.
        trace_id: Correlation id for this generation.
    """
    identity.require_grant("executive-digest", "digests:write")
    policy.enforce_autonomy("executive-digest", 1)  # L1 Draft: produces a document, sends nothing

    digest = digest_repo.create(
        Digest(
            digest_id=f"digest_{trace_id[-8:]}",
            tenant=settings.default_tenant,
            trace_id=trace_id,
            narrative=narrative,
            highlights=highlights,
            inputs=gather_digest_inputs(),
        )
    )
    audit_log.record(
        agent_name="executive-digest", event="digest_published",
        detail=f"digest_id={digest.digest_id} highlights={len(highlights)}", trace_id=trace_id,
    )
    return {"digest_id": digest.digest_id}


executive_digest_agent = LlmAgent(
    name="executive_digest_agent",
    model=settings.gemini_flash_model,
    description="Turns the fleet's current findings, concentration risks, and offboarding state into a short executive-readable narrative.",
    instruction=(
        "You are the Executive Risk Digest for a third-party risk fleet. Call "
        "`gather_digest_inputs` once. Refer to vendors by their `vendor_name`, never by "
        "`vendor_id` -- an executive reading this has no idea what 'vendor_1f8395599f' is. "
        "Write a short digest (3-5 short paragraphs, no "
        "headers) a busy executive can read in under a minute: lead with whatever is "
        "most urgent (critical-tier vendors with unreviewed gap findings, overdue "
        "offboarding data-deletion deadlines, and newly-detected concentration risks are "
        "all more urgent than routine metrics), then briefly note the fleet's overall "
        "posture (vendor count, average blind window, whether the fleet is currently at "
        "full autonomy or paused). Do not invent numbers or vendors not present in the "
        "input -- if a section has nothing to report, say so briefly rather than padding "
        "it. Then call `publish_digest` once with the narrative and a `highlights` list "
        "of 3-6 short bullet strings (the same points, compressed to one line each) for "
        "a UI to render as a quick-scan list, passing along the trace_id you were given."
    ),
    tools=[FunctionTool(gather_digest_inputs), FunctionTool(publish_digest)],
)
