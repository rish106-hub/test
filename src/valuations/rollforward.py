"""Contract §3.1 anchor-date to valuation-date roll-forward and equity bridge (D-007, D-025)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


def roll_forward_value(value_at_anchor: float, anchor_date: date, valuation_date: date, cost_of_equity: float,
                       dividends: Sequence[tuple[date, float]] = ()) -> float:
    """dividends: (ex_date, DPS). Only ex-dates in (anchor_date, valuation_date] are deducted,
    each compounded from its ex-date to the valuation date. tau = days / 365.25."""
    raise NotImplementedError("02-valuation: contract §3.1")


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


def equity_bridge(bv_at_anchor: float, anchor_date: date, eps_forecast: Sequence[tuple[date, float]],
                  valuation_date: date, interim_results: Sequence[InterimResult] = (),
                  dividends: Sequence[tuple[date, float]] = (), *, interim_dev_warn: float = 0.15,
                  financials_stale_days: int = 135, anchor_max_age_days: int = 425) -> EquityBridge:
    """Bridge reported BVPS at A to estimated BVPS at V (contract §3.1a, §3.1b).

    eps_forecast: (fiscal_year_end, EPS) for forecast years t = 1..N, contiguous from anchor_date.
    Forecast EPS accrues linearly by calendar day within each fiscal year. Raises ValuationError
    when valuation_date is after the last forecast year end."""
    raise NotImplementedError("02-valuation: contract §3.1a")
