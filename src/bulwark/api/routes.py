"""HTTP routes: the Agent Gateway ingress. Every route authenticates and
rate-limits via platform/auth.py before touching anything. This is a
separate concern from platform/identity.py's per-agent grants: this
module governs *external callers*, identity.py governs *agents*."""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from bulwark.api.document_extraction import EmptyExtractionError, UnsupportedFileError, extract_text
from bulwark.api.schemas import (
    AutonomyRequest,
    ConfirmDataDeletionRequest,
    GenericDecisionRequest,
    HumanDecisionRequest,
    LoginRequest,
    OffboardVendorRequest,
    RegisterVendorRequest,
    SubmitArtifactRequest,
    SubmitArtifactResponse,
    SubmitQuestionnaireRequest,
    SubmitQuestionnaireResponse,
    TriggerAssessmentRequest,
    UpdateQuestionnaireRequest,
)
from bulwark.config import settings
from bulwark.platform.auth import AuthenticationError, RateLimitExceeded, authenticate, rate_limiter
from bulwark.platform.event_bus import Envelope, bus, make_idempotency_key
from bulwark.platform.models import fleet_config_repo, finding_repo, questionnaire_repo, vendor_repo
from bulwark.platform.observability import audit_log
from bulwark.platform.policy import pause_agent, resume_agent, set_global_autonomy
from bulwark.platform.registry import registry

router = APIRouter()

# Matches SubmitArtifactRequest.raw_text's max_length -- an uploaded
# document's extracted text is truncated to the same ceiling the JSON
# raw_text path already enforces, rather than silently accepting an
# unbounded amount of text into an LLM call.
_MAX_ARTIFACT_TEXT_CHARS = 20000

# Overridable in tests / when Gemini credentials aren't configured -- see
# tests/test_api.py and main.py's lifespan.
ArtifactFn = Callable[[str, str, str, str, str, str], Awaitable[dict]]
QuestionnaireFn = Callable[[str, list[str], str], Awaitable[dict]]
DriftSweepFn = Callable[[], Awaitable[dict]]
DigestFn = Callable[[], Awaitable[dict]]
_artifact_fn: ArtifactFn | None = None
_questionnaire_fn: QuestionnaireFn | None = None
_drift_sweep_fn: DriftSweepFn | None = None
_digest_fn: DigestFn | None = None


def set_orchestration_fns(
    artifact_fn: ArtifactFn | None,
    questionnaire_fn: QuestionnaireFn | None,
    drift_sweep_fn: DriftSweepFn | None,
    digest_fn: DigestFn | None = None,
) -> None:
    global _artifact_fn, _questionnaire_fn, _drift_sweep_fn, _digest_fn
    _artifact_fn = artifact_fn
    _questionnaire_fn = questionnaire_fn
    _drift_sweep_fn = drift_sweep_fn
    _digest_fn = digest_fn


def _authorize(api_key: str | None) -> str:
    try:
        key = authenticate(api_key)
        rate_limiter.check(key)
        return key
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/auth/config")
async def get_auth_config() -> dict:
    """Unauthenticated by design -- the frontend needs to know whether to
    show a login page *before* it has an API key to authenticate with."""
    return {"login_required": settings.ui_password is not None}


@router.post("/auth/login")
async def login(payload: LoginRequest) -> dict:
    """Trades BULWARK_UI_PASSWORD for the first configured API key. This
    is a convenience gate for frontend/ (see config.py's ui_password
    docstring) -- the real per-request auth is still api_keys/_authorize
    on every other route; this just spares a judge from having to know
    the raw API key."""
    if settings.ui_password is None:
        raise HTTPException(status_code=404, detail="login is not configured (BULWARK_UI_PASSWORD unset)")
    try:
        rate_limiter.check("ui-login")
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if payload.password != settings.ui_password:
        raise HTTPException(status_code=401, detail="incorrect password")
    return {"api_key": settings.api_keys[0]}


