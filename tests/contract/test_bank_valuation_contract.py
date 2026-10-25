"""Contract §2, §3, §10. Owner: 02-valuation. Expected values are hand-derived (spec/test_plan.md)."""
from datetime import date

import pytest

from src.valuations.bank_drivers import BankBaseYear, BankDriverYear, project_bank
from src.valuations.bank_ri import residual_income_value
from src.valuations.blend import blend_fair_value
from src.valuations.ddm import dividend_discount_value
from src.valuations.discounting import cost_of_equity_capm, discount_factor
from src.valuations.errors import MethodNotAllowedError, TerminalGrowthError, ValuationError
from src.valuations.justified_pb import justified_pb
from src.valuations.method_selection import validate_method_for_business_model
from src.valuations.peer_relative import peer_relative_value
from src.valuations.rollforward import roll_forward_value
from src.valuations.terminal import gordon_terminal_value, sensitivity_grid, terminal_flag

pytestmark = pytest.mark.owner("02-valuation")
approx = pytest.approx

# Steady state: BV0 100, r 12%, ROE 15%, payout 50% -> g = 7.5%. Closed form: 100 + 3/0.045 = 166.6667
R, ROE, PAYOUT = 0.12, 0.15, 0.50
G = ROE * (1 - PAYOUT)
STEADY = 100 + (ROE - R) * 100 / (R - G)


def _steady_path(n=5):
    bv, eps, dps = 100.0, [], []
    for _ in range(n):
        e = ROE * bv
        eps.append(e); dps.append(e * PAYOUT); bv += e * (1 - PAYOUT)
    return eps, dps


def test_T_BNK_00_capm_and_discount_factor():
    assert cost_of_equity_capm(0.065, 1.1, 0.06) == approx(0.131)
    assert discount_factor(0.12, 2.0) == approx(1 / 1.12 ** 2)


def test_T_BNK_01_ri_ddm_justified_pb_agree_in_steady_state():
    eps, dps = _steady_path()
    ri = residual_income_value(100.0, eps, dps, R, ROE, G)
    ddm = dividend_discount_value(100.0, eps, dps, R, ROE, PAYOUT, G)
    assert STEADY == approx(166.6666666667)
    assert ri.value_at_anchor == approx(STEADY, rel=1e-9)
    assert ddm.value_at_anchor == approx(STEADY, rel=1e-9)
    assert justified_pb(ROE, R, G) * 100 == approx(STEADY, rel=1e-9)
    assert ri.terminal_value_share == approx(0.3258458538, rel=1e-7)


def test_T_BNK_02_ri_non_steady_hand_computed():
    # BV: 100 -> 112 -> 125.2 -> 139.6 ; RI: 2.0, 1.94, 1.724 ; RI_4 = 0.01 x 139.6 ; TV = 1.396/0.08
    ri = residual_income_value(100.0, [15.0, 16.5, 18.0], [3.0, 3.3, 3.6], 0.13, 0.14, 0.05)
    assert ri.book_values == approx((100.0, 112.0, 125.2, 139.6))
    assert ri.residual_incomes == approx((2.0, 1.94, 1.724))
    assert ri.pv_residual_income == approx(4.48403454993669)
    assert ri.terminal_value == approx(17.45)
    assert ri.pv_terminal_value == approx(12.0937253317458)
    assert ri.value_at_anchor == approx(116.577759881683)
    assert ri.terminal_value_share == approx(12.0937253317458 / 116.577759881683)


def test_T_BNK_03_terminal_roe_equal_to_cost_of_equity_gives_zero_terminal():
    ri = residual_income_value(100.0, [15.0], [3.0], 0.13, 0.13, 0.05)
    assert ri.pv_terminal_value == approx(0.0, abs=1e-12)


