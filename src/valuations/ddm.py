"""Contract §3.3 Dividend Discount Model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


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
    raise NotImplementedError("02-valuation: contract §3.3")
