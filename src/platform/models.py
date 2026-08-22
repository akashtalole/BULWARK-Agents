"""The control-evidence-assertion graph: BULWARK's core data model,
section 5 of the design doc. Each collection is a thin repository over a
DocumentStore (Firestore-backed, in-memory fallback).

The spec's true Firestore layout nests documents under
``/tenants/{tenant}/vendors/{vendor_id}/...``; this module flattens that
into top-level collections with ``tenant`` and ``vendor_id`` carried as
fields, which keeps both the in-memory and Firestore backends simple
while preserving every field the spec calls for. A production Firestore
deployment would add the composite indexes listed at the bottom of this
file's docstring reference in docs/architecture.md.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from bulwark.config import settings
from bulwark.platform.store import DocumentStore

# ------------------------------------------------------------------ utils


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ------------------------------------------------------------------ Tenant

TenantFramework = Literal["SOC2", "ISO27001"]


@dataclass
class Tenant:
    tenant: str
    region_pin: str
    framework: TenantFramework = "SOC2"


class TenantRepo:
    """Data sovereignty (section 6.3): a tenant's ``region_pin`` records
    which region its Vertex AI calls, Firestore location, and GCS buckets
    must resolve from. The spec is explicit that the real control here is
    an Organization Policy (``gcp.resourceLocations``) an auditor can
    verify independently -- not application code, which an auditor has to
    trust. This repo is the record of the commitment; ``region_pin`` on
    every request (see the event Envelope) is the app-level echo of it,
    not a substitute for the Org Policy binding a real deployment sets in
    Terraform/gcloud."""

    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("tenants")

    def upsert(self, tenant: Tenant) -> Tenant:
        self._store.set(tenant.tenant, asdict(tenant))
        return tenant

    def get(self, tenant: str) -> Tenant | None:
        data = self._store.get(tenant)
        return Tenant(**data) if data else None

    def get_or_default(self, tenant: str) -> Tenant:
        return self.get(tenant) or Tenant(tenant=tenant, region_pin="us-central1")

    def region_pin_matches(self, tenant: str, envelope_region_pin: str) -> bool:
        """Advisory app-level check that an event's region_pin agrees
        with its tenant's configured pin -- a signal to log/alert on, not
        the enforcement mechanism itself (that's the Org Policy binding,
        per section 6.3)."""
        return self.get_or_default(tenant).region_pin == envelope_region_pin


tenant_repo = TenantRepo()


# ------------------------------------------------------------------ Vendor

VendorStatus = Literal["onboarding", "active", "under_review", "offboarding", "offboarded"]
VendorTier = Literal["critical", "high", "moderate", "low"]


@dataclass
class Vendor:
    vendor_id: str
    tenant: str
    name: str
    tier: VendorTier
    data_classes: list[str] = field(default_factory=list)
    status: VendorStatus = "onboarding"
    last_assessed_at: str | None = None
    next_review_due: str | None = None


class VendorRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("vendors")

    def get_or_create(self, tenant: str, name: str, tier: VendorTier = "moderate") -> Vendor:
        existing = next((v for v in self._store.list(lambda d: d["tenant"] == tenant and d["name"] == name)), None)
        if existing:
            return Vendor(**existing)
        vendor = Vendor(vendor_id=_new_id("vendor"), tenant=tenant, name=name, tier=tier)
        self._store.set(vendor.vendor_id, asdict(vendor))
        return vendor

    def get(self, vendor_id: str) -> Vendor | None:
        data = self._store.get(vendor_id)
        return Vendor(**data) if data else None

    def list(self, tenant: str | None = None) -> list[Vendor]:
        return [Vendor(**d) for d in self._store.list(lambda d: tenant is None or d["tenant"] == tenant)]

    def update(self, vendor_id: str, **patch: Any) -> Vendor:
        data = self._store.update(vendor_id, patch)
        return Vendor(**data)

    def blind_window_days(self, vendor: Vendor) -> int | None:
        """Days since the last assessment -- the headline metric from section 1."""
        if not vendor.last_assessed_at:
            return None
        last = datetime.fromisoformat(vendor.last_assessed_at)
        return (datetime.now(timezone.utc) - last).days


vendor_repo = VendorRepo()

# ---------------------------------------------------------------- Artifact


@dataclass
class Artifact:
    artifact_id: str
    tenant: str
    vendor_id: str
    gcs_uri: str
    doc_type: str
    sha256: str
    armor_verdict: Literal["clean", "blocked"] = "clean"
    armor_findings: list[dict[str, Any]] = field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    created_at: str = field(default_factory=_now)


class ArtifactRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("artifacts")

    def create(self, artifact: Artifact) -> Artifact:
        self._store.set(artifact.artifact_id, asdict(artifact))
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        data = self._store.get(artifact_id)
        return Artifact(**data) if data else None

    def list_expiring_within(self, tenant: str, days: int) -> list[Artifact]:
        cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        return [
            Artifact(**d)
            for d in self._store.list(
                lambda x: x["tenant"] == tenant and x.get("valid_until") and x["valid_until"] <= cutoff
            )
        ]

    def list_for_vendor(self, vendor_id: str) -> list[Artifact]:
        return [Artifact(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]


artifact_repo = ArtifactRepo()

# --------------------------------------------------------------- Assertion


@dataclass
class Assertion:
    assertion_id: str
    tenant: str
    vendor_id: str
    control_ref: str
    claim: str
    source_artifact_id: str
    source_page: int | None
    confidence: float
    extracted_by_agent: str
    extracted_by_model: str
    created_at: str = field(default_factory=_now)


class AssertionRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("assertions")

    def create(self, assertion: Assertion) -> Assertion:
        self._store.set(assertion.assertion_id, asdict(assertion))
        return assertion

    def get(self, assertion_id: str) -> Assertion | None:
        data = self._store.get(assertion_id)
        return Assertion(**data) if data else None

    def list_for_vendor(self, vendor_id: str) -> list[Assertion]:
        return [Assertion(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]


assertion_repo = AssertionRepo()

# ---------------------------------------------------------- ControlRequirement


@dataclass
class ControlRequirement:
    control_ref: str
    tenant: str
    framework: str
    title: str
    requirement_text: str
    owner: str
    criticality: Literal["low", "medium", "high", "critical"] = "medium"


class ControlRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("controls")

    def upsert(self, control: ControlRequirement) -> ControlRequirement:
        self._store.set(f"{control.tenant}:{control.control_ref}", asdict(control))
        return control

    def get(self, tenant: str, control_ref: str) -> ControlRequirement | None:
        data = self._store.get(f"{tenant}:{control_ref}")
        return ControlRequirement(**data) if data else None

    def list(self, tenant: str) -> list[ControlRequirement]:
        return [ControlRequirement(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]


control_repo = ControlRepo()

# -------------------------------------------------------------------- Evidence


@dataclass
class Evidence:
    evidence_id: str
    tenant: str
    control_ref: str
    observed_value: str
    expected_value: str
    source: str
    collected_at: str
    content_hash: str

    @property
    def freshness(self) -> Literal["fresh", "stale"]:
        collected = datetime.fromisoformat(self.collected_at)
        age_days = (datetime.now(timezone.utc) - collected).days
        return "stale" if age_days > settings.evidence_freshness_days else "fresh"

    @property
    def satisfied(self) -> bool:
        return self.freshness == "fresh" and self.observed_value == self.expected_value


class EvidenceRepo:
    """Append-only, as the spec requires -- there is no update() here."""

    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("evidence")

    def create(self, evidence: Evidence) -> Evidence:
        self._store.set(evidence.evidence_id, asdict(evidence))
        return evidence

    def list_for_control(self, tenant: str, control_ref: str) -> list[Evidence]:
        items = [
            Evidence(**d) for d in self._store.list(lambda d: d["tenant"] == tenant and d["control_ref"] == control_ref)
        ]
        return sorted(items, key=lambda e: e.collected_at, reverse=True)

    def latest_for_control(self, tenant: str, control_ref: str) -> Evidence | None:
        items = self.list_for_control(tenant, control_ref)
        return items[0] if items else None

    def list(self, tenant: str) -> list[Evidence]:
        return [Evidence(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]


evidence_repo = EvidenceRepo()

# -------------------------------------------------------------------- Finding

FindingStatus = Literal["satisfied", "gap", "exception", "unknown"]


@dataclass
class Finding:
    finding_id: str
    tenant: str
    vendor_id: str
    control_ref: str
    status: FindingStatus
    gap_description: str
    residual_risk: int  # 1-25
    evidence_ids: list[str]
    assertion_ids: list[str]
    trace_id: str
    human_decision: dict[str, Any] | None = None
    # Section 10's fail-closed rule: a finding can never rest on stale
    # evidence claiming "satisfied" -- create_finding downgrades status to
    # "unknown" and sets this instead. Also set whenever section 6.4's
    # mandatory human-gate conditions apply (critical-tier vendor,
    # residual risk above threshold).
    requires_human: bool = False
    created_at: str = field(default_factory=_now)


class FindingRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("findings")

    def create(self, finding: Finding) -> Finding:
        self._store.set(finding.finding_id, asdict(finding))
        return finding

    def get(self, finding_id: str) -> Finding | None:
        data = self._store.get(finding_id)
        return Finding(**data) if data else None

    def list_for_vendor(self, vendor_id: str) -> list[Finding]:
        return [Finding(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]

    def list(self, tenant: str, status: FindingStatus | None = None) -> list[Finding]:
        return [
            Finding(**d)
            for d in self._store.list(lambda d: d["tenant"] == tenant and (status is None or d["status"] == status))
        ]

    def record_human_decision(self, finding_id: str, actor: str, decision: str, rationale: str) -> Finding:
        data = self._store.update(
            finding_id, {"human_decision": {"actor": actor, "decision": decision, "rationale": rationale, "at": _now()}}
        )
        return Finding(**data)


finding_repo = FindingRepo()

# ----------------------------------------------------------- AssessmentSnapshot


@dataclass
class AssessmentSnapshot:
    """Unlike Finding (keyed by vendor+control, overwritten in place on
    every reassessment) this is append-only: one immutable record per
    `create_finding` call. Without this, the fleet has no way to answer
    "is this vendor's risk on this control trending worse across
    reassessments" -- Finding alone only ever shows the current state,
    never the trajectory. `agents/drift_sentinel.py`'s risk_trend_rising
    signal is what this table exists to make possible."""

    snapshot_id: str
    tenant: str
    vendor_id: str
    control_ref: str
    status: str
    residual_risk: int
    finding_id: str
    trace_id: str
    created_at: str = field(default_factory=_now)


class AssessmentSnapshotRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("assessment_snapshots")

    def record(
        self, tenant: str, vendor_id: str, control_ref: str, status: str, residual_risk: int, finding_id: str, trace_id: str
    ) -> AssessmentSnapshot:
        snapshot = AssessmentSnapshot(
            snapshot_id=_new_id("snap"), tenant=tenant, vendor_id=vendor_id, control_ref=control_ref,
            status=status, residual_risk=residual_risk, finding_id=finding_id, trace_id=trace_id,
        )
        self._store.set(snapshot.snapshot_id, asdict(snapshot))
        return snapshot

    def list_for_vendor_control(self, vendor_id: str, control_ref: str) -> list[AssessmentSnapshot]:
        items = [
            AssessmentSnapshot(**d)
            for d in self._store.list(lambda d: d["vendor_id"] == vendor_id and d["control_ref"] == control_ref)
        ]
        return sorted(items, key=lambda s: s.created_at)

    def list_for_vendor(self, vendor_id: str) -> list[AssessmentSnapshot]:
        items = [AssessmentSnapshot(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]
        return sorted(items, key=lambda s: s.created_at)


assessment_snapshot_repo = AssessmentSnapshotRepo()

# ------------------------------------------------------------ ReasoningRecord


@dataclass
class ReasoningRecord:
    """Section 7's decision-record shape: not just *what* an agent
    decided (the Finding/Answer/etc. itself) but *why*, including the
    roads not taken. ``GET /findings/{id}/explain`` replays these."""

    decision_id: str
    subject_id: str  # the finding_id (or other decision subject) this record explains
    trace_id: str
    agent: str
    inputs_hash: str
    considered: list[dict[str, Any]]  # [{option, score, why_not?, chosen?}]
    evidence_ids: list[str]
    assertion_ids: list[str]
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    created_at: str = field(default_factory=_now)


class ReasoningRecordRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("reasoning_records")

    def create(self, record: ReasoningRecord) -> ReasoningRecord:
        self._store.set(record.decision_id, asdict(record))
        return record

    def list_for_subject(self, subject_id: str) -> list[ReasoningRecord]:
        items = [ReasoningRecord(**d) for d in self._store.list(lambda d: d["subject_id"] == subject_id)]
        return sorted(items, key=lambda r: r.created_at)

    def stamp_telemetry_for_trace(self, trace_id: str, model: str, tokens_in: int, tokens_out: int, latency_ms: int) -> None:
        """Real token/latency telemetry is only available from the ADK
        Runner's event stream (see agents/orchestrator.py's `_run`), not
        from inside the tool call that creates the record -- so records
        are created with zeroed telemetry and stamped here once the run
        that produced them finishes."""
        for data in self._store.list(lambda d: d["trace_id"] == trace_id):
            self._store.update(data["decision_id"], {"model": model, "tokens_in": tokens_in, "tokens_out": tokens_out, "latency_ms": latency_ms})


reasoning_record_repo = ReasoningRecordRepo()

# --------------------------------------------------------------- ContractTerm

ClauseRisk = Literal["low", "medium", "high", "critical"]


@dataclass
class ContractTerm:
    """One clause the Contract Intelligence Agent extracted from a
    vendor's MSA/DPA and evaluated against the tenant's playbook
    (agents/contract_playbook.py). Structurally the legal-risk analog of
    an Assertion + Finding rolled into one record: it's both the claim
    ("here is what the contract says") and the judgment ("here is how it
    compares to what we require"), because unlike a security control
    there's no separate "observed evidence" to cross-reference a contract
    clause against -- the text of the clause *is* the evidence."""

    term_id: str
    tenant: str
    vendor_id: str
    artifact_id: str
    clause_type: str  # e.g. "liability_cap", "breach_notification", "data_residency", "audit_rights"
    clause_text: str
    risk_level: ClauseRisk
    playbook_requirement: str
    deviation: str  # empty if the clause meets the playbook requirement
    source_page: int | None = None
    created_at: str = field(default_factory=_now)


class ContractTermRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("contract_terms")

    def create(self, term: ContractTerm) -> ContractTerm:
        self._store.set(term.term_id, asdict(term))
        return term

    def list_for_vendor(self, vendor_id: str) -> list[ContractTerm]:
        return [ContractTerm(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]


contract_term_repo = ContractTermRepo()

# --------------------------------------------------------------- Subprocessor


@dataclass
class Subprocessor:
    """One subprocessor a vendor's contract discloses -- the raw material
    for concentration-risk analysis (agents/concentration_analyzer.py).
    Deliberately its own collection rather than a field on ContractTerm:
    the same subprocessor name recurs across many vendors' contracts, and
    concentration analysis needs to query "which vendors share this
    subprocessor," not "what did this one contract say.\""""

    subprocessor_id: str
    tenant: str
    vendor_id: str
    artifact_id: str
    name: str
    purpose: str
    location: str
    created_at: str = field(default_factory=_now)


class SubprocessorRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("subprocessors")

    def create(self, subprocessor: Subprocessor) -> Subprocessor:
        self._store.set(subprocessor.subprocessor_id, asdict(subprocessor))
        return subprocessor

    def list_for_vendor(self, vendor_id: str) -> list[Subprocessor]:
        return [Subprocessor(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]

    def list(self, tenant: str) -> list[Subprocessor]:
        return [Subprocessor(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]


subprocessor_repo = SubprocessorRepo()

# ----------------------------------------------------------- ConcentrationRisk


@dataclass
class ConcentrationRisk:
    """One detected cluster: a single subprocessor (by normalized name)
    that enough of the tenant's vendors depend on that its failure would
    be a correlated, not independent, event -- the blind spot a
    per-vendor review can never catch, because each individual review
    looks fine in isolation."""

    risk_id: str
    tenant: str
    subprocessor_name: str
    vendor_ids: list[str]
    critical_vendor_count: int
    severity: ClauseRisk
    detail: str
    detected_at: str = field(default_factory=_now)


class ConcentrationRiskRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("concentration_risks")

    def create(self, risk: ConcentrationRisk) -> ConcentrationRisk:
        self._store.set(risk.risk_id, asdict(risk))
        return risk

    def list(self, tenant: str) -> list[ConcentrationRisk]:
        items = [ConcentrationRisk(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]
        return sorted(items, key=lambda r: r.critical_vendor_count, reverse=True)

    def clear_all(self, tenant: str) -> None:
        """Called before each analysis run so a subprocessor that drops
        below the concentration threshold (e.g. a vendor was offboarded)
        doesn't leave a stale risk record behind forever -- results
        always reflect current portfolio state, not an accumulating log."""
        for d in self._store.list(lambda d: d["tenant"] == tenant):
            self._store.delete(d["risk_id"])


concentration_risk_repo = ConcentrationRiskRepo()

# --------------------------------------------------------------- Offboarding

OffboardingStatus = Literal["pending", "confirmed"]


@dataclass
class OffboardingRecord:
    """Tracks the one obligation every vendor relationship ends with but
    that's almost always tracked in a spreadsheet, if at all: certifying
    data deletion within the contractual deadline. `deadline` is computed
    from the vendor's own `termination_assistance` ContractTerm when one
    exists, falling back to the playbook default -- this is what lets
    ``agents/offboarding.py``'s Drift Sentinel signal flag a vendor still
    holding your data past the date they were contractually required to
    delete it."""

    record_id: str
    tenant: str
    vendor_id: str
    reason: str
    initiated_at: str
    deadline: str
    status: OffboardingStatus = "pending"
    confirmed_at: str | None = None
    evidence_note: str | None = None


class OffboardingRecordRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("offboarding_records")

    def create(self, record: OffboardingRecord) -> OffboardingRecord:
        self._store.set(record.record_id, asdict(record))
        return record

    def get_for_vendor(self, vendor_id: str) -> OffboardingRecord | None:
        items = [OffboardingRecord(**d) for d in self._store.list(lambda d: d["vendor_id"] == vendor_id)]
        return max(items, key=lambda r: r.initiated_at) if items else None

    def confirm(self, record_id: str, evidence_note: str) -> OffboardingRecord:
        data = self._store.update(record_id, {"status": "confirmed", "confirmed_at": _now(), "evidence_note": evidence_note})
        return OffboardingRecord(**data)

    def list_overdue(self, tenant: str) -> list[OffboardingRecord]:
        now = _now()
        items = [
            OffboardingRecord(**d)
            for d in self._store.list(lambda d: d["tenant"] == tenant and d["status"] == "pending" and d["deadline"] < now)
        ]
        return items


offboarding_record_repo = OffboardingRecordRepo()

# --------------------------------------------------------------- Questionnaire


@dataclass
class Questionnaire:
    questionnaire_id: str
    tenant: str
    buyer: str
    received_at: str
    deadline: str | None
    total_questions: int = 0
    auto_answered: int = 0
    abstained: int = 0
    status: Literal["processing", "ready_for_review", "completed"] = "processing"


class QuestionnaireRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("questionnaires")

    def create(self, buyer: str, tenant: str, deadline: str | None = None) -> Questionnaire:
        q = Questionnaire(questionnaire_id=_new_id("quest"), tenant=tenant, buyer=buyer, received_at=_now(), deadline=deadline)
        self._store.set(q.questionnaire_id, asdict(q))
        return q

    def get(self, questionnaire_id: str) -> Questionnaire | None:
        data = self._store.get(questionnaire_id)
        return Questionnaire(**data) if data else None

    def update(self, questionnaire_id: str, **patch: Any) -> Questionnaire:
        return Questionnaire(**self._store.update(questionnaire_id, patch))

    def list(self, tenant: str) -> list[Questionnaire]:
        return [Questionnaire(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]


questionnaire_repo = QuestionnaireRepo()


@dataclass
class Answer:
    answer_id: str
    questionnaire_id: str
    question: str
    answer: str
    confidence: float
    citations: list[str]
    status: Literal["auto", "needs_human", "approved", "blocked_dlp"]


class AnswerRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("answers")

    def create(self, answer: Answer) -> Answer:
        self._store.set(answer.answer_id, asdict(answer))
        return answer

    def list_for_questionnaire(self, questionnaire_id: str) -> list[Answer]:
        return [Answer(**d) for d in self._store.list(lambda d: d["questionnaire_id"] == questionnaire_id)]


answer_repo = AnswerRepo()

# -------------------------------------------------------------------- Run


@dataclass
class Run:
    run_id: str
    agent: str
    started_at: str
    last_checkpoint: str
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    attempt: int = 1
    status: Literal["running", "completed", "failed"] = "running"


class RunRepo:
    """Checkpointed state for long-running agent sweeps (Drift Sentinel)."""

    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("runs")

    def start(self, agent: str, pending_steps: list[str]) -> Run:
        run = Run(run_id=_new_id("run"), agent=agent, started_at=_now(), last_checkpoint=_now(), pending_steps=pending_steps)
        self._store.set(run.run_id, asdict(run))
        return run

    def checkpoint(self, run_id: str, completed_step: str) -> Run:
        current = self._store.get(run_id) or {}
        completed = current.get("completed_steps", []) + [completed_step]
        pending = [s for s in current.get("pending_steps", []) if s != completed_step]
        data = self._store.update(
            run_id, {"completed_steps": completed, "pending_steps": pending, "last_checkpoint": _now()}
        )
        return Run(**data)

    def complete(self, run_id: str) -> Run:
        data = self._store.update(run_id, {"status": "completed", "last_checkpoint": _now()})
        return Run(**data)

    def get(self, run_id: str) -> Run | None:
        data = self._store.get(run_id)
        return Run(**data) if data else None


run_repo = RunRepo()

# -------------------------------------------------------------- FleetConfig

_FLEET_CONFIG_COLLECTION = "fleet_config"
_FLEET_CONFIG_DOC_ID = "global"


@dataclass
class FleetConfig:
    autonomy_level: int = 3  # THE KILL SWITCH -- see platform/policy.py
    max_daily_token_spend: float = 50.0
    paused_agents: list[str] = field(default_factory=list)


class FleetConfigRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore(_FLEET_CONFIG_COLLECTION)

    def get(self) -> FleetConfig:
        data = self._store.get(_FLEET_CONFIG_DOC_ID)
        if data is None:
            config = FleetConfig()
            self._store.set(_FLEET_CONFIG_DOC_ID, asdict(config))
            return config
        return FleetConfig(**data)

    def update(self, **patch: Any) -> FleetConfig:
        current = asdict(self.get())
        current.update(patch)
        self._store.set(_FLEET_CONFIG_DOC_ID, current)
        return FleetConfig(**current)


fleet_config_repo = FleetConfigRepo()

# ------------------------------------------------------------------- Digest


@dataclass
class Digest:
    """One run of the Executive Risk Digest: a persisted, replayable
    record of both the narrative Gemini wrote *and* the exact inputs it
    was grounded in -- so "what did the digest say last Monday" has a
    real answer, not just whatever's currently true."""

    digest_id: str
    tenant: str
    trace_id: str
    narrative: str
    highlights: list[str]
    inputs: dict[str, Any]
    generated_at: str = field(default_factory=_now)


class DigestRepo:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("digests")

    def create(self, digest: Digest) -> Digest:
        self._store.set(digest.digest_id, asdict(digest))
        return digest

    def get(self, digest_id: str) -> Digest | None:
        data = self._store.get(digest_id)
        return Digest(**data) if data else None

    def latest(self, tenant: str) -> Digest | None:
        items = [Digest(**d) for d in self._store.list(lambda d: d["tenant"] == tenant)]
        return max(items, key=lambda d: d.generated_at) if items else None


digest_repo = DigestRepo()
