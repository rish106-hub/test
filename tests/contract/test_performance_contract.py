"""Contract §7.9. Owner: 03-nav."""
from datetime import date

import pytest

from src.fund_nav import performance as P

pytestmark = pytest.mark.owner("03-nav")
SERIES = [(date(2024, 1, 1), 100.0), (date(2024, 6, 1), 120.0), (date(2025, 1, 1), 90.0),
          (date(2025, 6, 1), 95.0), (date(2025, 12, 31), 130.0)]


def test_T_PERF_01_returns():
    assert P.period_return(SERIES, date(2024, 1, 1), date(2025, 12, 31)) == pytest.approx(0.30)
    assert P.cagr(SERIES, date(2024, 1, 1), date(2025, 12, 31)) == pytest.approx(0.140175425099138)


def test_T_PERF_02_drawdown():
    assert P.max_drawdown(SERIES) == pytest.approx(-0.25)


def test_T_PERF_03_volatility_and_downside():
    assert P.annualised_volatility(SERIES) == pytest.approx(4.16339918050462)
    assert P.downside_deviation(SERIES, 0.05) == pytest.approx(1.98585037779810)


def test_T_PERF_04_missing_history_is_none_not_zero():
    assert P.period_return(SERIES, date(2020, 1, 1), date(2025, 12, 31)) is None
