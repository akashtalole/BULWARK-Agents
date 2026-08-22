"""The autonomy ladder and the kill switch -- enforced centrally, in one
place every agent's action-taking tools call through, rather than each
agent re-implementing its own notion of "am I allowed to do this."

    L0 Observe             -- read and log only
    L1 Draft                -- produce artifacts into a queue; nothing leaves the system
    L2 Act with approval     -- execute only after a recorded human decision
    L3 Act autonomously       -- reversible, low-blast-radius actions only

Two independent gates must both pass for an agent to take an action at a
given level:

1. The agent's own registered ceiling (Agent Registry) -- an agent can
   never act above the level it declared for itself, no matter what the
   global dial says.
2. The global dial (``fleet_config.autonomy_level``) and the per-agent
   pause list -- this is the literal kill switch: set the dial to 0 (or
   add an agent to ``paused_agents``) and every L1+ action across the
   fleet starts raising ``AutonomyBlocked``, live, without redeploying
   anything. That's the moment meant to be demonstrated on camera.
"""

from __future__ import annotations

from bulwark.platform.models import fleet_config_repo
from bulwark.platform.registry import registry

AUTONOMY_LEVELS = {
    0: "Observe",
    1: "Draft",
    2: "Act with approval",
    3: "Act autonomously",
}


class AutonomyBlocked(Exception):
    pass


def enforce_autonomy(agent_id: str, requested_level: int) -> None:
    """Raise AutonomyBlocked unless both the agent's own ceiling and the
    current global kill-switch state permit ``requested_level``."""
    record = registry.get(agent_id)
    if record is None:
        raise AutonomyBlocked(f"agent '{agent_id}' is not registered -- refusing to authorize any action")
    if requested_level > record.autonomy_ceiling:
        raise AutonomyBlocked(
            f"agent '{agent_id}' requested L{requested_level} "
            f"({AUTONOMY_LEVELS[requested_level]}) but its registered ceiling is "
            f"L{record.autonomy_ceiling} ({AUTONOMY_LEVELS[record.autonomy_ceiling]})"
        )

    config = fleet_config_repo.get()
    if agent_id in config.paused_agents:
        raise AutonomyBlocked(f"agent '{agent_id}' is paused by fleet_config.paused_agents")
    if requested_level > config.autonomy_level:
        raise AutonomyBlocked(
            f"global kill switch is at L{config.autonomy_level} "
            f"({AUTONOMY_LEVELS[config.autonomy_level]}); agent '{agent_id}' requested "
            f"L{requested_level} ({AUTONOMY_LEVELS[requested_level]})"
        )


def set_global_autonomy(level: int) -> None:
    if level not in AUTONOMY_LEVELS:
        raise ValueError(f"autonomy level must be one of {sorted(AUTONOMY_LEVELS)}")
    fleet_config_repo.update(autonomy_level=level)


def pause_agent(agent_id: str) -> None:
    config = fleet_config_repo.get()
    if agent_id not in config.paused_agents:
        fleet_config_repo.update(paused_agents=[*config.paused_agents, agent_id])


def resume_agent(agent_id: str) -> None:
    config = fleet_config_repo.get()
    fleet_config_repo.update(paused_agents=[a for a in config.paused_agents if a != agent_id])


def requires_mandatory_human_review(*, vendor_tier: str, residual_risk: int) -> tuple[bool, str | None]:
    """Section 6.4's mandatory human-in-the-loop gates, minus the two
    that are already enforced at their own point of action (outbound
    email -- agents/remediation_router.py; stale evidence -- checked
    directly in agents/risk_assessor.py's create_finding since it needs
    per-citation freshness, not just the vendor/risk inputs this function
    sees): a finding can never be closed autonomously for a critical-tier
    vendor, and never above the residual-risk threshold, no matter what
    the autonomy dial says. Returns (requires_human, reason)."""
    from bulwark.config import settings

    if vendor_tier == "critical":
        return True, "vendor is critical-tier"
    if residual_risk >= settings.residual_risk_human_threshold:
        return True, f"residual_risk {residual_risk} >= threshold {settings.residual_risk_human_threshold}"
    return False, None
