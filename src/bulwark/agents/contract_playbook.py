"""The contract playbook: the tenant's standard for what an acceptable
vendor contract clause looks like, per clause type.

Illustrative reference data -- same labeled-mock pattern as
``internal_sources.py`` (mock GCP evidence) and Claim Guardian's
billing-code reference in this account's other hackathon submission. A
real deployment would source this from the tenant's actual legal
playbook (often itself a Firestore collection a legal team edits), not a
Python constant; what's real here is the *shape* of playbook-driven
clause evaluation, not these specific numbers.
"""

from __future__ import annotations

PLAYBOOK: dict[str, dict[str, object]] = {
    "breach_notification": {
        "requirement": "Vendor must notify within 72 hours of becoming aware of a breach.",
        "max_hours": 72,
    },
    "liability_cap": {
        "requirement": "Liability cap must be at least 1x annual contract value, uncapped for data breaches.",
        "min_multiple_of_acv": 1.0,
    },
    "data_residency": {
        "requirement": "Vendor must commit to processing tenant data only in the tenant's contracted region.",
    },
    "audit_rights": {
        "requirement": "Tenant must retain the right to audit the vendor's security controls (directly or via a third party) at least annually.",
    },
    "subprocessor_flow_down": {
        "requirement": "Vendor must flow down equivalent data-protection obligations to every subprocessor and disclose subprocessor changes with at least 30 days' notice.",
    },
    "termination_assistance": {
        "requirement": "Vendor must provide data export and certify deletion within 30 days of contract termination.",
        "max_days": 30,
    },
}


def requirement_for(clause_type: str) -> str:
    entry = PLAYBOOK.get(clause_type)
    return str(entry["requirement"]) if entry else "No playbook entry for this clause type -- flag for manual legal review."


def termination_deadline_days() -> int:
    """Days a vendor has to confirm data deletion after offboarding
    begins, per the playbook's `termination_assistance` entry --
    ``agents/offboarding.py`` uses this to compute a deadline
    deterministically instead of re-deriving it from clause text."""
    entry = PLAYBOOK.get("termination_assistance", {})
    return int(entry.get("max_days", 30))  # type: ignore[arg-type]
