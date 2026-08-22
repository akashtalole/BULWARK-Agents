"""Circuit breaker (section 8): a daily token-spend cap that trips the
kill switch. "Breach -> all agents drop to L0" is the spec's exact
wording -- this module is what makes that literally true rather than
aspirational: ``check_circuit_breaker`` calls the same
``policy.set_global_autonomy(0)`` the manual kill switch uses.

Rates below are illustrative placeholders (clearly labeled, same honesty
standard as this build's other mock data) -- real Gemini pricing should
replace them before this cap means anything in production; what's real
is the mechanism (accumulate real per-call token counts from ADK's
``usage_metadata``, compare against a cap, trip the breaker), not the
dollar figures.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from bulwark.platform.models import fleet_config_repo
from bulwark.platform.store import DocumentStore

logger = logging.getLogger("bulwark.spend")

# Illustrative $/1K-token rates -- NOT verified real Gemini pricing.
_RATE_PER_1K_TOKENS_USD = {
    "prompt": 0.001,
    "candidates": 0.003,
}


def estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    return round(
        (tokens_in / 1000) * _RATE_PER_1K_TOKENS_USD["prompt"] + (tokens_out / 1000) * _RATE_PER_1K_TOKENS_USD["candidates"],
        6,
    )


@dataclass
class DailySpend:
    date: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class SpendLedger:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self._store = store or DocumentStore("spend_ledger")

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def record(self, tokens_in: int, tokens_out: int) -> DailySpend:
        today = self._today()
        cost = estimate_cost_usd(tokens_in, tokens_out)
        current = self._store.get(today) or {"date": today, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        updated = DailySpend(
            date=today,
            tokens_in=current["tokens_in"] + tokens_in,
            tokens_out=current["tokens_out"] + tokens_out,
            cost_usd=round(current["cost_usd"] + cost, 6),
        )
        self._store.set(today, asdict(updated))
        return updated

    def today(self) -> DailySpend:
        data = self._store.get(self._today())
        return DailySpend(**data) if data else DailySpend(date=self._today())

    def reset_today(self) -> None:
        self._store.set(self._today(), asdict(DailySpend(date=self._today())))


spend_ledger = SpendLedger()


def check_circuit_breaker() -> bool:
    """Call after recording spend. Returns True if the breaker just
    tripped (or was already tripped) this call, having forced the global
    autonomy dial to 0 as a side effect."""
    from bulwark.platform.policy import set_global_autonomy  # local import: avoid a policy<->spend import cycle

    config = fleet_config_repo.get()
    spend = spend_ledger.today()
    if spend.cost_usd < config.max_daily_token_spend:
        return False

    if config.autonomy_level != 0:
        logger.warning(
            "circuit breaker tripped: daily spend $%.4f >= cap $%.2f -- forcing autonomy_level to 0",
            spend.cost_usd, config.max_daily_token_spend,
        )
        set_global_autonomy(0)
    return True
