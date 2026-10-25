"""Contract §7.6 Method 4 hypothetical rebalanced portfolio."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class HypoLineInput:
    security_id: str
    effective_weight: float
    scenario_price_inr: float
    fair_value_inr: float | None
    assumed_buy_price_inr: float | None = None
    quantity_override: float | None = None


@dataclass(frozen=True)
class HypoLineResult:
    security_id: str
    quantity: float
    cost_inr: float
    fee_inr: float
    market_value_inr: float
    fair_value_inr: float | None


@dataclass(frozen=True)
class HypoPortfolioResult:
    lines: tuple[HypoLineResult, ...]
    cash_remaining_inr: float
    value_market_inr: float
    value_fair_inr: float
    status: str   # PASS | FAIL (negative cash)


def build_hypothetical_portfolio(capital_inr: float, lines: Sequence[HypoLineInput],
                                 transaction_cost_pct: float) -> HypoPortfolioResult:
    raise NotImplementedError("03-nav: contract §7.6")
