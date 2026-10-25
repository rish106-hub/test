"""Contract §3.2 Residual Income (primary bank method, R004)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RIResult:
    value_at_anchor: float        # V_A, per share, INR
    pv_residual_income: float
    terminal_value: float         # TV_N, undiscounted, at end of year N
    pv_terminal_value: float
    terminal_value_share: float   # PV_TV / V_A
    book_values: tuple[float, ...]       # BV_0 .. BV_N
    residual_incomes: tuple[float, ...]  # RI_1 .. RI_N


def residual_income_value(bv0: float, eps: Sequence[float], dps: Sequence[float], cost_of_equity: float,
                          terminal_roe: float, terminal_growth: float) -> RIResult:
    """Per-share RI value at the anchor date. eps/dps are years 1..N after the anchor."""
    raise NotImplementedError("02-valuation: contract §3.2")
