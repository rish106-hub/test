"""Contract §3.2 Residual Income (primary bank method, R004)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.valuations.discounting import discount_factor
from src.valuations.errors import ValuationError
from src.valuations.terminal import gordon_terminal_value, require_growth_below_rate


@dataclass(frozen=True)
class RIResult:
    value_at_anchor: float        # V_A, per share, INR
    pv_residual_income: float
    terminal_value: float         # TV_N, undiscounted, at end of year N
    pv_terminal_value: float
    terminal_value_share: float   # PV_TV / V_A
    book_values: tuple[float, ...]       # BV_0 .. BV_N
    residual_incomes: tuple[float, ...]  # RI_1 .. RI_N


def clean_surplus_book_values(bv0: float, eps: Sequence[float], dps: Sequence[float]) -> tuple[float, ...]:
    """BV_t = BV_{t-1} + EPS_t - DPS_t, returned as BV_0 .. BV_N."""
    if len(eps) != len(dps) or not eps:
        raise ValuationError("eps and dps must be non-empty and of equal length (years 1..N)")
    bvs = [float(bv0)]
    for e, d in zip(eps, dps):
        bvs.append(bvs[-1] + e - d)
    return tuple(bvs)


def residual_income_value(bv0: float, eps: Sequence[float], dps: Sequence[float], cost_of_equity: float,
                          terminal_roe: float, terminal_growth: float) -> RIResult:
    """Per-share RI value at the anchor date. eps/dps are years 1..N after the anchor."""
    r, g = cost_of_equity, terminal_growth
    require_growth_below_rate(r, g)
    bvs = clean_surplus_book_values(bv0, eps, dps)
    n = len(eps)
    ris = tuple(eps[t] - r * bvs[t] for t in range(n))                 # beginning-of-year book value
    pv_ri = sum(ri * discount_factor(r, t + 1) for t, ri in enumerate(ris))
    tv = gordon_terminal_value((terminal_roe - r) * bvs[n], r, g)      # RI_{N+1} / (r - g)
    pv_tv = tv * discount_factor(r, n)
    value = bvs[0] + pv_ri + pv_tv
    if value == 0:
        raise ValuationError("RI value at anchor is zero; terminal value share undefined")
    return RIResult(value, pv_ri, tv, pv_tv, pv_tv / value, bvs, ris)
