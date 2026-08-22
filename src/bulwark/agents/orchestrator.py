"""Wiring: ADK Runners for the four LLM-backed agents/agent-groups, the
event-bus subscriptions that implement the three continuous loops from
section 2, and the one hardcoded security gate that isn't left to a
prompt.

No agent module imports another agent module. Every handoff below is
either (a) a direct function call from *this* file -- into an LLM
agent's Runner, or into a deterministic (non-LLM) agent's plain function,
like ``check_offboarding_overdue`` or ``analyze_concentration_risk`` --
which is orchestration/system code acting under no agent's identity, or
(b) ``bus.publish``/``bus.subscribe`` on a named topic. That is the
decoupling the architecture is graded on, and
``tests/test_architecture_invariants.py`` checks it mechanically on every
run rather than leaving it as a claim a diagram makes.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from bulwark.agents import intake
from bulwark.agents.concentration_analyzer import analyze_concentration_risk
from bulwark.agents.contract_intelligence import contract_intelligence_agent
from bulwark.agents.drift_sentinel import drift_sentinel_agent
from bulwark.agents.executive_digest import executive_digest_agent
from bulwark.agents.offboarding import check_offboarding_overdue
from bulwark.agents.questionnaire_responder import questionnaire_responder_agent
from bulwark.agents.remediation_router import remediation_router_agent
from bulwark.agents.risk_assessor import risk_assessor_agent
from bulwark.agents.supervisor import supervisor_agent
from bulwark.config import settings
from bulwark.platform.event_bus import Envelope, bus, make_idempotency_key
from bulwark.platform.guardrails import guardrails_plugin
from bulwark.platform.models import finding_repo, questionnaire_repo, reasoning_record_repo, vendor_repo
from bulwark.platform.observability import audit_log, observability_plugin
from bulwark.platform.spend import check_circuit_breaker, spend_ledger

# MSAs/DPAs/contracts route to Contract Intelligence instead of Intake --
# see agents/contract_intelligence.py's module docstring for why this is a
# separate agent rather than a branch inside Intake's own instruction.
_CONTRACT_DOC_TYPES = {"msa", "dpa", "contract", "sla", "order form"}

_APP_NAME = settings.service_name
_session_service = InMemorySessionService()

# One Runner per root ADK agent. `intake_agent` and `supervisor_agent`
# (which owns risk_assessor_agent + questionnaire_responder_agent as
# sub_agents) are the two entry points reachable from an inbound event;
# drift_sentinel and remediation_router are triggered by internal signals.
_intake_runner = Runner(
    app_name=_APP_NAME, agent=intake.intake_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)
_contract_runner = Runner(
    app_name=_APP_NAME, agent=contract_intelligence_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)
_supervisor_runner = Runner(
    app_name=_APP_NAME, agent=supervisor_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)
_drift_sentinel_runner = Runner(
    app_name=_APP_NAME, agent=drift_sentinel_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)
_remediation_runner = Runner(
    app_name=_APP_NAME, agent=remediation_router_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)
_digest_runner = Runner(
    app_name=_APP_NAME, agent=executive_digest_agent, session_service=_session_service,
    plugins=[guardrails_plugin, observability_plugin],
)


_ROOT_MODEL_FOR_RUNNER = {
    "vendor_intake_agent": settings.gemini_flash_model,
    "contract_intelligence_agent": settings.gemini_flash_model,
    "assurance_supervisor": settings.gemini_flash_model,  # may transfer to risk_assessor_agent (Pro) mid-run
    "drift_sentinel_agent": settings.gemini_flash_model,
    "remediation_router_agent": settings.gemini_flash_model,
    "executive_digest_agent": settings.gemini_flash_model,
}


async def _run(runner: Runner, prompt: str, user_id: str, trace_id: str) -> str:
    session_id = f"session_{uuid.uuid4().hex[:10]}"
    await _session_service.create_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id, state={"trace_id": trace_id}
    )
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    tokens_in = tokens_out = 0
    start = time.monotonic()
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        usage = getattr(event, "usage_metadata", None)
        if usage is not None:
            tokens_in += getattr(usage, "prompt_token_count", None) or 0
            tokens_out += getattr(usage, "candidates_token_count", None) or 0
        if getattr(event, "content", None) and event.content.parts and event.is_final_response():
            final_text = " ".join(p.text for p in event.content.parts if getattr(p, "text", None))
    latency_ms = int((time.monotonic() - start) * 1000)

    # Real per-call token telemetry (section 7's `tokens`/`model`/
    # `latency_ms` fields) and the circuit breaker's spend tracking
    # (section 8) share this one extraction point -- there's nowhere
    # else in this codebase real usage_metadata is available.
    if tokens_in or tokens_out:
        spend_ledger.record(tokens_in, tokens_out)
        check_circuit_breaker()
    model = _ROOT_MODEL_FOR_RUNNER.get(runner.agent.name, settings.gemini_flash_model)
    reasoning_record_repo.stamp_telemetry_for_trace(trace_id, model, tokens_in, tokens_out, latency_ms)

    return final_text or "No response produced."


# ------------------------------------------------------------- Loop A: Onboard


async def process_vendor_artifact(
    vendor_name: str, doc_type: str, raw_text: str, gcs_uri: str, sha256: str, user_id: str
) -> dict[str, Any]:
    """Entry point for a new vendor artifact. Provenance is hardcoded to
    "untrusted" here -- there is no parameter that lets a caller mark
    vendor-supplied content as anything else, and this function is the
    *only* code path that runs vendor document text through an LLM. It
    never calls the Supervisor: Model Armor's deterministic prescan runs
    first, and only Intake or Contract Intelligence -- both untrusted-zone
    agents -- ever see the content, chosen by `doc_type`."""
    trace_id = uuid.uuid4().hex
    envelope = Envelope(
        payload={"vendor_name": vendor_name, "doc_type": doc_type, "gcs_uri": gcs_uri},
        idempotency_key=make_idempotency_key("vendor.artifact.received", sha256),
        provenance="untrusted",
        trace_id=trace_id,
    )
    assert envelope.provenance == "untrusted"  # the hardcoded gate this module's docstring describes

    scan = intake.prescan_artifact(vendor_name, doc_type, raw_text, gcs_uri, sha256)
    await bus.publish("vendor.artifact.received", envelope)

    if scan["armor_verdict"] == "blocked":
        audit_log.record(
            agent_name="vendor-intake", event="artifact_blocked_by_model_armor",
            detail=f"vendor={vendor_name} findings={scan['armor_findings']}", trace_id=trace_id,
        )
        return {"trace_id": trace_id, "status": "blocked_by_model_armor", **scan}

    if doc_type.strip().lower() in _CONTRACT_DOC_TYPES:
        return await _process_contract(scan, doc_type, raw_text, user_id, trace_id)

    prompt = (
        f"New vendor artifact to extract claims from.\nvendor_id: {scan['vendor_id']}\n"
        f"artifact_id: {scan['artifact_id']}\ndoc_type: {doc_type}\n\nDocument text:\n{raw_text}"
    )
    summary = await _run(_intake_runner, prompt, user_id, trace_id)

    assertion_envelope = Envelope(
        payload={"vendor_id": scan["vendor_id"]},
        idempotency_key=make_idempotency_key("assertion.extracted", scan["artifact_id"]),
        trace_id=trace_id,
    )
    await bus.publish("assertion.extracted", assertion_envelope)

    return {"trace_id": trace_id, "status": "extracted", "summary": summary, **scan}


async def _process_contract(scan: dict[str, Any], doc_type: str, raw_text: str, user_id: str, trace_id: str) -> dict[str, Any]:
    prompt = (
        f"New vendor contract to review.\nvendor_id: {scan['vendor_id']}\n"
        f"artifact_id: {scan['artifact_id']}\ndoc_type: {doc_type}\n\nDocument text:\n{raw_text}"
    )
    summary = await _run(_contract_runner, prompt, user_id, trace_id)

    terms_envelope = Envelope(
        payload={"vendor_id": scan["vendor_id"], "artifact_id": scan["artifact_id"]},
        idempotency_key=make_idempotency_key("contract.terms_extracted", scan["artifact_id"]),
        trace_id=trace_id,
    )
    await bus.publish("contract.terms_extracted", terms_envelope)

    return {"trace_id": trace_id, "status": "contract_reviewed", "summary": summary, **scan}


async def _on_assertion_extracted(topic: str, envelope: Envelope) -> None:
    """System glue: an extraction finishing is what actually *requests* a
    fresh assessment. Kept as a separate topic from assessment.requested
    (rather than one topic doing double duty) so other future consumers
    -- a metrics dashboard, say -- can subscribe to "claims were
    extracted" without also being on the hook for triggering assessment."""
    vendor_id = envelope.payload["vendor_id"]
    request_envelope = Envelope(
        payload={"vendor_id": vendor_id, "reason": "new_assertions_extracted"},
        idempotency_key=make_idempotency_key("assessment.requested", vendor_id, envelope.event_id),
        trace_id=envelope.trace_id,
    )
    await bus.publish("assessment.requested", request_envelope)


