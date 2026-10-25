"""Contract §7.6 Method 4 hypothetical rebalanced portfolio."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

CASH_ROUND_DIGITS = 6   # cash within a millionth of a rupee of zero is not overspending


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
    fair_value_inr: float | None     # None: the security is unvalued; it is carried at market in HRPV_Fair


@dataclass(frozen=True)
class HypoPortfolioResult:
    lines: tuple[HypoLineResult, ...]
    cash_remaining_inr: float
    value_market_inr: float
    value_fair_inr: float
    status: str   # PASS | FAIL (negative cash)


def build_hypothetical_portfolio(capital_inr: float, lines: Sequence[HypoLineInput],
                                 transaction_cost_pct: float) -> HypoPortfolioResult:
    out, spent, mkt, fair = [], 0.0, 0.0, 0.0
    for l in lines:
        buy = l.assumed_buy_price_inr if l.assumed_buy_price_inr is not None else l.scenario_price_inr
        if buy <= 0:
            raise ValueError(f"{l.security_id}: buy price must be positive")
        if l.quantity_override is not None:
            qty = l.quantity_override
        else:
            qty = math.floor(capital_inr * l.effective_weight / (buy * (1 + transaction_cost_pct)))
        cost = qty * buy
        fee = cost * transaction_cost_pct
        mv = qty * l.scenario_price_inr
        fv = None if l.fair_value_inr is None else qty * l.fair_value_inr
        out.append(HypoLineResult(l.security_id, qty, cost, fee, mv, fv))
        spent += cost + fee
        mkt += mv
        fair += mv if fv is None else fv
    cash = capital_inr - spent
    return HypoPortfolioResult(lines=tuple(out), cash_remaining_inr=cash, value_market_inr=mkt + cash,
                               value_fair_inr=fair + cash,
                               status="PASS" if round(cash, CASH_ROUND_DIGITS) >= 0 else "FAIL")
