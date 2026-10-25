"""Contract §3.1 anchor-date to valuation-date roll-forward and equity bridge (D-007, D-025)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from src.common.enums import CheckResult
from src.common.units import year_fraction
from src.valuations.errors import ValuationError


def dividends_in_window(dividends: Sequence[tuple[date, float]], start: date, end: date) -> list[tuple[date, float]]:
    """Dividends whose ex-date d satisfies start < d <= end."""
    return [(d, dps) for d, dps in dividends if start < d <= end]


def roll_forward_value(value_at_anchor: float, anchor_date: date, valuation_date: date, cost_of_equity: float,
                       dividends: Sequence[tuple[date, float]] = ()) -> float:
    """dividends: (ex_date, DPS). Only ex-dates in (anchor_date, valuation_date] are deducted,
    each compounded from its ex-date to the valuation date. tau = days / 365.25."""
    if valuation_date < anchor_date:
        raise ValuationError(f"valuation date {valuation_date} is before the anchor date {anchor_date}")
    r = cost_of_equity
    grown = value_at_anchor * (1.0 + r) ** year_fraction(anchor_date, valuation_date)
    paid = sum(dps * (1.0 + r) ** year_fraction(d, valuation_date)
               for d, dps in dividends_in_window(dividends, anchor_date, valuation_date))
    return grown - paid


@dataclass(frozen=True)
class InterimResult:
    """One reported, discrete interim period after the anchor (e.g. Q1FY2027), per diluted share."""
    period_end: date
    eps: float
    source_id: str = ""


@dataclass(frozen=True)
class EquityBridge:
    """Contract §3.1a. Each line keeps its own basis: reported, forecast or estimate."""
    bv_reported_at_anchor: float           # historical, as of anchor_date
    latest_results_period_end: date        # R: anchor_date when no interim period has been reported
    eps_reported_after_anchor: float       # Σ reported interim EPS with period_end in (A, V]
    eps_forecast_stub: float               # EPS_1 x days(R, V) / days(A, FYE_1)
    dividends_paid: float                  # Σ DPS with ex-date in (A, V]
    bv_estimated_at_valuation: float       # estimate, as of valuation_date
    interim_eps_deviation_pct: float | None    # None when no interim period has been reported
    forecast_update_flag: str              # PASS | WARNING
    financials_age_days: int               # V - R
    anchor_age_days: int                   # V - A
    freshness_status: str                  # PASS | STALE | FAIL (§3.1b)


def forecast_year_bounds(anchor_date: date, eps_forecast: Sequence[tuple[date, float]]) -> list[tuple[date, date, float]]:
    """[(start, end, EPS_t)] for t = 1..N: FY_t = (FYE_{t-1}, FYE_t] with FYE_0 = anchor_date."""
    years, start = [], anchor_date
    for fye, eps in sorted(eps_forecast, key=lambda x: x[0]):
        if fye <= start:
            raise ValuationError(f"forecast year end {fye} is not after {start}")
        years.append((start, fye, float(eps)))
        start = fye
    return years


def accrued_forecast_eps(years: Sequence[tuple[date, date, float]], start: date, end: date) -> float:
    """Σ_t EPS_t x days((start, end] ∩ FY_t) / days(FY_t): forecast EPS accrued by calendar day."""
    total = 0.0
    for fy_start, fy_end, eps in years:
        overlap = (min(end, fy_end) - max(start, fy_start)).days
        if overlap > 0:
            total += eps * overlap / (fy_end - fy_start).days
    return total


def freshness_status(financials_age_days: int, anchor_age_days: int, financials_stale_days: int,
                     anchor_max_age_days: int) -> str:
    """Contract §3.1b: FAIL if the anchor is overdue, else STALE if the latest results are old, else PASS."""
    if anchor_age_days > anchor_max_age_days:
        return CheckResult.FAIL.value
    if financials_age_days > financials_stale_days:
        return CheckResult.STALE.value
    return CheckResult.PASS.value


def equity_bridge(bv_at_anchor: float, anchor_date: date, eps_forecast: Sequence[tuple[date, float]],
                  valuation_date: date, interim_results: Sequence[InterimResult] = (),
                  dividends: Sequence[tuple[date, float]] = (), *, interim_dev_warn: float = 0.15,
                  financials_stale_days: int = 135, anchor_max_age_days: int = 425) -> EquityBridge:
    """Bridge reported BVPS at A to estimated BVPS at V (contract §3.1a, §3.1b).

    eps_forecast: (fiscal_year_end, EPS) for forecast years t = 1..N, contiguous from anchor_date.
    Forecast EPS accrues linearly by calendar day within each fiscal year. Raises ValuationError
    when valuation_date is after the last forecast year end."""
    a, v = anchor_date, valuation_date
    years = forecast_year_bounds(a, eps_forecast)
    if not years:
        raise ValuationError("equity bridge needs at least one forecast year")
    if v < a:
        raise ValuationError(f"valuation date {v} is before the anchor date {a}")
    if v > years[-1][1]:
        raise ValuationError(f"valuation date {v} is after the last forecast year end {years[-1][1]}: "
                             "the model has no forecast covering it (contract §3.1a)")
    reported = [i for i in interim_results if a < i.period_end <= v]
    r = max((i.period_end for i in reported), default=a)
    eps_reported = sum(i.eps for i in reported)
    stub = accrued_forecast_eps(years, r, v)
    divs = sum(dps for _, dps in dividends_in_window(dividends, a, v))
    bv_v = bv_at_anchor + eps_reported + stub - divs
    deviation, flag = None, CheckResult.PASS.value
    if reported:
        forecast_ar = accrued_forecast_eps(years, a, r)
        if forecast_ar == 0:
            flag = CheckResult.WARNING.value      # nothing to compare against: review the year-1 drivers
        else:
            deviation = eps_reported / forecast_ar - 1.0
            if abs(deviation) > interim_dev_warn:
                flag = CheckResult.WARNING.value
    fin_age, anchor_age = (v - r).days, (v - a).days
    return EquityBridge(
        bv_reported_at_anchor=bv_at_anchor, latest_results_period_end=r, eps_reported_after_anchor=eps_reported,
        eps_forecast_stub=stub, dividends_paid=divs, bv_estimated_at_valuation=bv_v,
        interim_eps_deviation_pct=deviation, forecast_update_flag=flag, financials_age_days=fin_age,
        anchor_age_days=anchor_age,
        freshness_status=freshness_status(fin_age, anchor_age, financials_stale_days, anchor_max_age_days))
