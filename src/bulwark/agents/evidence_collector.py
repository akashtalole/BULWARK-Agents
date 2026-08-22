"""Evidence Collector (`evidence-collector`): read-only, scheduled,
deliberately deterministic -- no Gemini call.

Comparing an observed value to a policy's expected value is a pure
lookup-and-compare, not a reasoning task, so this "agent" is plain
Python rather than an ADK LlmAgent. That is a genuine design choice, not
a corner cut: it is cheaper (zero tokens for a step that runs every 6
hours across every control), and it removes an entire class of risk --
prompt injection has nothing to inject into, because there is no prompt.
Every other agent in the fleet still goes through the shared
Observability plugin's audit trail; this one calls ``audit_log.record``
directly for the same effect, since there is no ADK Runner wrapping it.
"""

from __future__ import annotations

from bulwark.agents.internal_sources import read_all_sources
from bulwark.config import settings
from bulwark.platform import identity, policy
from bulwark.platform.models import Evidence, evidence_repo
from bulwark.platform.observability import audit_log


def collect_evidence(trace_id: str | None = None) -> list[Evidence]:
    """Read every internal source and append one Evidence record per
    reading. Append-only, per the data model -- this never updates a
    prior reading, it always adds a new one."""
    identity.require_grant("evidence-collector", "cloud_asset_inventory:read")
    identity.require_grant("evidence-collector", "security_command_center:read")
    identity.require_grant("evidence-collector", "iam:read")
    identity.require_grant("evidence-collector", "logging:read")
    identity.require_grant("evidence-collector", "evidence:write")
    policy.enforce_autonomy("evidence-collector", 3)  # L3: read-only sweep, append-only write

    collected: list[Evidence] = []
    for i, reading in enumerate(read_all_sources()):
        evidence = evidence_repo.create(
            Evidence(
                evidence_id=f"ev_{reading['control_ref']}_{reading['source']}_{i}",
                tenant=settings.default_tenant,
                control_ref=str(reading["control_ref"]),
                observed_value=str(reading["observed_value"]),
                expected_value=str(reading["expected_value"]),
                source=str(reading["source"]),
                collected_at=str(reading["collected_at"]),
                content_hash=f"h_{reading['control_ref']}_{reading['source']}",
            )
        )
        collected.append(evidence)
        audit_log.record(
            agent_name="evidence-collector",
            event="evidence_collected",
            detail=(
                f"control={evidence.control_ref} source={evidence.source} "
                f"satisfied={evidence.satisfied} freshness={evidence.freshness}"
            ),
            trace_id=trace_id,
        )
    return collected