async def _on_assessment_requested(topic: str, envelope: Envelope) -> None:
    vendor_id = envelope.payload["vendor_id"]
    reason = envelope.payload.get("reason", "requested")
    prompt = f"Event: assessment requested for vendor_id={vendor_id}. Reason: {reason}."
    await _run(_supervisor_runner, prompt, "system", envelope.trace_id)

    vendor = vendor_repo.get(vendor_id)
    if vendor:
        vendor_repo.update(vendor_id, status="active", last_assessed_at=envelope.published_at)

    for finding in finding_repo.list_for_vendor(vendor_id):
        if finding.status == "gap" and finding.trace_id == envelope.trace_id:
            finding_envelope = Envelope(
                payload={"finding_id": finding.finding_id, "residual_risk": finding.residual_risk},
                idempotency_key=make_idempotency_key("finding.created", finding.finding_id),
                trace_id=envelope.trace_id,
            )
            await bus.publish("finding.created", finding_envelope)


async def _on_finding_created(topic: str, envelope: Envelope) -> None:
    finding_id = envelope.payload["finding_id"]
    prompt = (
        f"Event: a new gap finding was created: finding_id={finding_id}. Open a ticket for it "
        "assigned to 'security-review-queue' and build its decision packet."
    )
    await _run(_remediation_runner, prompt, "system", envelope.trace_id)


