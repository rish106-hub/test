"""Contract §8 expected five-year return."""
from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from src.common.units import DAYS_PER_YEAR_XIRR
from src.valuations.errors import ProbabilityError, ValuationError

PROBABILITY_SUM_TOL = 1e-9


def _npv(rate: float, cashflows: Sequence[float], years: Sequence[float]) -> float:
    return sum(cf / (1.0 + rate) ** y for cf, y in zip(cashflows, years))


def xirr(cashflows: Sequence[float], dates: Sequence[date]) -> float:
    """Excel XIRR convention: sum CF_i / (1 + r) ** ((d_i - d_0).days / 365) = 0.

    d_0 is the first date in the list, as in Excel. Solved by bisection on a bracket, then
    polished, to ~1e-14; raises ValuationError when the flows have no sign change."""
    if len(cashflows) != len(dates) or len(cashflows) < 2:
        raise ValuationError("xirr needs at least two cash flows with one date each")
    if not (any(cf > 0 for cf in cashflows) and any(cf < 0 for cf in cashflows)):
        raise ValuationError("xirr needs at least one positive and one negative cash flow")
    d0 = dates[0]
    years = [(d - d0).days / DAYS_PER_YEAR_XIRR for d in dates]
    if any(y < 0 for y in years):
        raise ValuationError("no cash-flow date may precede the first date (Excel XIRR)")
    lo, hi = -0.999999999, 1.0
    f_lo = _npv(lo, cashflows, years)
    while _npv(hi, cashflows, years) * f_lo > 0:
        hi *= 2.0
        if hi > 1e6:
            raise ValuationError("xirr did not bracket a root")
    for _ in range(400):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, cashflows, years)
        if f_mid == 0 or (hi - lo) < 1e-15:
            return mid
        if f_mid * f_lo > 0:
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def bank_exit_value(exit_pb: float, bvps_at_exit: float) -> float:
    """Exit_Value_T = Exit_PB x BVPS_T (Exit_PB is an explicit user assumption; contract §8)."""
    return exit_pb * bvps_at_exit


def reinvested_total_return(price_0: float, start: date, end: date, dividends: Sequence[tuple[date, float]],
                            exit_value: float, reinvestment_rate: float) -> float:
    """Annualised total return with dividends reinvested at r_reinv to the exit date (Excel days/365):
    W_T = Exit + Σ DPS_d x (1 + r_reinv) ** ((T - d) / 365); TR = (W_T / P_0) ** (365 / (T - V)) - 1."""
    if price_0 <= 0:
        raise ValuationError("price must be positive")
    days = (end - start).days
    if days <= 0:
        raise ValuationError("exit date must be after the start date")
    wealth = exit_value + sum(dps * (1.0 + reinvestment_rate) ** ((end - d).days / DAYS_PER_YEAR_XIRR)
                              for d, dps in dividends)
    return (wealth / price_0) ** (DAYS_PER_YEAR_XIRR / days) - 1.0


def probability_weighted(values: Mapping[str, float | None], probabilities: Mapping[str, float | None]) -> float | None:
    """None if any probability is blank; ProbabilityError if entered and sum != 1 (1e-9)."""
    if not probabilities or any(p is None for p in probabilities.values()):
        return None
    if any(p < 0 or p > 1 for p in probabilities.values()):
        raise ProbabilityError(f"probabilities must lie in [0, 1]: {dict(probabilities)}")
    total = sum(probabilities.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOL:
        raise ProbabilityError(f"scenario probabilities sum to {total}, not 1")
    out = 0.0
    for case, p in probabilities.items():
        if p == 0:
            continue
        v = values.get(case)
        if v is None:
            return None
        out += p * v
    return out
