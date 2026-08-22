from bulwark.platform.models import fleet_config_repo
from bulwark.platform.spend import SpendLedger, check_circuit_breaker, estimate_cost_usd, spend_ledger


def test_estimate_cost_usd_scales_with_tokens():
    assert estimate_cost_usd(0, 0) == 0.0
    assert estimate_cost_usd(1000, 0) > 0
    assert estimate_cost_usd(0, 1000) > estimate_cost_usd(1000, 0)  # candidates rate > prompt rate


def test_ledger_accumulates_across_records():
    ledger = SpendLedger()
    ledger.reset_today()
    first = ledger.record(1000, 500)
    second = ledger.record(1000, 500)
    assert second.tokens_in == first.tokens_in + 1000
    assert second.cost_usd > first.cost_usd


def test_circuit_breaker_trips_and_forces_autonomy_to_zero():
    spend_ledger.reset_today()
    fleet_config_repo.update(autonomy_level=3, max_daily_token_spend=0.001)
    spend_ledger.record(1_000_000, 500_000)  # comfortably over a $0.001 cap

    tripped = check_circuit_breaker()

    assert tripped is True
    assert fleet_config_repo.get().autonomy_level == 0
    fleet_config_repo.update(autonomy_level=3, max_daily_token_spend=50.0)


def test_circuit_breaker_does_not_trip_under_cap():
    spend_ledger.reset_today()
    fleet_config_repo.update(autonomy_level=3, max_daily_token_spend=50.0)
    spend_ledger.record(10, 5)

    tripped = check_circuit_breaker()

    assert tripped is False
    assert fleet_config_repo.get().autonomy_level == 3
