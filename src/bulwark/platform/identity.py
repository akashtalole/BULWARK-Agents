"""Agent Identity: zero-trust, per-agent resource grants.

Section 6.1's design property, enforced in code rather than asserted in
prose: *the agent that touches untrusted data has no access to anything
worth stealing, and the agents with access never touch untrusted data.*

Every tool in agents/ calls ``require_grant(agent_id, scope)`` before it
touches a resource. This is a hard allow/deny check against a table
below, independent of anything the model decided or was told to do --
compromising the Intake Agent (the one agent that processes attacker-
controlled documents) yields access to nothing, because its grant set is
empty for every resource worth stealing.

In a real deployment each row below is a distinct GCP service account
with IAM bindings that make the same statement at the infrastructure
layer (see deploy/setup_gcp.sh); this module is what lets that same
zero-trust shape be demonstrated and unit-tested without a live project.
"""

from __future__ import annotations

from dataclasses import dataclass


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class AgentGrant:
    service_account: str
    allowed: frozenset[str]
    denied: frozenset[str]  # documented explicitly even where redundant with "not allowed"


AGENT_GRANTS: dict[str, AgentGrant] = {
    "assurance-supervisor": AgentGrant(
        service_account="sa-supervisor",
        allowed=frozenset({"events:route"}),
        denied=frozenset({"evidence:read", "assertions:read", "findings:write", "network:egress"}),
    ),
    "vendor-intake": AgentGrant(
        service_account="sa-intake",
        allowed=frozenset({"gcs:quarantine:read", "assertions:write"}),
        denied=frozenset({"evidence:read", "findings:write", "answers:write", "network:egress"}),
    ),
    "contract-intelligence": AgentGrant(
        service_account="sa-contract",
        # Same untrusted trust zone as Intake, same shape of grant: can
        # read the quarantine bucket and write its own extraction output,
        # nothing else -- compromising this agent yields nothing more
        # than compromising Intake would.
        allowed=frozenset({"gcs:quarantine:read", "contract_terms:write", "subprocessors:write", "pubsub:publish"}),
        denied=frozenset({"evidence:read", "assertions:read", "findings:write", "answers:write", "network:egress"}),
    ),
    "concentration-analyzer": AgentGrant(
        service_account="sa-concentration",
        allowed=frozenset({"subprocessors:read", "vendors:read", "concentration_risks:write"}),
        denied=frozenset({"findings:write", "contract_terms:read", "network:egress"}),
    ),
    "framework-crosswalk": AgentGrant(
        service_account="sa-crosswalk",
        # Read-only over the fleet's own already-produced Findings --
        # writes nothing, so there's no scope worth denying beyond the
        # usual "never write findings, never leave the network."
        allowed=frozenset({"findings:read"}),
        denied=frozenset({"findings:write", "evidence:read", "assertions:read", "network:egress"}),
    ),
    "offboarding-agent": AgentGrant(
        service_account="sa-offboarding",
        allowed=frozenset({"vendors:write", "offboarding_records:read", "offboarding_records:write", "contract_terms:read"}),
        denied=frozenset({"findings:write", "gcs:quarantine:read", "network:egress"}),
    ),
    "executive-digest": AgentGrant(
        service_account="sa-digest",
        # Reads broadly across the fleet's own already-produced output --
        # the widest read scope of any agent -- but writes nothing except
        # its own digest record, and network:egress stays denied like
        # everywhere else: a digest is read via the API, it is never
        # emailed or posted anywhere by this codebase.
        allowed=frozenset({"findings:read", "vendors:read", "concentration_risks:read", "offboarding_records:read", "digests:write"}),
        denied=frozenset({"findings:write", "vendors:write", "gcs:quarantine:read", "network:egress"}),
    ),
    "evidence-collector": AgentGrant(
        service_account="sa-evidence",
        allowed=frozenset(
            {
                "cloud_asset_inventory:read",
                "security_command_center:read",
                "iam:read",
                "logging:read",
                "evidence:write",
            }
        ),
        denied=frozenset({"findings:write", "assertions:read", "network:egress"}),
    ),
    "risk-assessor": AgentGrant(
        service_account="sa-assessor",
        allowed=frozenset({"assertions:read", "evidence:read", "controls:read", "findings:write", "assessment_snapshots:write"}),
        denied=frozenset({"gcs:quarantine:read", "network:egress"}),
    ),
    "questionnaire-responder": AgentGrant(
        service_account="sa-questionnaire",
        allowed=frozenset({"evidence:read", "answers:write", "export:dlp_gated"}),
        denied=frozenset({"gcs:quarantine:read", "export:direct"}),
    ),
    "drift-sentinel": AgentGrant(
        service_account="sa-sentinel",
        allowed=frozenset(
            {
                "assessments:read",
                "assessments:write",
                "assessment_snapshots:read",
                "memory_bank:read",
                "memory_bank:write",
                "pubsub:publish",
            }
        ),
        denied=frozenset({"findings:write", "network:egress"}),
    ),
    "remediation-router": AgentGrant(
        service_account="sa-remediation",
        allowed=frozenset({"tickets:write", "pubsub:publish", "secrets:read", "email:draft"}),
        denied=frozenset({"email:send_autonomous"}),
    ),
}


def require_grant(agent_id: str, scope: str) -> None:
    grant = AGENT_GRANTS.get(agent_id)
    if grant is None:
        raise PermissionDenied(f"unknown agent_id '{agent_id}' has no identity grant at all")
    if scope in grant.denied:
        raise PermissionDenied(f"agent '{agent_id}' ({grant.service_account}) is explicitly denied scope '{scope}'")
    if scope not in grant.allowed:
        raise PermissionDenied(f"agent '{agent_id}' ({grant.service_account}) has no grant for scope '{scope}'")
