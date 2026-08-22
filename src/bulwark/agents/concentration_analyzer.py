"""Concentration Risk Analyzer (`concentration-analyzer`): deliberately
deterministic, no LLM call -- same reasoning as Evidence Collector.
Clustering subprocessor names shared across vendors is a graph lookup,
not a judgment call, so making it plain Python instead of an ADK
`LlmAgent` costs zero tokens and carries zero prompt-injection surface,
on the one agent whose entire job is reading data other agents already
extracted from untrusted documents.

The problem this solves: standard third-party risk review is
per-vendor -- each SOC 2 report, each contract, gets reviewed in
isolation and comes back looking fine. What that misses is *portfolio*
risk: if twelve of a company's "diversified" vendors all secretly run on
the same subprocessor (the same cloud region, the same auth provider, the
same payment processor), a single outage or breach at that one
subprocessor becomes a correlated failure across a dozen vendor
relationships that were never assessed together. This is exactly the
blind spot behind real incidents like the 2024 CrowdStrike outage
cascading through supposedly-independent downstream vendors, and it is
structurally invisible to any tool that only ever looks at one vendor at
a time -- which is what makes this a genuine architectural capability,
not a bigger checklist.
"""

from __future__ import annotations

import re
from collections import defaultdict

from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import ConcentrationRisk, concentration_risk_repo, subprocessor_repo, vendor_repo
from bulwark.platform.observability import audit_log


def _severity(vendor_count: int, critical_count: int) -> str:
    if critical_count >= 2:
        return "critical"
    if critical_count == 1 or vendor_count >= 4:
        return "high"
    return "medium"


def analyze_concentration_risk(trace_id: str | None = None) -> list[ConcentrationRisk]:
    """Cluster every subprocessor in the tenant's graph by normalized
    name, across all vendors, and flag every cluster touching 2+ distinct
    vendors -- especially where more than one of them is critical-tier.

    Returns the list of ConcentrationRisk records created this run
    (previous runs' records for the same subprocessor are superseded, not
    accumulated, so this always reflects current portfolio state)."""
    identity.require_grant("concentration-analyzer", "subprocessors:read")
    identity.require_grant("concentration-analyzer", "vendors:read")
    identity.require_grant("concentration-analyzer", "concentration_risks:write")
    policy.enforce_autonomy("concentration-analyzer", 3)  # L3: read-only analysis, write is this agent's own derived data

    concentration_risk_repo.clear_all(settings.default_tenant)

    all_subprocessors = subprocessor_repo.list(settings.default_tenant)
    vendors_by_name: dict[str, set[str]] = defaultdict(set)
    for sp in all_subprocessors:
        vendors_by_name[sp.name.strip().lower()].add(sp.vendor_id)

    results: list[ConcentrationRisk] = []
    for normalized_name, vendor_ids in vendors_by_name.items():
        if len(vendor_ids) < 2:
            continue  # a subprocessor used by exactly one vendor isn't a concentration risk

        vendors = [v for vid in vendor_ids if (v := vendor_repo.get(vid)) is not None]
        critical_vendors = [v for v in vendors if v.tier == "critical"]
        display_name = next(
            (sp.name for sp in all_subprocessors if sp.name.strip().lower() == normalized_name), normalized_name
        )
        severity = _severity(len(vendors), len(critical_vendors))
        detail = (
            f"{len(vendors)} vendors depend on '{display_name}' "
            f"({len(critical_vendors)} critical-tier: {[v.name for v in critical_vendors]}). "
            "A single incident at this subprocessor would be a correlated failure across "
            "all of them, not an independent one."
        )
        risk_id = "conc_" + re.sub(r"[^a-z0-9]+", "_", normalized_name).strip("_")
        risk = concentration_risk_repo.create(
            ConcentrationRisk(
                risk_id=risk_id,
                tenant=settings.default_tenant,
                subprocessor_name=display_name,
                vendor_ids=sorted(vendor_ids),
                critical_vendor_count=len(critical_vendors),
                severity=severity,  # type: ignore[arg-type]
                detail=detail,
            )
        )
        results.append(risk)
        audit_log.record(
            agent_name="concentration-analyzer",
            event="concentration_risk_detected",
            detail=detail,
            trace_id=trace_id,
        )

    return results
