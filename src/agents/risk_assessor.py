"""Risk Assessor (`risk-assessor`): the only agent on Gemini Pro, reserved
for the one step that's genuinely complex final reasoning -- cross-
referencing what a vendor *claims* (Assertions) against what your control
framework *requires* (ControlRequirement) and what's independently
*observed* (Evidence), and forming a residual-risk judgment.

The anti-hallucination boundary here is deterministic code, not a prompt
instruction: ``create_finding`` refuses to persist a finding that doesn't
cite at least one real evidence_id or assertion_id, and validates that
every cited id actually exists before writing anything. An LLM that tries
to fabricate a finding with no citations, or with a citation to an id that
doesn't exist, gets a rejection back as the tool result -- it never
reaches storage.
"""

from __future__ import annotations

import hashlib

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import (
    Finding,
    ReasoningRecord,
    assertion_repo,
    assessment_snapshot_repo,
    control_repo,
    evidence_repo,
    finding_repo,
    reasoning_record_repo,
    vendor_repo,
)
from bulwark.platform.observability import audit_log


def get_assessment_context(vendor_id: str) -> dict:
    """Fetch everything needed to assess a vendor: its Assertions, the
    tenant's ControlRequirements, and the latest Evidence for each of
    those controls (with freshness already computed).

    Args:
        vendor_id: The vendor to assess.

    Returns:
        `{vendor, assertions, controls, evidence_by_control}` -- ground
        every finding you draft in this data; do not cite an id that
        isn't present here.
    """
    vendor = vendor_repo.get(vendor_id)
    if vendor is None:
        return {"error": f"unknown vendor_id: {vendor_id}"}
    assertions = assertion_repo.list_for_vendor(vendor_id)
    controls = control_repo.list(vendor.tenant)
    evidence_by_control = {
        c.control_ref: [
            {
                "evidence_id": e.evidence_id,
                "observed_value": e.observed_value,
                "expected_value": e.expected_value,
                "satisfied": e.satisfied,
                "freshness": e.freshness,
            }
            for e in evidence_repo.list_for_control(vendor.tenant, c.control_ref)
        ]
        for c in controls
    }
    return {
        "vendor": {"vendor_id": vendor.vendor_id, "name": vendor.name, "tier": vendor.tier},
        "assertions": [
            {
                "assertion_id": a.assertion_id,
                "control_ref": a.control_ref,
                "claim": a.claim,
                "confidence": a.confidence,
            }
            for a in assertions
        ],
        "controls": [{"control_ref": c.control_ref, "title": c.title, "criticality": c.criticality} for c in controls],
        "evidence_by_control": evidence_by_control,
    }


