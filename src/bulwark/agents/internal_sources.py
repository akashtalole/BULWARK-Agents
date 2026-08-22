"""Mock internal evidence sources.

Stands in for the real read-only GCP/tooling calls Evidence Collector
would make in production (Cloud Asset Inventory, Security Command Center,
IAM policy bindings, Cloud Logging retention config, GitHub
branch-protection rules, Jira SLA data, HR onboarding records) -- the same
"illustrative reference data, clearly labeled" pattern used for the mock
ERP/billing-code datasets in this hackathon's other two submissions. A
real deployment swaps ``read_all_sources`` for actual API calls behind
the same return shape; nothing else in evidence_collector.py would change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_all_sources() -> list[dict[str, object]]:
    """Return one reading per (control_ref, source). A `drifted` reading
    is included on purpose (CC6.8) so the demo has something for Drift
    Sentinel to actually catch."""
    fresh = _now_iso()
    return [
        {
            "control_ref": "CC6.1",
            "source": "iam",
            "observed_value": "mfa_enforced",
            "expected_value": "mfa_enforced",
            "collected_at": fresh,
        },
        {
            "control_ref": "CC6.6",
            "source": "cloud_asset_inventory",
            "observed_value": "no_public_buckets",
            "expected_value": "no_public_buckets",
            "collected_at": fresh,
        },
        {
            "control_ref": "CC6.8",
            "source": "logging",
            "observed_value": "retention_30d",  # drifted: policy requires 365d
            "expected_value": "retention_365d",
            "collected_at": fresh,
        },
        {
            "control_ref": "CC7.2",
            "source": "security_command_center",
            "observed_value": "no_critical_findings_open",
            "expected_value": "no_critical_findings_open",
            "collected_at": fresh,
        },
        {
            "control_ref": "CC8.1",
            "source": "github",
            "observed_value": "branch_protection_enabled",
            "expected_value": "branch_protection_enabled",
            "collected_at": fresh,
        },
        # A reading intentionally older than the freshness window, so
        # Evidence Collector's freshness derivation has something to show.
        {
            "control_ref": "CC9.2",
            "source": "jira",
            "observed_value": "sla_met",
            "expected_value": "sla_met",
            "collected_at": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
        },
    ]
