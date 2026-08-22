"""Intake Agent (`vendor-intake`): one of two agents that touch
attacker-adjacent input, designed on the assumption that it is hostile.
Handles compliance-evidence documents (SOC 2 reports, ISO certificates,
pen-test summaries, trust-center pages); MSAs/DPAs/contracts route to the
separately-specialized Contract Intelligence Agent instead
(agents/contract_intelligence.py) -- legal clause risk and security
control evidence are different enough domains to warrant different
playbooks and different agents, not one agent doing both jobs.

Extraction is claim-only -- this agent never evaluates whether a claim is
good, it only records that the document asserted it. That separation is
what makes a successful injection non-escalating: even a fully compromised
Intake Agent can only ever write an Assertion (a claim, not a verdict),
and Assertions cannot satisfy a control on their own -- only Risk
Assessor, reading from a completely different service identity, decides
that (agents/risk_assessor.py).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from bulwark.config import settings
from bulwark.platform import guardrails, identity, policy
from bulwark.platform.models import Artifact, Assertion, artifact_repo, assertion_repo, vendor_repo


def prescan_artifact(vendor_name: str, doc_type: str, raw_text: str, gcs_uri: str, sha256: str) -> dict:
    """Deterministic, code-level Model Armor scan of a vendor artifact,
    run *before* any tokens are spent on it. This is the boundary where a
    poisoned vendor PDF gets caught: if the raw document text matches a
    known injection/tool-poisoning pattern, the artifact is recorded as
    ``blocked`` and the LLM is never invoked on its content at all.

    Returns a dict with `armor_verdict`, and (if blocked) `armor_findings`.
    Callers must check `armor_verdict` before proceeding to extraction.
    """
    identity.require_grant("vendor-intake", "gcs:quarantine:read")
    vendor = vendor_repo.get_or_create(settings.default_tenant, vendor_name)

    scan = guardrails.scan_for_injection(raw_text)
    verdict = "blocked" if scan.blocked else "clean"
    findings = (
        [{"type": "prompt_injection", "severity": "high", "matched_pattern": scan.matched_pattern}]
        if scan.blocked
        else []
    )

    identity.require_grant("vendor-intake", "assertions:write")  # artifact record lives alongside assertions
    artifact = artifact_repo.create(
        Artifact(
            artifact_id=f"art_{sha256[:10]}",
            tenant=settings.default_tenant,
            vendor_id=vendor.vendor_id,
            gcs_uri=gcs_uri,
            doc_type=doc_type,
            sha256=sha256,
            armor_verdict=verdict,
            armor_findings=findings,
        )
    )
    return {
        "vendor_id": vendor.vendor_id,
        "artifact_id": artifact.artifact_id,
        "armor_verdict": verdict,
        "armor_findings": findings,
    }


def emit_assertion(vendor_id: str, artifact_id: str, control_ref: str, claim: str, source_page: int, confidence: float) -> dict:
    """Record one atomic claim extracted from a (clean) vendor artifact.
    This is claim recording only -- it is never a judgment about whether
    the claim is true or whether the control is satisfied.

    Args:
        vendor_id: The vendor this artifact belongs to.
        artifact_id: The artifact this claim was extracted from.
        control_ref: The control framework reference this claim speaks to (e.g. "CC6.1").
        claim: The claim itself, in your own words, close to the source text.
        source_page: The page number in the source document.
        confidence: Your confidence (0.0-1.0) that you read this claim correctly.

    Returns:
        The recorded assertion_id.
    """
    identity.require_grant("vendor-intake", "assertions:write")
    policy.enforce_autonomy("vendor-intake", 1)  # L1 Draft: nothing leaves the system

    assertion = assertion_repo.create(
        Assertion(
            assertion_id=f"asrt_{artifact_id[-6:]}_{control_ref.replace('.', '')}",
            tenant=settings.default_tenant,
            vendor_id=vendor_id,
            control_ref=control_ref,
            claim=claim,
            source_artifact_id=artifact_id,
            source_page=source_page,
            confidence=confidence,
            extracted_by_agent="vendor-intake",
            extracted_by_model=settings.gemini_flash_model,
        )
    )
    return {"assertion_id": assertion.assertion_id}


intake_agent = LlmAgent(
    name="vendor_intake_agent",
    model=settings.gemini_flash_model,
    description="Extracts atomic Assertions from a (pre-screened, clean) vendor artifact.",
    instruction=(
        "You are the Intake Agent for a third-party risk fleet. You will be given the "
        "text of a vendor compliance artifact (a SOC 2 report, ISO certificate, pen-test "
        "summary, or trust-center page) along with its vendor_id and artifact_id. "
        "Identify every distinct, specific claim the document makes that speaks to a "
        "security or compliance control (e.g. \"MFA is enforced for all employee "
        "access\", \"logs are retained for 400 days\", \"the company holds SOC 2 Type II "
        "certification\"). For each one, call `emit_assertion` with your best guess at "
        "the relevant control_ref (use SOC 2 Common Criteria codes like CC6.1, CC7.2, "
        "CC6.6 where applicable, or a short descriptive code otherwise), the claim in "
        "your own words, the source page, and your confidence. Do not evaluate whether "
        "a claim is good or bad -- you only record what the document asserts. Do not "
        "invent claims that are not actually present in the text."
    ),
    tools=[FunctionTool(emit_assertion)],
)