@pytest.mark.parametrize("g", [0.12, 0.13])
def test_T_BNK_04_growth_not_below_rate_is_rejected(g):
    eps, dps = _steady_path()
    with pytest.raises(TerminalGrowthError):
        residual_income_value(100.0, eps, dps, R, ROE, g)
    with pytest.raises(TerminalGrowthError):
        justified_pb(ROE, R, g)
    with pytest.raises(TerminalGrowthError):
        gordon_terminal_value(1.0, R, g)


def test_T_BNK_05_roll_forward_with_dividend_after_anchor():
    v = roll_forward_value(STEADY, date(2026, 3, 31), date(2026, 10, 25), R,
                           dividends=[(date(2026, 7, 15), 5.0), (date(2026, 3, 1), 99.0), (date(2026, 11, 1), 99.0)])
    tau = 208 / 365.25
    tau_d = (date(2026, 10, 25) - date(2026, 7, 15)).days / 365.25
    assert v == approx(STEADY * 1.12 ** tau - 5.0 * 1.12 ** tau_d)   # 172.6168...
    assert v == approx(172.616846041628)


def test_T_BNK_06_fcff_dcf_is_not_a_bank_primary_method():
    with pytest.raises(MethodNotAllowedError):
        validate_method_for_business_model("Deposit-taking bank", "FCFF DCF (WACC)")
    validate_method_for_business_model("Deposit-taking bank", "Residual Income")  # no raise


def test_T_BNK_07_peer_relative_value_and_flags():
    ok = peer_relative_value(2.5, 400.0, n_valid=5)
    assert ok.value == approx(1000.0) and ok.flag == "PASS"
    thin = peer_relative_value(2.5, 400.0, n_valid=2)
    assert thin.value == approx(1000.0) and thin.flag == "WARNING"
    none = peer_relative_value(None, 400.0, n_valid=0)
    assert none.value is None and none.flag == "MISSING"   # never 0


def test_T_BNK_08_blend_weights():
    assert blend_fair_value({"RI": 100.0, "DDM": 80.0}, {"RI": 1.0, "DDM": 0.0}) == approx(100.0)
    assert blend_fair_value({"RI": 100.0, "DDM": 80.0}, {"RI": 0.75, "DDM": 0.25}) == approx(95.0)
    assert blend_fair_value({"RI": 100.0, "DDM": None}, {"RI": 0.5, "DDM": 0.5}) is None
    with pytest.raises(ValuationError):
        blend_fair_value({"RI": 100.0}, {"RI": 0.9})


def test_T_BNK_09_terminal_flag_and_grid():
    assert terminal_flag(0.80, 0.75) == "WARNING"
    assert terminal_flag(0.50, 0.75) == "PASS"
    grid = sensitivity_grid(lambda r, g: 1.0 / (r - g), [0.11, 0.12], [0.11, 0.05])
    assert grid[0][0] is None                        # g = r
    assert grid[1][1] == approx(1 / 0.07)


def test_T_BNK_10_driver_projection_one_year_hand_computed():
    base = BankBaseYear(advances=1000.0, iea_to_advances=1.5, non_interest_income=20.0,
                        operating_expenses=40.0, equity=200.0, diluted_shares=100_000_000)
    yr = BankDriverYear(advance_growth=0.10, iea_to_advances=1.5, nim=0.04, non_interest_income_growth=0.10,
                        opex_growth=0.05, credit_cost=0.01, tax_rate=0.25, payout_ratio=0.20)
    (p,) = project_bank(base, [yr])
    assert p.advances == approx(1100.0)
    assert p.nii == approx(63.0)          # 0.04 x (1500 + 1650) / 2
    assert p.ppop == approx(43.0)         # 63 + 22 - 42
    assert p.provisions == approx(10.5)   # 0.01 x 1050
    assert p.pat == approx(24.375)
    assert p.eps == approx(2.4375)        # 24.375 Cr x 1e7 / 1e8 shares
    assert p.dps == approx(0.4875)
    assert p.equity == approx(219.5)
    assert p.bvps == approx(21.95)
    assert p.roe == approx(24.375 / 209.75)
