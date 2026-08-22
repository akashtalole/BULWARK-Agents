import pytest

from bulwark.platform.auth import rate_limiter
from bulwark.platform.models import fleet_config_repo
from bulwark.platform.policy import resume_agent, set_global_autonomy
from bulwark.platform.registry import bootstrap_registry, registry


@pytest.fixture(autouse=True)
def _fleet_defaults():
    """The Agent Registry, fleet_config, and the Agent Gateway's rate
    limiter are process-wide singletons (that's the point --
    policy.enforce_autonomy and every route's _authorize() read the same
    ones every call goes through). Reset them before every test so one
    test's kill-switch/circuit-breaker/rate-limit exercise can't leak
    into the next."""
    bootstrap_registry()
    set_global_autonomy(3)
    fleet_config_repo.update(max_daily_token_spend=50.0)
    rate_limiter.reset()
    for record in registry.list():  # every registered agent, not a hardcoded list that can drift out of sync
        resume_agent(record.agent_id)
    yield