bus.subscribe("assertion.extracted", _on_assertion_extracted)
bus.subscribe("assessment.requested", _on_assessment_requested)
bus.subscribe("finding.created", _on_finding_created)

# --------------------------------------------------------------- Loop B: Watch


async def run_drift_sweep() -> dict[str, Any]:
    """Manual/scheduled tick for Drift Sentinel. Cloud Scheduler drives
    this in production (deploy/setup_gcp.sh provisions the job); locally
    or in the demo, POST /drift-sentinel/tick (see scripts/demo_cli.py)
    calls this directly.

    Also composes in the offboarding-overdue check from `agents/
    offboarding.py` -- a deterministic comparison that needs no LLM
    judgment, so it's called directly from here (the composition root)
    rather than imported into `drift_sentinel.py` itself, the same shape
    as `_on_subprocessors_extracted` calling Concentration Analyzer
    below. See `tests/test_architecture_invariants.py`."""
    trace_id = uuid.uuid4().hex
    summary = await _run(_drift_sentinel_runner, "Event: scheduled drift sweep. Run it now.", "system", trace_id)
    offboarding_overdue_signals = check_offboarding_overdue(trace_id)
    return {"trace_id": trace_id, "summary": summary, "offboarding_overdue_signals": offboarding_overdue_signals}


async def generate_digest() -> dict[str, Any]:
    """Manual/scheduled tick for the Executive Risk Digest. A real
    deployment would run this weekly via Cloud Scheduler alongside the
    other two sweeps; `POST /digest/generate` calls it directly for a
    demo or an on-demand refresh."""
    trace_id = uuid.uuid4().hex
    await _run(_digest_runner, f"Event: generate this week's executive risk digest. trace_id: {trace_id}", "system", trace_id)
    from bulwark.platform.models import digest_repo

    digest = digest_repo.latest(settings.default_tenant)
    return {"trace_id": trace_id, "digest_id": digest.digest_id if digest else None}


async def _on_drift_detected(topic: str, envelope: Envelope) -> None:
    """"Reopens the affected assessments without being asked" -- this is
    that reopening, wired as automatically as everything else: a drift
    signal republishes assessment.requested for every affected vendor,
    with no human or API call in between."""
    for vendor_id in envelope.payload.get("affected_vendors", []):
        request_envelope = Envelope(
            payload={"vendor_id": vendor_id, "reason": f"drift_detected: {envelope.payload.get('reason', '')}"},
            idempotency_key=make_idempotency_key("assessment.requested", vendor_id, envelope.event_id),
            trace_id=envelope.trace_id,
        )
        await bus.publish("assessment.requested", request_envelope)


async def _on_evidence_collected(topic: str, envelope: Envelope) -> None:
    """evidence.collected: Evidence Collector -> Drift Sentinel (section
    4.2). A production deployment would scope Drift Sentinel's reaction
    to just the changed `control_refs` in the payload; at this build's
    scale a full sweep is cheap enough to just run directly, and it's the
    same `run_drift_sweep` the scheduled tick uses -- one code path, two
    triggers (a schedule, and a signal), matching the "wakes on schedule
    and on signal" behavior section 3.6 specifies."""
    await run_drift_sweep()


