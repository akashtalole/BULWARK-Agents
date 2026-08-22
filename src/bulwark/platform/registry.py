"""Agent Registry: the catalog Security, Legal, Procurement, and Sales
Engineering each discover and reuse the same seven agents from, per
section 3's fleet design.

Every agent self-registers at startup with its registry id, model,
trust zone, and autonomy ceiling -- the same fields enforced at runtime
by platform/policy.py, so the registry is a live reflection of what's
actually deployed, not documentation that can drift from it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from bulwark.platform.store import DocumentStore

_REGISTRY_COLLECTION = "agent_registry"


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    name: str
    version: str
    description: str
    model: str
    trust_zone: str  # "untrusted" | "internal" | "internal-read-only" | "egress-controlled" | "internal-write"
    autonomy_ceiling: int  # 0 Observe / 1 Draft / 2 Act-with-approval / 3 Act-autonomously
    departments: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


class AgentRegistry:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore(_REGISTRY_COLLECTION)

    def register(self, record: AgentRecord) -> None:
        self._store.set(record.agent_id, asdict(record))

    def get(self, agent_id: str) -> AgentRecord | None:
        data = self._store.get(agent_id)
        return AgentRecord(**data) if data else None

    def list(self) -> list[AgentRecord]:
        return sorted((AgentRecord(**d) for d in self._store.list()), key=lambda r: r.agent_id)


registry = AgentRegistry()


def bootstrap_registry() -> None:
    from bulwark.config import settings

    flash, pro = settings.gemini_flash_model, settings.gemini_pro_model

    registry.register(
        AgentRecord(
            agent_id="assurance-supervisor",
            name="Supervisor",
            version="0.1.0",
            description="Classifies inbound events and delegates to the fleet. Holds no tools.",
            model=flash,
            trust_zone="internal",
            autonomy_ceiling=1,
            departments=["security", "procurement"],
            tools=[],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="vendor-intake",
            name="Intake Agent",
            version="0.1.0",
            description="Extracts atomic Assertions from untrusted vendor artifacts. Never evaluates them.",
            model=flash,
            trust_zone="untrusted",
            autonomy_ceiling=1,
            departments=["security", "procurement", "legal"],
            tools=["emit_assertion"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="contract-intelligence",
            name="Contract Intelligence Agent",
            version="0.1.0",
            description=(
                "Extracts clauses and subprocessors from untrusted vendor contracts (MSA/DPA), "
                "flagging gaps against the tenant's legal playbook. Feeds Concentration Analyzer."
            ),
            model=flash,
            trust_zone="untrusted",
            autonomy_ceiling=1,
            departments=["legal", "procurement", "security"],
            tools=["extract_contract_terms", "extract_subprocessors"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="concentration-analyzer",
            name="Concentration Risk Analyzer",
            version="0.1.0",
            description=(
                "Detects vendor portfolios that look diversified but share a single underlying "
                "subprocessor. Deliberately deterministic (no LLM call) -- clustering shared "
                "names in a graph is a lookup, not reasoning."
            ),
            model="deterministic (no LLM)",
            trust_zone="internal-read-only",
            autonomy_ceiling=3,
            departments=["security", "procurement"],
            tools=["analyze_concentration_risk"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="framework-crosswalk",
            name="Framework Crosswalk Agent",
            version="0.1.0",
            description=(
                "Computes how much of a target compliance framework (ISO 27001, NIST CSF) a vendor "
                "already satisfies via its existing SOC 2 findings, so a compliance team knows exactly "
                "which controls still need fresh evidence instead of re-collecting everything from zero."
            ),
            model="deterministic (no LLM)",
            trust_zone="internal-read-only",
            autonomy_ceiling=3,
            departments=["security", "legal", "procurement"],
            tools=["compute_framework_coverage"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="offboarding-agent",
            name="Offboarding & Termination Assistance Agent",
            version="0.1.0",
            description=(
                "Tracks the data-deletion deadline every DPA's termination_assistance clause "
                "creates when a vendor relationship ends, and flags it via Drift Sentinel if it's "
                "missed. Deliberately deterministic (no LLM call) -- comparing a deadline to today "
                "is a lookup, not reasoning."
            ),
            model="deterministic (no LLM)",
            trust_zone="internal-write",
            autonomy_ceiling=3,
            departments=["legal", "procurement", "security"],
            tools=["initiate_offboarding", "confirm_data_deletion", "check_offboarding_overdue"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="executive-digest",
            name="Executive Risk Digest Agent",
            version="0.1.0",
            description=(
                "Synthesizes the fleet's current findings, concentration risks, and offboarding "
                "state into a short, prioritized narrative a busy executive can read in under a "
                "minute, instead of clicking through 30+ API endpoints."
            ),
            model=flash,
            trust_zone="internal",
            # Ceiling is the max of what its two tools individually request:
            # gather_digest_inputs is read-only (L3, same as Framework
            # Crosswalk's own read-only analysis); publish_digest itself
            # still only ever requests L1 (Draft) -- writing a digest
            # document, nothing leaves the system.
            autonomy_ceiling=3,
            departments=["security", "legal", "procurement", "sales-engineering"],
            tools=["gather_digest_inputs", "publish_digest"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="evidence-collector",
            name="Evidence Collector",
            version="0.1.0",
            description=(
                "Turns live internal posture into control Evidence. Read-only. Deliberately "
                "deterministic (no LLM call) -- collecting a value and comparing it to a "
                "policy needs no reasoning, and skipping the model call removes an entire "
                "class of risk from the one agent with the broadest read access."
            ),
            model="deterministic (no LLM)",
            trust_zone="internal-read-only",
            autonomy_ceiling=3,
            departments=["security"],
            tools=["collect_evidence"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="risk-assessor",
            name="Risk Assessor",
            version="0.1.0",
            description="Cross-references Assertions + Evidence + ControlRequirements into cited Findings.",
            model=pro,
            trust_zone="internal",
            autonomy_ceiling=1,
            departments=["security", "legal"],
            tools=["create_finding"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="questionnaire-responder",
            name="Questionnaire Responder",
            version="0.1.0",
            description="Answers buyer questionnaires from the evidence graph, with citations and abstention.",
            model=flash,
            trust_zone="egress-controlled",
            autonomy_ceiling=2,
            departments=["sales-engineering", "security"],
            tools=["draft_answer"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="drift-sentinel",
            name="Drift Sentinel",
            version="0.1.0",
            description="Long-running per-vendor watch: expiry, breach signals, subprocessor changes, control drift.",
            model=flash,
            trust_zone="internal",
            autonomy_ceiling=3,
            departments=["security", "procurement"],
            tools=["reopen_assessment"],
        )
    )
    registry.register(
        AgentRecord(
            agent_id="remediation-router",
            name="Remediation Router",
            version="0.1.0",
            description="Opens tickets, builds decision packets, drafts (never sends) vendor follow-up email.",
            model=flash,
            trust_zone="internal-write",
            autonomy_ceiling=2,
            departments=["security", "procurement", "legal"],
            tools=["open_ticket", "draft_vendor_email", "build_decision_packet"],
        )
    )