def create_finding(
    vendor_id: str,
    control_ref: str,
    status: str,
    gap_description: str,
    residual_risk: int,
    evidence_ids: list[str],
    assertion_ids: list[str],
    trace_id: str,
    considered: list[dict],
) -> dict:
    """Persist a Finding -- REJECTED unless it cites at least one real
    evidence_id or assertion_id from `get_assessment_context`. A finding
    that would be "satisfied" on stale evidence is downgraded to
    "unknown" and flagged for human review instead -- evidence going
    stale can never silently keep a control looking green.

    Args:
        vendor_id: The vendor this finding is about.
        control_ref: The control this finding evaluates.
        status: One of "satisfied", "gap", "exception", "unknown".
        gap_description: Empty if satisfied; otherwise what's missing and why.
        residual_risk: 1-25 (severity x likelihood).
        evidence_ids: evidence_id values from get_assessment_context that support this finding.
        assertion_ids: assertion_id values from get_assessment_context that support this finding.
        trace_id: The trace_id you were given for this assessment run.
        considered: The alternative statuses you weighed before this one, each a dict
            with `option`, `score` (0.0-1.0), `why_not` (omit on the one you chose),
            and `chosen: true` on exactly one entry -- this is the reasoning-chain
            record a human (or an auditor) can later replay via GET /findings/{id}/explain.

    Returns:
        The finding_id on success, or an `error` explaining the citation
        rejection -- fix the citations and call this again.
    """
    identity.require_grant("risk-assessor", "findings:write")
    identity.require_grant("risk-assessor", "assessment_snapshots:write")
    policy.enforce_autonomy("risk-assessor", 1)  # L1 Draft: a finding is a draft until a human reviews it

    if not evidence_ids and not assertion_ids:
        audit_log.record(
            agent_name="risk-assessor",
            event="finding_rejected_missing_citations",
            detail=f"vendor={vendor_id} control={control_ref}: no evidence_ids or assertion_ids supplied",
            trace_id=trace_id,
        )
        return {"error": "citation_validation_failed", "reason": "at least one evidence_id or assertion_id is required"}

    vendor = vendor_repo.get(vendor_id)
    known_assertions = {a.assertion_id: a for a in assertion_repo.list_for_vendor(vendor_id)}
    known_evidence = {e.evidence_id: e for e in evidence_repo.list(vendor.tenant)} if vendor else {}
    unknown = [i for i in evidence_ids if i not in known_evidence] + [
        i for i in assertion_ids if i not in known_assertions
    ]
    if unknown:
        audit_log.record(
            agent_name="risk-assessor",
            event="finding_rejected_unknown_citations",
            detail=f"vendor={vendor_id} control={control_ref}: unrecognized ids {unknown}",
            trace_id=trace_id,
        )
        return {"error": "citation_validation_failed", "reason": f"unrecognized citation ids: {unknown}"}

    # Fail-closed rule (section 10 / section 6.4's third mandatory gate):
    # never let a control read "satisfied" on stale evidence.
    requires_human = False
    cited_evidence = [known_evidence[i] for i in evidence_ids]
    if any(e.freshness == "stale" for e in cited_evidence) and status == "satisfied":
        audit_log.record(
            agent_name="risk-assessor",
            event="finding_downgraded_stale_evidence",
            detail=f"vendor={vendor_id} control={control_ref}: cited evidence is stale, status forced satisfied->unknown",
            trace_id=trace_id,
        )
        status = "unknown"
        requires_human = True

    # Section 6.4's other two mandatory gates: critical-tier vendor, and
    # residual risk above threshold. Neither changes `status` -- unlike
    # the stale-evidence rule, there's nothing factually wrong with the
    # assessment itself, it's just consequential enough that a human must
    # sign off before it's treated as resolved.
    mandatory, reason = policy.requires_mandatory_human_review(
        vendor_tier=vendor.tier if vendor else "moderate", residual_risk=residual_risk
    )
    if mandatory:
        requires_human = True
        audit_log.record(
            agent_name="risk-assessor", event="finding_flagged_for_mandatory_review",
            detail=f"vendor={vendor_id} control={control_ref}: {reason}", trace_id=trace_id,
        )

    finding = finding_repo.create(
        Finding(
            finding_id=f"find_{vendor_id[-6:]}_{control_ref.replace('.', '')}",
            tenant=settings.default_tenant,
            vendor_id=vendor_id,
            control_ref=control_ref,
            status=status,  # type: ignore[arg-type]
            gap_description=gap_description,
            residual_risk=residual_risk,
            evidence_ids=evidence_ids,
            assertion_ids=assertion_ids,
            trace_id=trace_id,
            requires_human=requires_human,
        )
    )
    assessment_snapshot_repo.record(
        settings.default_tenant, vendor_id, control_ref, finding.status, residual_risk, finding.finding_id, trace_id
    )

    inputs_hash = hashlib.sha256(
        f"{control_ref}|{sorted(evidence_ids)}|{sorted(assertion_ids)}".encode()
    ).hexdigest()
    reasoning_record_repo.create(
        ReasoningRecord(
            decision_id=f"dec_{finding.finding_id}",
            subject_id=finding.finding_id,
            trace_id=trace_id,
            agent="risk-assessor",
            inputs_hash=inputs_hash,
            considered=considered,
            evidence_ids=evidence_ids,
            assertion_ids=assertion_ids,
            model=settings.gemini_pro_model,
        )
    )

    return {"finding_id": finding.finding_id, "status": status, "requires_human": requires_human}


risk_assessor_agent = LlmAgent(
    name="risk_assessor_agent",
    model=settings.gemini_pro_model,
    description="Cross-references Assertions + Evidence + ControlRequirements into cited, risk-scored Findings.",
    instruction=(
        "You are the Risk Assessor for a third-party risk fleet, and you're the only "
        "agent on the more capable model -- use it for genuine judgment, not a rubber "
        "stamp. Given a vendor_id, call `get_assessment_context` first. For each control "
        "in the result, decide its status: \"satisfied\" if evidence or a credible "
        "assertion supports it, \"gap\" if nothing supports it or the evidence "
        "contradicts it, \"exception\" only if you're told a negotiated exception "
        "applies, \"unknown\" if there's simply no data either way. Score residual_risk "
        "1-25 (roughly: control criticality x how stale/contradicted the evidence is). "
        "Then call `create_finding` once per control, citing the exact evidence_id(s) "
        "and/or assertion_id(s) from the context that justify your call -- never a "
        "finding with zero citations, and never an id you didn't see in the context. "
        "Also pass `considered`: the 2-3 statuses you weighed (e.g. satisfied, gap, "
        "escalate) each with a 0.0-1.0 score, a `why_not` on every one you didn't pick, "
        "and `chosen: true` on the one you did -- this is what lets a human replay your "
        "reasoning later. If `create_finding` returns an error, fix the citations and "
        "retry. If it downgrades your status because the cited evidence was stale, "
        "accept that -- do not retry with different evidence to force 'satisfied'."
    ),
    tools=[FunctionTool(get_assessment_context), FunctionTool(create_finding)],
)