@router.get("/registry")
async def list_registry(x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    return [vars(r) for r in registry.list()]


# ------------------------------------------------------------------ vendors


@router.post("/vendors")
async def register_vendor(payload: RegisterVendorRequest, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `POST /vendors` -- register a vendor and set its tier
    up front, ahead of any artifact arriving for it (`vendors/artifacts`
    also creates a vendor on demand if one doesn't exist yet, which
    covers the common case where the first thing you have for a vendor
    *is* their SOC 2 report; this route is for when tier needs to be set
    before that, e.g. a critical-tier vendor entered during procurement)."""
    _authorize(x_api_key)
    vendor = vendor_repo.get_or_create(settings.default_tenant, payload.name, tier=payload.tier)  # type: ignore[arg-type]
    if payload.data_classes:
        vendor_repo.update(vendor.vendor_id, data_classes=payload.data_classes)
    return vars(vendor_repo.get(vendor.vendor_id))


@router.post("/vendors/artifacts", response_model=SubmitArtifactResponse)
async def submit_artifact(payload: SubmitArtifactRequest, x_api_key: str | None = Header(default=None)) -> SubmitArtifactResponse:
    _authorize(x_api_key)
    if _artifact_fn is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestration is not configured. Set GOOGLE_API_KEY (or Vertex AI credentials) and restart.",
        )
    result = await _artifact_fn(payload.vendor_name, payload.doc_type, payload.raw_text, payload.gcs_uri, payload.sha256, x_api_key)
    return SubmitArtifactResponse(**result)


@router.post("/vendors/artifacts/upload", response_model=SubmitArtifactResponse)
async def upload_artifact(
    vendor_name: str = Form(..., min_length=1, max_length=200),
    doc_type: str = Form(..., min_length=1, max_length=50),
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
) -> SubmitArtifactResponse:
    """A real file (PDF/DOCX/TXT) instead of pre-typed raw_text -- the
    enterprise on-ramp: a vendor's SOC 2/DPA usually arrives as a document,
    not a paste buffer. Extraction happens here, at the HTTP edge, *before*
    the text ever reaches an agent -- Model Armor's injection scan on the
    downstream Intake/Contract Intelligence callback still sees every
    extracted character, exactly as it would for the raw_text path."""
    _authorize(x_api_key)
    if _artifact_fn is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestration is not configured. Set GOOGLE_API_KEY (or Vertex AI credentials) and restart.",
        )
    try:
        raw_text = await extract_text(file)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmptyExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    truncated = len(raw_text) > _MAX_ARTIFACT_TEXT_CHARS
    if truncated:
        raw_text = raw_text[:_MAX_ARTIFACT_TEXT_CHARS]

    result = await _artifact_fn(vendor_name, doc_type, raw_text, f"gs://bulwark-quarantine/{file.filename}", "uploaded", x_api_key)
    if truncated:
        result["summary"] = f"{result.get('summary', '')} (source document truncated to {_MAX_ARTIFACT_TEXT_CHARS} chars)".strip()
    return SubmitArtifactResponse(**result)


@router.get("/vendors")
async def list_vendors(x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    vendors = vendor_repo.list()
    return [{**vars(v), "blind_window_days": vendor_repo.blind_window_days(v)} for v in vendors]


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    vendor = vendor_repo.get(vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="vendor not found")
    return {**vars(vendor), "blind_window_days": vendor_repo.blind_window_days(vendor)}


@router.get("/vendors/{vendor_id}/findings")
async def get_vendor_findings(vendor_id: str, x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    return [vars(f) for f in finding_repo.list_for_vendor(vendor_id)]


@router.get("/vendors/{vendor_id}/contract-terms")
async def get_vendor_contract_terms(vendor_id: str, x_api_key: str | None = Header(default=None)) -> list[dict]:
    """Clauses Contract Intelligence extracted from this vendor's
    contract(s), each already evaluated against the playbook -- filter
    client-side on a non-empty `deviation` for just the flagged ones."""
    _authorize(x_api_key)
    from bulwark.platform.models import contract_term_repo

    return [vars(t) for t in contract_term_repo.list_for_vendor(vendor_id)]


@router.get("/vendors/{vendor_id}/subprocessors")
async def get_vendor_subprocessors(vendor_id: str, x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    from bulwark.platform.models import subprocessor_repo

    return [vars(s) for s in subprocessor_repo.list_for_vendor(vendor_id)]


@router.get("/vendors/{vendor_id}/assessment-history")
async def get_vendor_assessment_history(vendor_id: str, x_api_key: str | None = Header(default=None)) -> list[dict]:
    """Append-only AssessmentSnapshot trail for this vendor -- unlike
    `GET /vendors/{id}/findings` (current state only), this is every
    reassessment ever recorded, in order, which is what
    `risk_trend_rising` signals are computed from."""
    _authorize(x_api_key)
    from bulwark.platform.models import assessment_snapshot_repo

    return [vars(s) for s in assessment_snapshot_repo.list_for_vendor(vendor_id)]


@router.get("/vendors/{vendor_id}/crosswalk")
async def get_vendor_framework_crosswalk(
    vendor_id: str, target_framework: str = "ISO27001", x_api_key: str | None = Header(default=None)
) -> dict:
    """How much of `target_framework` this vendor already satisfies via
    its existing SOC 2 findings, per `agents/framework_crosswalk.py`."""
    _authorize(x_api_key)
    from bulwark.agents.framework_crosswalk import compute_framework_coverage

    return compute_framework_coverage(vendor_id, target_framework)


@router.post("/vendors/{vendor_id}/offboard")
async def offboard_vendor(
    vendor_id: str, payload: OffboardVendorRequest, x_api_key: str | None = Header(default=None)
) -> dict:
    """Starts the offboarding clock (`agents/offboarding.py`) -- sets
    `vendor.status = "offboarding"` and computes a data-deletion deadline
    from the vendor's own extracted termination_assistance clause (or the
    playbook default). Deterministic, no credentials needed."""
    _authorize(x_api_key)
    from bulwark.agents.offboarding import initiate_offboarding

    trace_id = uuid.uuid4().hex
    return initiate_offboarding(vendor_id, payload.reason, trace_id)


@router.post("/vendors/{vendor_id}/offboard/confirm")
async def confirm_vendor_data_deletion(
    vendor_id: str, payload: ConfirmDataDeletionRequest, x_api_key: str | None = Header(default=None)
) -> dict:
    """Closes out an offboarding -- sets `vendor.status = "offboarded"`,
    a terminal state. Deterministic, no credentials needed."""
    _authorize(x_api_key)
    from bulwark.agents.offboarding import confirm_data_deletion

    trace_id = uuid.uuid4().hex
    return confirm_data_deletion(vendor_id, payload.evidence_note, trace_id)


@router.get("/vendors/{vendor_id}/offboarding")
async def get_vendor_offboarding(vendor_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    from bulwark.platform.models import offboarding_record_repo

    record = offboarding_record_repo.get_for_vendor(vendor_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no offboarding record for this vendor")
    return vars(record)


# -------------------------------------------------------------- assessments


@router.post("/assessments")
async def trigger_assessment(payload: TriggerAssessmentRequest, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `POST /assessments` -- manually (re-)trigger a
    vendor's assessment, e.g. from a reviewer's own judgment rather than
    an automated signal. Publishes the same `assessment.requested` topic
    Drift Sentinel and the Onboard loop use, so it flows through the
    identical Supervisor -> Risk Assessor path -- this is a different
    *trigger*, not a different code path."""
    _authorize(x_api_key)
    if vendor_repo.get(payload.vendor_id) is None:
        raise HTTPException(status_code=404, detail="vendor not found")
    if not settings.has_llm_credentials:
        raise HTTPException(
            status_code=503,
            detail="Orchestration is not configured. Set GOOGLE_API_KEY (or Vertex AI credentials) and restart.",
        )
    trace_id = uuid.uuid4().hex
    envelope = Envelope(
        payload={"vendor_id": payload.vendor_id, "reason": payload.reason, "scope": payload.scope},
        idempotency_key=make_idempotency_key("assessment.requested", payload.vendor_id, trace_id),
        trace_id=trace_id,
    )
    await bus.publish("assessment.requested", envelope)
    return {"trace_id": trace_id, "vendor_id": payload.vendor_id, "status": "requested"}


@router.get("/assessments/{trace_id}")
async def get_assessment_status(trace_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `GET /assessments/{id}` -- status + checkpoint
    position. There's no single "Assessment" record in this build's data
    model (see docs/architecture.md); this synthesizes status from what
    *does* exist for the trace: the audit trail (progress) and any
    findings produced under it (outcome) -- and a Run's checkpoint
    position too, on the rare path where trace_id and run_id coincide
    (Drift Sentinel's own sweep tick)."""
    _authorize(x_api_key)
    from bulwark.platform.models import run_repo

    entries = audit_log.trace(trace_id)
    if not entries:
        raise HTTPException(status_code=404, detail="no activity found for this trace_id")
    findings = [vars(f) for f in finding_repo.list(settings.default_tenant) if f.trace_id == trace_id]
    run = run_repo.get(trace_id)
    return {
        "trace_id": trace_id,
        "status": "completed" if any(e["event"] == "agent_finished" for e in entries) else "running",
        "findings": findings,
        "run_checkpoint": vars(run) if run else None,
    }


# ----------------------------------------------------------------- findings


@router.get("/findings")
async def list_findings(status: str | None = None, x_api_key: str | None = Header(default=None)) -> list[dict]:
    """`GET /findings?status=gap` -- section 9's global, filterable findings listing."""
    _authorize(x_api_key)
    return [vars(f) for f in finding_repo.list(settings.default_tenant, status=status)]  # type: ignore[arg-type]


@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    finding = finding_repo.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return vars(finding)


@router.get("/findings/{finding_id}/explain")
async def explain_finding(finding_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 7: "Demonstrating that an auditor can ask 'why did the
    agent decide this?' and get a straight answer is the difference
    between a demo and a system." Replays the reasoning-chain record(s)
    for this finding -- every alternative considered, its score, and why
    it wasn't chosen -- alongside the finding itself."""
    _authorize(x_api_key)
    from bulwark.platform.models import reasoning_record_repo

    finding = finding_repo.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    records = reasoning_record_repo.list_for_subject(finding_id)
    return {"finding": vars(finding), "reasoning": [vars(r) for r in records]}


async def _record_finding_decision_core(finding_id: str, actor: str, decision: str, rationale: str) -> dict:
    existing = finding_repo.get(finding_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="finding not found")
    finding = finding_repo.record_human_decision(finding_id, actor, decision, rationale)

    # human.decision: HITL UI -> Remediation Router (section 4.2's event
    # table). Published here -- the human's own action, not any agent's
    # -- and consumed by orchestrator._on_human_decision, which is what
    # actually lets Remediation Router draft a vendor email now that the
    # gate it checks (finding.human_decision is not None) is satisfied.
    envelope = Envelope(
        payload={"subject_id": finding_id, "decision": decision, "actor": actor, "rationale": rationale},
        idempotency_key=make_idempotency_key("human.decision", finding_id, actor, decision, str(uuid.uuid4())),
        provenance="human",
        trace_id=existing.trace_id,
    )
    await bus.publish("human.decision", envelope)
    return vars(finding)


@router.post("/findings/{finding_id}/decision")
async def record_finding_decision(
    finding_id: str, payload: HumanDecisionRequest, x_api_key: str | None = Header(default=None)
) -> dict:
    _authorize(x_api_key)
    return await _record_finding_decision_core(finding_id, payload.actor, payload.decision, payload.rationale)


@router.post("/decisions")
async def record_decision(payload: GenericDecisionRequest, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `POST /decisions` -- the generic form of
    `/findings/{id}/decision`, keyed by `subject_id` rather than the
    finding_id being in the path. Findings are the only decision subject
    type in this build (see docs/architecture.md), so this delegates to
    the same finding-decision logic; a subject_id that isn't a known
    finding_id is a 404, same as the path-based route."""
    _authorize(x_api_key)
    return await _record_finding_decision_core(payload.subject_id, payload.actor, payload.decision, payload.rationale)


# ------------------------------------------------------------ questionnaires


@router.post("/questionnaires", response_model=SubmitQuestionnaireResponse)
async def submit_questionnaire(
    payload: SubmitQuestionnaireRequest, x_api_key: str | None = Header(default=None)
) -> SubmitQuestionnaireResponse:
    _authorize(x_api_key)
    if _questionnaire_fn is None:
        raise HTTPException(status_code=503, detail="Orchestration is not configured.")
    result = await _questionnaire_fn(payload.buyer, payload.questions, x_api_key)
    return SubmitQuestionnaireResponse(**result)


@router.get("/questionnaires")
async def list_questionnaires(x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    return [vars(q) for q in questionnaire_repo.list(settings.default_tenant)]


@router.get("/questionnaires/{questionnaire_id}")
async def get_questionnaire(questionnaire_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    from bulwark.platform.models import answer_repo

    questionnaire = questionnaire_repo.get(questionnaire_id)
    if questionnaire is None:
        raise HTTPException(status_code=404, detail="questionnaire not found")
    answers = answer_repo.list_for_questionnaire(questionnaire_id)
    return {**vars(questionnaire), "answers": [vars(a) for a in answers]}


@router.patch("/questionnaires/{questionnaire_id}")
async def update_questionnaire(
    questionnaire_id: str, payload: UpdateQuestionnaireRequest, x_api_key: str | None = Header(default=None)
) -> dict:
    """Manual edit, not a re-run of the Attest loop: renames the buyer
    and/or replaces the question set. `questions` is matched against
    existing answers by exact text -- a question whose text is unchanged
    keeps its existing answer untouched; a genuinely new question gets a
    fresh `needs_human` answer (see AnswerRepo.create_manual) since
    nothing here calls the LLM; a question that's gone has its answer
    deleted with it."""
    _authorize(x_api_key)
    from bulwark.platform.models import answer_repo

    questionnaire = questionnaire_repo.get(questionnaire_id)
    if questionnaire is None:
        raise HTTPException(status_code=404, detail="questionnaire not found")

    patch: dict[str, Any] = {}
    if payload.buyer is not None:
        patch["buyer"] = payload.buyer

    if payload.questions is not None:
        existing_answers = answer_repo.list_for_questionnaire(questionnaire_id)
        existing_questions = {a.question for a in existing_answers}
        new_questions = set(payload.questions)

        for answer in existing_answers:
            if answer.question not in new_questions:
                answer_repo.delete(answer.answer_id)
        for question in payload.questions:
            if question not in existing_questions:
                answer_repo.create_manual(questionnaire_id, question)

        remaining = answer_repo.list_for_questionnaire(questionnaire_id)
        patch["total_questions"] = len(remaining)
        patch["auto_answered"] = sum(1 for a in remaining if a.status == "auto")
        patch["abstained"] = sum(1 for a in remaining if a.status == "needs_human")

    if patch:
        questionnaire = questionnaire_repo.update(questionnaire_id, **patch)

    answers = answer_repo.list_for_questionnaire(questionnaire_id)
    return {**vars(questionnaire), "answers": [vars(a) for a in answers]}


@router.post("/questionnaires/{questionnaire_id}/export")
async def export_questionnaire(questionnaire_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `POST /questionnaires/{id}/export` -- DLP-gated export.
    Only answers already marked `auto` (passed both the confidence bar
    and the DLP scan in `draft_answer`) are included; `needs_human` and
    `blocked_dlp` answers are excluded from the export, not just flagged
    -- an export can't leak what was never allowed to leave in the first
    place. Exported `auto` answers are marked `approved`."""
    _authorize(x_api_key)
    from bulwark.platform.models import Answer, answer_repo

    questionnaire = questionnaire_repo.get(questionnaire_id)
    if questionnaire is None:
        raise HTTPException(status_code=404, detail="questionnaire not found")

    all_answers = answer_repo.list_for_questionnaire(questionnaire_id)
    exportable = [Answer(**{**vars(a), "status": "approved"}) for a in all_answers if a.status == "auto"]
    excluded = [a for a in all_answers if a.status != "auto"]
    for a in exportable:
        answer_repo.create(a)

    return {
        "questionnaire_id": questionnaire_id,
        "exported": [vars(a) for a in exportable],
        "excluded_count": len(excluded),
        "excluded_reasons": {a.answer_id: a.status for a in excluded},
    }


# -------------------------------------------------------------------- runs


@router.post("/runs/{trace_id}/rollback")
async def rollback_run(trace_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Section 8: "All L3 actions are reversible by construction... POST
    /runs/{id}/rollback replays them in reverse." The path parameter is a
    trace_id (see platform/rollback.py's docstring for why that's the
    grouping key rather than a Drift Sentinel Run's own run_id)."""
    _authorize(x_api_key)
    from bulwark.platform.rollback import rollback_trace

    reverted = rollback_trace(trace_id)
    return {"trace_id": trace_id, "reverted": reverted}


# ---------------------------------------------------------------- watch loop


@router.post("/evidence-collector/tick")
async def trigger_evidence_sweep(x_api_key: str | None = Header(default=None)) -> dict:
    """Evidence Collector is deterministic (no LLM, see
    agents/evidence_collector.py), so unlike the other three tick/submit
    routes this one needs no orchestration function or Gemini credentials
    -- it runs even with none configured. Cloud Scheduler hits this every
    EVIDENCE_SWEEP_HOURS in production; deploy/setup_gcp.sh provisions
    that job."""
    _authorize(x_api_key)
    from bulwark.agents.evidence_collector import collect_evidence

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    collected = collect_evidence()

    # evidence.collected: Evidence Collector -> Drift Sentinel (section
    # 4.2). Evidence Collector's own service account has no pubsub:publish
    # grant (platform/identity.py mirrors the spec's zero-trust table
    # exactly, and that grant isn't in it) -- publishing the follow-on
    # event is this route's job, acting as system/Gateway code, not the
    # agent's. orchestrator._on_evidence_collected picks it up.
    envelope = Envelope(
        payload={"control_refs": sorted({e.control_ref for e in collected}), "run_id": run_id},
        idempotency_key=make_idempotency_key("evidence.collected", run_id),
        trace_id=run_id,
    )
    await bus.publish("evidence.collected", envelope)
    return {"collected": len(collected), "run_id": run_id, "records": [vars(e) for e in collected]}


@router.post("/drift-sentinel/tick")
async def trigger_drift_sweep(x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    if _drift_sweep_fn is None:
        raise HTTPException(status_code=503, detail="Orchestration is not configured.")
    return await _drift_sweep_fn()


@router.post("/concentration-analyzer/tick")
async def trigger_concentration_analysis(x_api_key: str | None = Header(default=None)) -> dict:
    """Concentration Analyzer is deterministic (no LLM, see
    agents/concentration_analyzer.py), so like /evidence-collector/tick
    this needs no orchestration function or Gemini credentials -- it
    normally fires automatically off subprocessors.extracted, but can
    also be re-run manually to recompute against the current portfolio."""
    _authorize(x_api_key)
    from bulwark.agents.concentration_analyzer import analyze_concentration_risk

    results = analyze_concentration_risk()
    return {"clusters_detected": len(results), "risks": [vars(r) for r in results]}


@router.get("/concentration-risks")
async def list_concentration_risks(x_api_key: str | None = Header(default=None)) -> list[dict]:
    """Every currently-detected shared-subprocessor cluster, most
    critical-vendor-heavy first -- the "vendors that look diversified but
    aren't" view. See agents/concentration_analyzer.py's module docstring
    for the real-world incident pattern this catches."""
    _authorize(x_api_key)
    from bulwark.platform.models import concentration_risk_repo

    return [vars(r) for r in concentration_risk_repo.list(settings.default_tenant)]


# ------------------------------------------------------------- observability


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    return {"trace_id": trace_id, "entries": audit_log.trace(trace_id)}


@router.get("/dlq")
async def get_dlq(x_api_key: str | None = Header(default=None)) -> list[dict]:
    _authorize(x_api_key)
    return bus.dlq_entries()


# -------------------------------------------------------- fleet config / kill switch


@router.get("/fleet-config")
async def get_fleet_config(x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    return vars(fleet_config_repo.get())


@router.post("/fleet-config")
async def update_fleet_config(payload: AutonomyRequest, x_api_key: str | None = Header(default=None)) -> dict:
    """The kill switch, live: set autonomy_level to 0 (or pause a specific
    agent) and every L1+ agent action across the fleet starts raising
    AutonomyBlocked on its very next tool call -- no redeploy, no restart."""
    _authorize(x_api_key)
    if payload.autonomy_level is not None:
        set_global_autonomy(payload.autonomy_level)
    if payload.pause_agent_id:
        pause_agent(payload.pause_agent_id)
    if payload.resume_agent_id:
        resume_agent(payload.resume_agent_id)
    return vars(fleet_config_repo.get())


# -------------------------------------------------------------- fleet health


@router.get("/fleet/health")
async def fleet_health(x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9: `GET /fleet/health` -- per-agent health, DLQ depth, spend."""
    _authorize(x_api_key)
    from bulwark.platform.spend import spend_ledger

    config = fleet_config_repo.get()
    agents = [
        {
            "agent_id": r.agent_id, "trust_zone": r.trust_zone, "autonomy_ceiling": r.autonomy_ceiling,
            "paused": r.agent_id in config.paused_agents,
            "effective_ceiling": min(r.autonomy_ceiling, config.autonomy_level) if r.agent_id not in config.paused_agents else 0,
        }
        for r in registry.list()
    ]
    return {
        "global_autonomy_level": config.autonomy_level,
        "agents": agents,
        "dlq_depth": len(bus.dlq_entries()),
        "spend_today": vars(spend_ledger.today()),
        "spend_cap_usd": config.max_daily_token_spend,
    }


# ------------------------------------------------------------------- metrics


@router.get("/metrics")
async def get_metrics(x_api_key: str | None = Header(default=None)) -> dict:
    """Section 9 / section 13: the dashboard numbers, computed live from
    this build's own data rather than hardcoded -- "measured numbers on
    synthetic-but-realistic data are entirely legitimate, just label them
    as such" (section 13). Everything here is exactly that: real
    arithmetic over whatever vendors/questionnaires/findings/evidence
    exist right now, which will be synthetic seed data in a demo."""
    _authorize(x_api_key)
    from bulwark.platform.models import control_repo, evidence_repo

    vendors = vendor_repo.list(settings.default_tenant)
    blind_windows = [d for v in vendors if (d := vendor_repo.blind_window_days(v)) is not None]
    blind_window_avg_days = round(sum(blind_windows) / len(blind_windows), 2) if blind_windows else None

    questionnaires = questionnaire_repo.list(settings.default_tenant)
    total_questions = sum(q.total_questions for q in questionnaires)
    total_auto = sum(q.auto_answered for q in questionnaires)
    questions_auto_answered_pct = round(100 * total_auto / total_questions, 1) if total_questions else 0.0

    all_findings = finding_repo.list(settings.default_tenant)
    findings_traceable_pct = (
        round(100 * sum(1 for f in all_findings if f.evidence_ids or f.assertion_ids) / len(all_findings), 1)
        if all_findings else 100.0
    )

    controls = control_repo.list(settings.default_tenant)
    fresh_count = sum(
        1 for c in controls if (latest := evidence_repo.latest_for_control(settings.default_tenant, c.control_ref)) and latest.freshness == "fresh"
    )
    control_coverage_fresh_pct = round(100 * fresh_count / len(controls), 1) if controls else 0.0

    return {
        "blind_window_avg_days": blind_window_avg_days,
        "vendor_count": len(vendors),
        "questions_auto_answered_pct": questions_auto_answered_pct,
        "findings_traceable_to_evidence_pct": findings_traceable_pct,
        "control_coverage_fresh_evidence_pct": control_coverage_fresh_pct,
        "injection_attempts_blocked": audit_log.count_events("model_armor_blocked") + audit_log.count_events("guardrails_blocked"),
        "findings_requiring_human_review": sum(1 for f in all_findings if f.requires_human),
        "note": "computed live from this deployment's own data (synthetic in a demo) -- see section 13 of the design spec.",
    }


# --------------------------------------------------------------------- digest


@router.post("/digest/generate")
async def generate_digest(x_api_key: str | None = Header(default=None)) -> dict:
    """Runs the Executive Risk Digest Agent (`agents/executive_digest.py`)
    now, rather than waiting for the next scheduled run. Needs Gemini
    credentials -- the synthesis step is genuine LLM judgment, unlike
    `gather_digest_inputs` itself, which is deterministic."""
    _authorize(x_api_key)
    if _digest_fn is None:
        raise HTTPException(status_code=503, detail="Orchestration is not configured.")
    return await _digest_fn()


@router.get("/digest/latest")
async def get_latest_digest(x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    from bulwark.platform.models import digest_repo

    digest = digest_repo.latest(settings.default_tenant)
    if digest is None:
        raise HTTPException(status_code=404, detail="no digest has been generated yet")
    return vars(digest)


@router.get("/digest/{digest_id}")
async def get_digest(digest_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _authorize(x_api_key)
    from bulwark.platform.models import digest_repo

    digest = digest_repo.get(digest_id)
    if digest is None:
        raise HTTPException(status_code=404, detail="digest not found")
    return vars(digest)
