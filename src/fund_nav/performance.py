"""Contract §7.9 fund performance metrics. Series are (date, value) sorted ascending.

A metric is None, never 0 or a guess, when the series does not cover the requested window.
Expense ratios are already inside NAV and are never deducted again.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Sequence

Series = Sequence[tuple[date, float]]

TRADING_DAYS = 252
DAYS_PER_YEAR_RETURN = 365   # CAGR exponent, contract §7.9


def value_on_or_before(series: Series, d: date) -> float | None:
    """Last observation dated on or before d, or None if the series starts after d."""
    best = None
    for dt, v in series:
        if dt > d:
            break
        best = v
    return best


def _covers(series: Series, start: date, end: date) -> bool:
    return bool(series) and series[0][0] <= start and series[-1][0] >= end and start < end


def period_return(series: Series, start: date, end: date) -> float | None:
    """NAV_end / NAV_start - 1, None unless the series has history at start and runs to end."""
    if not _covers(series, start, end):
        return None
    return value_on_or_before(series, end) / value_on_or_before(series, start) - 1


def cagr(series: Series, start: date, end: date) -> float | None:
    if not _covers(series, start, end):
        return None
    days = (end - start).days
    ratio = value_on_or_before(series, end) / value_on_or_before(series, start)
    return ratio ** (DAYS_PER_YEAR_RETURN / days) - 1


def simple_returns(series: Series) -> list[float]:
    return [series[i][1] / series[i - 1][1] - 1 for i in range(1, len(series))]


def annualised_volatility(series: Series) -> float | None:
    """Sample stdev of simple returns between consecutive observations x sqrt(252); None below 2 returns."""
    r = simple_returns(series)
    if len(r) < 2:
        return None
    return statistics.stdev(r) * math.sqrt(TRADING_DAYS)


def max_drawdown(series: Series) -> float | None:
    if not series:
        return None
    peak, worst = series[0][1], 0.0
    for _, v in series:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def downside_deviation(series: Series, mar_annual: float) -> float | None:
    """sqrt(mean(min(r - MAR_daily, 0)^2)) x sqrt(252); the mean is over all returns."""
    r = simple_returns(series)
    if not r:
        return None
    mar_daily = (1 + mar_annual) ** (1 / TRADING_DAYS) - 1
    return math.sqrt(sum(min(x - mar_daily, 0.0) ** 2 for x in r) / len(r)) * math.sqrt(TRADING_DAYS)


def sharpe(cagr_value: float, rf: float, vol: float) -> float | None:
    if cagr_value is None or vol is None or vol == 0:
        return None
    return (cagr_value - rf) / vol


def sortino(cagr_value: float, mar_annual: float, downside_dev: float) -> float | None:
    if cagr_value is None or downside_dev is None or downside_dev == 0:
        return None
    return (cagr_value - mar_annual) / downside_dev


def rolling_returns(series: Series, window_days: int) -> list[tuple[date, float]]:
    """Return(h) at every observation date that has a full window of history behind it."""
    out = []
    if not series:
        return out
    first = series[0][0]
    for dt, v in series:
        start = dt - timedelta(days=window_days)
        if start < first:
            continue
        out.append((dt, v / value_on_or_before(series, start) - 1))
    return out


def window(series: Series, start: date, end: date) -> list[tuple[date, float]]:
    """Observations with start <= date <= end (the series a window's risk metrics are computed from)."""
    return [(d, v) for d, v in series if start <= d <= end]
