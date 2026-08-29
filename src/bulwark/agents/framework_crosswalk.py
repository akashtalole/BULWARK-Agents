"""Framework Crosswalk Agent (`framework-crosswalk`): deliberately
deterministic, no LLM call -- same reasoning as Evidence Collector and
Concentration Analyzer. Looking up a control's equivalent in another
framework is a table lookup, not judgment, so this costs zero tokens and
carries zero prompt-injection surface on an agent that only ever reads
data other agents already produced.

The problem this solves: enterprises rarely carry just one compliance
framework. The same company answers to SOC 2 for one buyer, ISO 27001
for a European one, NIST CSF for a federal one -- and standard tooling
re-collects evidence for each framework independently, because nothing
tells a compliance team "you already proved this exact control, just
under a different name." That's redundant audit work multiplying
linearly with the number of frameworks a vendor (or the tenant itself)
has to satisfy. This agent doesn't re-collect anything -- it looks at
Findings Risk Assessor has *already* produced for a vendor's SOC 2
controls and reports, per the crosswalk in
``framework_crosswalk_reference.py``, which controls in a target
framework are already indirectly covered versus which ones still need
fresh evidence. That's the difference between "start ISO 27001
evidence collection from zero" and "here are the 4 controls you
actually still need."
"""

from __future__ import annotations

from bulwark.agents.framework_crosswalk_reference import CROSSWALK
from bulwark.platform import identity, policy
from bulwark.platform.models import finding_repo


def compute_framework_coverage(vendor_id: str, target_framework: str) -> dict:
    """For a vendor already assessed against SOC 2 controls, report how
    much of `target_framework` (e.g. "ISO27001", "NISTCSF") is already
    indirectly satisfied via the crosswalk, versus genuinely uncovered.

    This is deliberately conservative: a target control only counts as
    covered if there's a `Finding` with `status == "satisfied"` for its
    SOC 2 equivalent -- a gap, an exception, or an unassessed control all
    count as still needing attention, same as they would under direct
    assessment.

    Some target controls have more than one SOC 2 equivalent (e.g. both
    CC6.8 and CC7.2 crosswalk to ISO 27001's A.12.4.1 -- log retention
    and security monitoring are both partial evidence for it). Grouping
    by `target_control` before classifying covered vs. gap matters here:
    without it, a target control with one satisfied and one unsatisfied
    mapping would show up in *both* lists -- a contradiction a reviewer
    would read as a bug, and a target control double-counted in
    `coverage_pct`'s denominator. One satisfied mapping is enough to call
    the target control covered.

    Returns:
        `{vendor_id, target_framework, covered_controls, gap_controls,
        coverage_pct}` -- each covered/gap entry cites the SOC 2
        control(s) and (for covered ones) the finding_id that justifies
        the coverage claim, so the result is traceable, not just a number.
    """
    identity.require_grant("framework-crosswalk", "findings:read")
    policy.enforce_autonomy("framework-crosswalk", 3)  # L3: read-only cross-referencing of the fleet's own output

    satisfied_by_control = {f.control_ref: f for f in finding_repo.list_for_vendor(vendor_id) if f.status == "satisfied"}

    mappings_by_target: dict[str, list[str]] = {}
    for soc2_ref, targets in CROSSWALK.items():
        target_ref = targets.get(target_framework)
        if target_ref is None:
            continue
        mappings_by_target.setdefault(target_ref, []).append(soc2_ref)

    covered: list[dict] = []
    gaps: list[dict] = []
    for target_ref, soc2_refs in mappings_by_target.items():
        satisfied_ref = next((ref for ref in soc2_refs if ref in satisfied_by_control), None)
        if satisfied_ref:
            covered.append(
                {
                    "target_control": target_ref,
                    "via_soc2_control": satisfied_ref,
                    "source_finding_id": satisfied_by_control[satisfied_ref].finding_id,
                }
            )
        else:
            gaps.append(
                {
                    "target_control": target_ref,
                    "via_soc2_control": " / ".join(soc2_refs),
                    "reason": "no satisfied SOC 2 finding yet for the equivalent control",
                }
            )

    total = len(covered) + len(gaps)
    return {
        "vendor_id": vendor_id,
        "target_framework": target_framework,
        "covered_controls": covered,
        "gap_controls": gaps,
        "coverage_pct": round(100 * len(covered) / total, 1) if total else 0.0,
    }
