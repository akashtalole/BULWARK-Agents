import pytest

from bulwark.platform.policy import AutonomyBlocked, enforce_autonomy, pause_agent, resume_agent, set_global_autonomy

# Registry bootstrap + fleet-config reset happens in the autouse
# conftest.py fixture, shared by every test module.


def test_agent_may_act_up_to_its_own_ceiling():
    enforce_autonomy("evidence-collector", 3)  # ceiling is 3 -- must not raise


def test_agent_cannot_exceed_its_own_registered_ceiling():
    with pytest.raises(AutonomyBlocked):
        enforce_autonomy("risk-assessor", 2)  # risk-assessor's ceiling is 1


def test_global_kill_switch_blocks_every_agent_above_the_dial():
    set_global_autonomy(0)
    with pytest.raises(AutonomyBlocked):
        enforce_autonomy("vendor-intake", 1)
    set_global_autonomy(3)


def test_global_dial_is_independent_of_per_agent_ceiling():
    """Even at global level 3, an agent's own ceiling still applies."""
    set_global_autonomy(3)
    with pytest.raises(AutonomyBlocked):
        enforce_autonomy("risk-assessor", 2)


def test_pausing_a_specific_agent_blocks_only_that_agent():
    pause_agent("drift-sentinel")
    with pytest.raises(AutonomyBlocked):
        enforce_autonomy("drift-sentinel", 3)
    enforce_autonomy("evidence-collector", 3)  # unaffected
    resume_agent("drift-sentinel")
    enforce_autonomy("drift-sentinel", 3)  # resumed


def test_set_global_autonomy_rejects_invalid_level():
    with pytest.raises(ValueError):
        set_global_autonomy(7)
