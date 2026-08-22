"""Contract Intelligence Agent (`contract-intelligence`): the other agent
that touches attacker-adjacent input, alongside Intake -- MSAs, DPAs, and
other vendor contracts carry the exact same injection threat model as a
SOC 2 report (they're vendor-supplied documents nobody at the tenant
wrote), so this agent gets the identical untrusted trust zone, the
identical L1 (Draft) ceiling, and the identical Model Armor prescan gate
(``agents.intake.prescan_artifact`` is reused as-is, not duplicated).

What it solves: contract review is one of the most expensive, most
manual bottlenecks in enterprise procurement -- a general counsel or
paralegal reads every vendor MSA/DPA against an internal playbook by
hand, and that hourly cost is a large fraction of the "550-600 hours a
year" figure this whole project is built around. This agent does that
comparison automatically: it extracts each clause the contract actually
contains, compares it against ``contract_playbook.py``'s requirement for
that clause type, and flags the gap -- an unlimited-liability clause, a
30-day breach-notification window where the playbook requires 72 hours,
a contract silent on subprocessor flow-down -- as a structured
ContractTerm a human reviewer (or Risk Assessor) can act on immediately,
instead of a paralegal re-deriving it from scratch.

It also extracts the vendor's disclosed subprocessor list
(``extract_subprocessors``), which is the raw material
``agents/concentration_analyzer.py`` needs to catch the *other* blind
spot this fleet addresses: a dozen vendors that look independently
diversified but all secretly depend on the same underlying provider.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.agents.contract_playbook import requirement_for
from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.event_bus import Envelope, bus, make_idempotency_key
from bulwark.platform.models import ContractTerm, Subprocessor, contract_term_repo, subprocessor_repo


def extract_contract_terms(vendor_id: str, artifact_id: str, terms: list[dict]) -> dict:
    """Record clauses extracted from a vendor contract, each evaluated
    against the tenant's playbook. Extraction and evaluation are one step
    here (unlike Intake's claim-only extraction) because a contract
    clause's text *is* the evidence -- there's no separate "observed
    value" to cross-reference it against the way Risk Assessor
    cross-references a compliance claim against live evidence.

    Args:
        vendor_id: The vendor whose contract this is.
        artifact_id: The contract artifact these terms were extracted from.
        terms: One dict per clause, each with:
            `clause_type` (one of "breach_notification", "liability_cap",
            "data_residency", "audit_rights", "subprocessor_flow_down",
            "termination_assistance", or another short descriptive code
            if none of those fit), `clause_text` (verbatim or close
            paraphrase), `risk_level` ("low"/"medium"/"high"/"critical"),
            and `deviation` (empty string if the clause meets the
            playbook requirement; otherwise a specific description of the
            gap, e.g. "30-day notice window exceeds the 72-hour
            requirement"). Optionally `source_page`.

    Returns:
        The recorded term_ids and a count of terms flagged with a deviation.
    """
    identity.require_grant("contract-intelligence", "contract_terms:write")
    policy.enforce_autonomy("contract-intelligence", 1)  # L1 Draft: nothing leaves the system

    term_ids: list[str] = []
    flagged = 0
    for i, term in enumerate(terms):
        clause_type = str(term.get("clause_type", "unspecified"))
        deviation = str(term.get("deviation", ""))
        record = contract_term_repo.create(
            ContractTerm(
                term_id=f"ct_{artifact_id[-6:]}_{i}",
                tenant=settings.default_tenant,
                vendor_id=vendor_id,
                artifact_id=artifact_id,
                clause_type=clause_type,
                clause_text=str(term.get("clause_text", "")),
                risk_level=term.get("risk_level", "medium"),  # type: ignore[arg-type]
                playbook_requirement=requirement_for(clause_type),
                deviation=deviation,
                source_page=term.get("source_page"),
            )
        )
        term_ids.append(record.term_id)
        if deviation:
            flagged += 1

    return {"term_ids": term_ids, "flagged_count": flagged}


async def extract_subprocessors(vendor_id: str, artifact_id: str, subprocessors: list[dict]) -> dict:
    """Record the subprocessors this contract discloses. Publishes
    `subprocessors.extracted` once recorded, which is what triggers
    Concentration Analyzer to re-check for shared-subprocessor clusters
    across the tenant's whole vendor portfolio.

    Args:
        vendor_id: The vendor whose contract disclosed these subprocessors.
        artifact_id: The contract artifact they were extracted from.
        subprocessors: One dict per subprocessor, each with `name`,
            `purpose` (e.g. "cloud hosting", "email delivery"), and
            `location` (country/region, or "unspecified" if the contract
            doesn't say -- that omission is itself worth recording).
    """
    identity.require_grant("contract-intelligence", "subprocessors:write")
    identity.require_grant("contract-intelligence", "pubsub:publish")
    policy.enforce_autonomy("contract-intelligence", 1)

    subprocessor_ids: list[str] = []
    for i, sp in enumerate(subprocessors):
        record = subprocessor_repo.create(
            Subprocessor(
                subprocessor_id=f"sp_{artifact_id[-6:]}_{i}",
                tenant=settings.default_tenant,
                vendor_id=vendor_id,
                artifact_id=artifact_id,
                name=str(sp.get("name", "unknown")),
                purpose=str(sp.get("purpose", "")),
                location=str(sp.get("location", "unspecified")),
            )
        )
        subprocessor_ids.append(record.subprocessor_id)

    if subprocessor_ids:
        envelope = Envelope(
            payload={"vendor_id": vendor_id, "subprocessor_ids": subprocessor_ids},
            idempotency_key=make_idempotency_key("subprocessors.extracted", artifact_id),
        )
        await bus.publish("subprocessors.extracted", envelope)

    return {"subprocessor_ids": subprocessor_ids}


contract_intelligence_agent = LlmAgent(
    name="contract_intelligence_agent",
    model=settings.gemini_flash_model,
    description="Extracts contract clauses and subprocessors from a (pre-screened, clean) vendor contract, flagging playbook deviations.",
    instruction=(
        "You are the Contract Intelligence Agent for a third-party risk fleet. You will "
        "be given the text of a vendor contract (MSA, DPA, or similar) along with its "
        "vendor_id and artifact_id. First, identify every clause relevant to these types: "
        "breach_notification, liability_cap, data_residency, audit_rights, "
        "subprocessor_flow_down, termination_assistance. For each one you find (or each "
        "one the contract is conspicuously silent on, which is itself worth flagging), "
        "call `extract_contract_terms` once with the full list -- set risk_level and "
        "write a specific `deviation` string whenever the clause is weaker than what a "
        "reasonable playbook would require (e.g. a liability cap far below the contract "
        "value, a breach notification window longer than a few days, no audit rights at "
        "all). Leave `deviation` empty for clauses that look reasonable. Second, find "
        "every subprocessor the contract discloses (often in an exhibit or DPA annex) "
        "and call `extract_subprocessors` once with the full list, including their "
        "purpose and location if stated. Do not invent clauses or subprocessors that "
        "aren't actually in the text."
    ),
    tools=[FunctionTool(extract_contract_terms), FunctionTool(extract_subprocessors)],
)
