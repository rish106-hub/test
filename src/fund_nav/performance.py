"""Contract §7.9 fund performance metrics. Series are (date, value) sorted ascending."""
from __future__ import annotations

from datetime import date
from typing import Sequence

Series = Sequence[tuple[date, float]]


def period_return(series: Series, start: date, end: date) -> float | None: raise NotImplementedError("03-nav")
def cagr(series: Series, start: date, end: date) -> float | None: raise NotImplementedError("03-nav")
def annualised_volatility(series: Series) -> float: raise NotImplementedError("03-nav")
def max_drawdown(series: Series) -> float: raise NotImplementedError("03-nav")
def downside_deviation(series: Series, mar_annual: float) -> float: raise NotImplementedError("03-nav")
def sharpe(cagr_value: float, rf: float, vol: float) -> float | None: raise NotImplementedError("03-nav")
def sortino(cagr_value: float, mar_annual: float, downside_dev: float) -> float | None: raise NotImplementedError("03-nav")
def rolling_returns(series: Series, window_days: int) -> list[tuple[date, float]]: raise NotImplementedError("03-nav")
