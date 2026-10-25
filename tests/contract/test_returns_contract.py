"""Contract §8. Owner: 02-valuation."""
from datetime import date

import pytest

from src.valuations.errors import ProbabilityError
from src.valuations.expected_return import bank_exit_value, probability_weighted, xirr

pytestmark = pytest.mark.owner("02-valuation")


def test_T_RET_01_xirr_matches_excel_convention():
    d0, d1 = date(2026, 10, 25), date(2031, 10, 25)            # 1,826 days
    exit_value = 100 * 1.10 ** (1826 / 365)
    assert xirr([-100.0, exit_value], [d0, d1]) == pytest.approx(0.10, abs=1e-9)


def test_T_RET_02_xirr_with_interim_dividend():
    d = [date(2026, 1, 1), date(2027, 1, 1), date(2028, 1, 1)]
    # -100, +10 after 365 days, +110 after 730 days -> exactly 10%
    assert xirr([-100.0, 10.0, 110.0], d) == pytest.approx(0.10, abs=1e-9)


def test_T_RET_03_exit_value():
    assert bank_exit_value(2.0, 350.0) == pytest.approx(700.0)


def test_T_RET_04_probabilities_are_never_invented():
    vals = {"Bear": -0.05, "Base": 0.10, "Bull": 0.20}
    assert probability_weighted(vals, {"Bear": None, "Base": None, "Bull": None}) is None
    assert probability_weighted(vals, {"Bear": 0.25, "Base": 0.5, "Bull": 0.25}) == pytest.approx(0.0875)
    with pytest.raises(ProbabilityError):
        probability_weighted(vals, {"Bear": 0.3, "Base": 0.5, "Bull": 0.3})
