"""Contract §3.3 Dividend Discount Model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.valuations.bank_ri import clean_surplus_book_values
from src.valuations.discounting import discount_factor
from src.valuations.errors import ValuationError
from src.valuations.terminal import gordon_terminal_value, require_growth_below_rate


@dataclass(frozen=True)
class DDMResult:
    value_at_anchor: float
    pv_dividends: float
    terminal_value: float
    pv_terminal_value: float
    terminal_value_share: float


def dividend_discount_value(bv0: float, eps: Sequence[float], dps: Sequence[float], cost_of_equity: float,
                            terminal_roe: float, terminal_payout: float, terminal_growth: float) -> DDMResult:
    """BV_N is rolled by clean surplus from bv0/eps/dps; DPS_{N+1} = ROE_T * BV_N * payout_T."""
    r, g = cost_of_equity, terminal_growth
    require_growth_below_rate(r, g)
    bvs = clean_surplus_book_values(bv0, eps, dps)
    n = len(dps)
    pv_d = sum(d * discount_factor(r, t + 1) for t, d in enumerate(dps))
    tv = gordon_terminal_value(terminal_roe * bvs[n] * terminal_payout, r, g)
    pv_tv = tv * discount_factor(r, n)
    value = pv_d + pv_tv
    if value == 0:
        raise ValuationError("DDM value at anchor is zero; terminal value share undefined")
    return DDMResult(value, pv_d, tv, pv_tv, pv_tv / value)