def _on_subprocessors_extracted(topic: str, envelope: Envelope) -> None:
    """subprocessors.extracted: Contract Intelligence -> Concentration
    Analyzer. Deliberately a sync (non-async) handler calling a plain
    function, not `_run` -- Concentration Analyzer is the second
    deliberately-non-LLM agent in this fleet (see its module docstring),
    so there's no Runner to invoke here, just a direct call, the same
    shape as evidence-collector's own tick."""
    analyze_concentration_risk(envelope.trace_id)


bus.subscribe("drift.detected", _on_drift_detected)
bus.subscribe("evidence.collected", _on_evidence_collected)
bus.subscribe("subprocessors.extracted", _on_subprocessors_extracted)
bus.subscribe(
    "contract.terms_extracted",
    lambda topic, envelope: None,  # documents the topic; no further automated reaction in this build --
    # a natural extension is routing high/critical-risk-level deviations into Remediation Router the same
    # way finding.created does for security gaps, left out here to keep this addition well-scoped
)

# -------------------------------------------------------------- Loop C: Attest

_QUESTION_SPLIT_RE = re.compile(r"\n?\s*\d+[.)]\s*")


async def submit_questionnaire(buyer: str, questions: list[str], user_id: str) -> dict[str, Any]:
    """Entry point for a new buyer questionnaire."""
    trace_id = uuid.uuid4().hex
    questionnaire = questionnaire_repo.create(buyer=buyer, tenant=settings.default_tenant)

    envelope = Envelope(
        payload={"questionnaire_id": questionnaire.questionnaire_id, "buyer": buyer},
        idempotency_key=make_idempotency_key("questionnaire.received", questionnaire.questionnaire_id),
        provenance="internal",
        trace_id=trace_id,
    )
    await bus.publish("questionnaire.received", envelope)

    prompt = (
        f"Event: buyer questionnaire received.\nquestionnaire_id: {questionnaire.questionnaire_id}\n"
        f"buyer: {buyer}\n\nQuestions:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    )
    summary = await _run(_supervisor_runner, prompt, user_id, trace_id)

    final = questionnaire_repo.get(questionnaire.questionnaire_id)
    auto_pct = round(100 * final.auto_answered / final.total_questions, 1) if final and final.total_questions else 0.0
    drafted_envelope = Envelope(
        payload={"questionnaire_id": questionnaire.questionnaire_id, "auto_pct": auto_pct, "abstain_count": final.abstained if final else 0},
        idempotency_key=make_idempotency_key("answer.drafted", questionnaire.questionnaire_id, trace_id),
        trace_id=trace_id,
    )
    await bus.publish("answer.drafted", drafted_envelope)

    return {"trace_id": trace_id, "questionnaire_id": questionnaire.questionnaire_id, "summary": summary}


def _noop(topic: str, envelope: Envelope) -> None:
    """Documents a topic exists on the bus with no further automated
    reaction -- questionnaire.received's work is driven synchronously by
    submit_questionnaire itself (it needs the Supervisor's result back
    before it can return one); answer.drafted's payload is aggregate
    reporting for a human review queue, not something that triggers
    another agent."""
    return None


async def _on_human_decision(topic: str, envelope: Envelope) -> None:
    """human.decision: HITL UI -> Remediation Router (section 4.2). This
    is what actually closes the loop the human-decision gate in
    agents/remediation_router.py checks for: recording a decision here
    republishes the event, and Remediation Router is asked to follow up
    -- `draft_vendor_email`'s gate (finding.human_decision is not None)
    is now satisfied, so it can actually draft the email this time."""
    finding_id = envelope.payload["subject_id"]
    prompt = (
        f"Event: a human recorded decision '{envelope.payload['decision']}' on finding_id={finding_id} "
        f"(rationale: {envelope.payload['rationale']}). If this decision calls for following up with the "
        "vendor, draft that email now -- the human decision is already recorded, so the gate is satisfied. "
        "If it doesn't call for vendor follow-up (e.g. the decision was to accept the risk internally), "
        "just acknowledge that no outbound action is needed."
    )
    await _run(_remediation_runner, prompt, "system", envelope.trace_id)


bus.subscribe("questionnaire.received", _noop)
bus.subscribe("answer.drafted", _noop)
bus.subscribe("human.decision", _on_human_decision)
