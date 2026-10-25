"""I layer, part 1: the 05-qa clean-room implementation reproduces every hand-derived contract
case (spec/test_plan.md §C). This proves that an independent reader of the contract reaches the
same numbers, without any worker code. Check IDs mirror the contract case: I-BNK-11 ↔ T-BNK-11.
"""
import dataclasses
from datetime import date

import pytest

from tests.contract import cases as K
from tests.independent.cleanroom import controls as QC, nav as QN, valuation as QV

approx = pytest.approx
R, ROE, PAYOUT = 0.12, 0.15, 0.50
G = ROE * (1 - PAYOUT)


def _steady(n=5):
    bv, eps, dps = 100.0, [], []
    for _ in range(n):
        e = ROE * bv
        eps.append(e); dps.append(e * PAYOUT); bv += e * (1 - PAYOUT)
    return eps, dps


def _with(lines, line_id, **ch):
    return [dataclasses.replace(l, **ch) if l.line_id == line_id else l for l in lines]


# --------------------------------------------------------------------------- bank §2-3, §10
def test_I_BNK_00_capm_and_discount_factor():
    assert QV.capm(0.065, 1.1, 0.06) == approx(0.131)
    assert QV.discount_factor(0.12, 2.0) == approx(1 / 1.12 ** 2)


def test_I_BNK_01_steady_state_ri_ddm_pb_agree():
    eps, dps = _steady()
    ri = QV.residual_income(100.0, eps, dps, R, ROE, G)
    ddm = QV.dividend_discount(100.0, eps, dps, R, ROE, PAYOUT, G)
    assert ri.value_at_anchor == approx(166.6666666667, rel=1e-9)
    assert ddm.value_at_anchor == approx(166.6666666667, rel=1e-9)
    assert QV.justified_pb(ROE, R, G) * 100 == approx(166.6666666667, rel=1e-9)
    assert ri.terminal_value_share == approx(0.3258458538, rel=1e-7)


def test_I_BNK_02_ri_non_steady():
    ri = QV.residual_income(100.0, [15.0, 16.5, 18.0], [3.0, 3.3, 3.6], 0.13, 0.14, 0.05)
    assert ri.book_values == approx((100.0, 112.0, 125.2, 139.6))
    assert ri.residual_incomes == approx((2.0, 1.94, 1.724))
    assert ri.pv_residual_income == approx(4.48403454993669)
    assert ri.terminal_value == approx(17.45)
    assert ri.pv_terminal_value == approx(12.0937253317458)
    assert ri.value_at_anchor == approx(116.577759881683)


def test_I_BNK_03_terminal_roe_equal_to_r():
    assert QV.residual_income(100.0, [15.0], [3.0], 0.13, 0.13, 0.05).pv_terminal_value == approx(0.0, abs=1e-12)


@pytest.mark.parametrize("g", [0.12, 0.13])
def test_I_BNK_04_g_not_below_r_rejected(g):
    eps, dps = _steady()
    for fn in (lambda: QV.residual_income(100.0, eps, dps, R, ROE, g), lambda: QV.justified_pb(ROE, R, g),
               lambda: QV.gordon(1.0, R, g), lambda: QV.dividend_discount(100.0, eps, dps, R, ROE, PAYOUT, g)):
        with pytest.raises(QV.QATerminalGrowthError):
            fn()


def test_I_BNK_05_roll_forward():
    steady = 100 + (ROE - R) * 100 / (R - G)
    v = QV.roll_forward(steady, date(2026, 3, 31), date(2026, 10, 25), R,
                        [(date(2026, 7, 15), 5.0), (date(2026, 3, 1), 99.0), (date(2026, 11, 1), 99.0)])
    assert v == approx(172.616846041628)


def test_I_BNK_06_fcff_not_a_bank_primary():
    with pytest.raises(QV.QAMethodNotAllowedError):
        QV.validate_method("Deposit-taking bank", "FCFF DCF (WACC)")
    QV.validate_method("Deposit-taking bank", "Residual Income")


def test_I_BNK_07_peer_relative():
    assert (QV.peer_relative(2.5, 400.0, 5).value, QV.peer_relative(2.5, 400.0, 5).flag) == (approx(1000.0), "PASS")
    assert QV.peer_relative(2.5, 400.0, 2).flag == "WARNING"
    none = QV.peer_relative(None, 400.0, 0)
    assert none.value is None and none.flag == "MISSING"


def test_I_BNK_08_blend():
    assert QV.blend({"RI": 100.0, "DDM": 80.0}, {"RI": 1.0, "DDM": 0.0}) == approx(100.0)
    assert QV.blend({"RI": 100.0, "DDM": 80.0}, {"RI": 0.75, "DDM": 0.25}) == approx(95.0)
    assert QV.blend({"RI": 100.0, "DDM": None}, {"RI": 0.5, "DDM": 0.5}) is None
    with pytest.raises(QV.QAValuationError):
        QV.blend({"RI": 100.0}, {"RI": 0.9})


def test_I_BNK_09_terminal_flag_and_grid():
    assert QV.terminal_flag(0.80, 0.75) == "WARNING" and QV.terminal_flag(0.50, 0.75) == "PASS"
    grid = QV.sensitivity_grid(lambda r, g: 1.0 / (r - g), [0.11, 0.12], [0.11, 0.05])
    assert grid[0][0] is None and grid[1][1] == approx(1 / 0.07)


def test_I_BNK_10_driver_projection():
    base = dataclasses.make_dataclass("B", ["advances", "iea_to_advances", "non_interest_income",
                                            "operating_expenses", "equity", "diluted_shares"])(
        1000.0, 1.5, 20.0, 40.0, 200.0, 100_000_000)
    yr = dataclasses.make_dataclass("D", ["advance_growth", "iea_to_advances", "nim", "non_interest_income_growth",
                                          "opex_growth", "credit_cost", "tax_rate", "payout_ratio"])(
        0.10, 1.5, 0.04, 0.10, 0.05, 0.01, 0.25, 0.20)
    (p,) = QV.project_bank(base, [yr])
    assert (p.advances, p.nii, p.ppop, p.provisions, p.pat) == (approx(1100), approx(63), approx(43), approx(10.5), approx(24.375))
    assert (p.eps, p.dps, p.equity, p.bvps) == (approx(2.4375), approx(0.4875), approx(219.5), approx(21.95))
    assert p.roe == approx(24.375 / 209.75)


A = date(2026, 3, 31)
EPS_FC = [(date(2027, 3, 31), 18.0), (date(2028, 3, 31), 20.0)]
DIVS = [(date(2026, 6, 20), 2.0), (date(2026, 3, 1), 99.0), (date(2027, 11, 1), 99.0)]
Q1, Q2, Q3 = date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)


def test_I_BNK_11_equity_bridge():
    b = QV.equity_bridge(100.0, A, EPS_FC, date(2026, 10, 25), [(Q1, 4.4), (Q2, 4.6)], DIVS)
    assert (b.latest_results_period_end, b.eps_reported_after_anchor) == (Q2, approx(9.0))
    assert b.eps_forecast_stub == approx(18.0 * 25 / 365)
    assert b.bv_estimated_at_valuation == approx(108.232876712329)
    assert b.interim_eps_deviation_pct == approx(9.0 / (18.0 * 183 / 365) - 1)
    assert (b.forecast_update_flag, b.financials_age_days, b.anchor_age_days, b.freshness_status) == ("PASS", 25, 208, "PASS")


def test_I_BNK_12_interim_deviation_warning():
    b = QV.equity_bridge(100.0, A, EPS_FC, date(2026, 10, 25), [(Q1, 3.0)], DIVS)
    assert b.interim_eps_deviation_pct == approx(3.0 / (18.0 * 91 / 365) - 1)
    assert b.forecast_update_flag == "WARNING"
    assert b.bv_estimated_at_valuation == approx(106.769863013699)
    assert (b.financials_age_days, b.freshness_status) == (117, "PASS")


def test_I_BNK_13_no_interims_all_forecast_stale():
    b = QV.equity_bridge(100.0, A, EPS_FC, date(2026, 10, 25), (), DIVS)
    assert b.latest_results_period_end == A and b.eps_reported_after_anchor == 0.0
    assert b.interim_eps_deviation_pct is None
    assert b.bv_estimated_at_valuation == approx(108.257534246575)
    assert (b.financials_age_days, b.freshness_status) == (208, "STALE")


def test_I_BNK_14_stub_crosses_fye_anchor_overdue():
    b = QV.equity_bridge(100.0, A, EPS_FC, date(2027, 6, 10), [(Q1, 4.4), (Q2, 4.6), (Q3, 4.5)], DIVS)
    assert b.eps_forecast_stub == approx(18.0 * 90 / 365 + 20.0 * 71 / 366)
    assert b.bv_estimated_at_valuation == approx(119.818137585149)
    assert (b.anchor_age_days, b.freshness_status) == (436, "FAIL")


def test_I_BNK_15_beyond_forecast_horizon():
    with pytest.raises(QV.QAValuationError):
        QV.equity_bridge(100.0, A, EPS_FC, date(2028, 4, 15))


# --------------------------------------------------------------------------- insurance §4
def test_I_INS_01_04_sotp():
    kw = dict(ev=20_000.0, stake=0.80, cash=500.0, debt=300.0, other=0.0, shares=345_000_000, holdco_discount=0.10)
    assert QV.appraisal_value(20_000.0, 2_000.0, 15.0) == approx(50_000.0)
    assert QV.sotp_per_share(**kw, vnb=2_000.0, vnb_multiple=15.0) == approx(1049.27536231884)
    assert QV.appraisal_value(20_000.0, target_p_ev=2.0) == approx(40_000.0)
    with pytest.raises(QV.QADoubleCountingError):
        QV.appraisal_value(20_000.0, 2_000.0, 15.0, 2.0)
    with pytest.raises(QV.QADoubleCountingError):
        QV.appraisal_value(20_000.0)


# --------------------------------------------------------------------------- controls §6
B = QC.Controls(750.0, 500.0, 400.0, 600.0, required_margin_of_safety_pct=0.20)
SHOCK, ABS_, FUND, BIAS = QC.MODE_SHOCK, QC.MODE_ABSOLUTE, QC.FV_FUNDAMENTAL, QC.FV_MANUAL


def test_I_PRC_00_defaults_identity():
    o = QC.resolve(B)
    assert (o.selected_scenario_market_price, o.selected_scenario_fair_value, o.effective_shock_pct) == (750.0, 500.0, 0.0)
    assert (o.fv_label, o.control_status, o.control_warning) == ("Model output (unmodified)", "OK", "")


def test_I_PRC_01_03_manual_tests_1_to_3():
    o1 = QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.10))
    assert (o1.selected_scenario_market_price, o1.selected_scenario_fair_value) == (approx(675.0), 500.0)
    o2 = QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.10,
                                        fair_value_mode=BIAS, fair_value_bias_pct=-0.10))
    assert (o2.selected_scenario_fair_value, o2.selected_scenario_market_price) == (approx(450.0), approx(675.0))
    assert "MANUALLY BIASED" in o2.fv_label
    o3 = QC.resolve(dataclasses.replace(B, market_price_mode=ABS_, absolute_scenario_price=595.0,
                                        market_price_shock_pct=-0.10, sector_shock_pct=-0.05,
                                        global_shock_pct=-0.02, fair_value_bias_pct=-0.10))
    assert (o3.selected_scenario_market_price, o3.selected_scenario_fair_value) == (595.0, 500.0)
    assert o3.fair_value_after_bias == approx(450.0)
    assert "Price shocks set but ignored" in o3.control_warning
    assert "Fair-value bias set but ignored" in o3.control_warning


def test_I_PRC_04_derived_outputs():
    o = QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.10,
                                       fair_value_mode=BIAS, fair_value_bias_pct=-0.10))
    assert o.implied_upside_to_fair_value == approx(450 / 675 - 1)
    assert o.fair_value_gap == approx(450 / 750 - 1)
    assert o.target_purchase_price == approx(360.0) and o.control_warning == ""


def test_I_PRC_05_06_compounding_and_original_mode():
    o = QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.10, sector_shock_pct=-0.05))
    assert o.selected_scenario_market_price == approx(641.25)
    o6 = QC.resolve(dataclasses.replace(B, market_price_shock_pct=-0.10, sector_shock_pct=-0.05))
    assert (o6.selected_scenario_market_price, o6.market_price_after_shock) == (750.0, approx(641.25))
    assert "Price shocks set but ignored" in o6.control_warning


def test_I_PRC_07_09_case_absolute_blank_unvalued():
    o7 = QC.resolve(dataclasses.replace(B, fair_value_mode=FUND, fundamental_case="Bear"))
    assert (o7.fundamental_case_fv, o7.selected_scenario_fair_value) == (400.0, 400.0) and "Bear" in o7.fv_label
    o8 = QC.resolve(dataclasses.replace(B, market_price_mode=ABS_))
    assert o8.selected_scenario_market_price is None and o8.control_status.startswith("FAIL")
    o9 = QC.resolve(dataclasses.replace(B, model_fv_base=None, model_fv_bear=None, model_fv_bull=None,
                                        market_price_mode=SHOCK, market_price_shock_pct=-0.10))
    assert o9.selected_scenario_market_price == approx(675.0)
    assert (o9.selected_scenario_fair_value, o9.target_purchase_price, o9.implied_upside_to_fair_value) == (None, None, None)
    assert o9.control_status == "UNVALUED"


def test_I_PRC_10_12_tpp_absolute_in_shock_mode_apply_once():
    assert QC.resolve(B).target_purchase_price == approx(400.0)
    assert QC.resolve(dataclasses.replace(B, fair_value_mode=FUND, fundamental_case="Bear")).target_purchase_price == approx(320.0)
    assert QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.30)).target_purchase_price == approx(400.0)
    o11 = QC.resolve(dataclasses.replace(B, market_price_mode=SHOCK, market_price_shock_pct=-0.10, absolute_scenario_price=595.0))
    assert o11.selected_scenario_market_price == approx(675.0)
    assert "Absolute price set but ignored" in o11.control_warning and o11.control_status == "OK"
    g = dataclasses.replace(B, market_price_mode=SHOCK, global_shock_pct=-0.10)
    assert QC.resolve(g).market_price_after_shock == approx(675.0)
    assert QC.resolve(dataclasses.replace(g, sector_shock_pct=-0.05, market_price_shock_pct=0.02)
                      ).market_price_after_shock == approx(654.075)


# --------------------------------------------------------------------------- NAV §7
@pytest.mark.parametrize("case,mf001,mf002", [("Base", 75.20, 166.20), ("Bear", 67.20, 141.90), ("Bull", 83.20, 190.50)])
def test_I_NAV_02_03_method1(case, mf001, mf002):
    r = QN.weighted_adjustment_nav(80.0, K.MF001, case)
    assert r.nav == approx(mf001) and r.adjustment_by_line["MF001-L3"] == 0.0
    assert sum(r.adjustment_by_sector.values()) == approx(r.sum_adjustment)
    assert QN.weighted_adjustment_nav(150.0, K.MF002, case).nav == approx(mf002)


def test_I_NAV_01_classification():
    assert [QN.coverage_status(l) for l in K.MF001] == [
        "MODEL_VALUED", "MODEL_VALUED", "UNVALUED", "CARRYING_VALUE", "CARRYING_VALUE"]


def test_I_NAV_04_05_method2_plan_ratio():
    m2 = QN.quantity_based_nav(80.0, K.MF001)
    assert (m2.na_market_inr_cr, m2.na_numerator_inr_cr, m2.nav) == (approx(1000.0), approx(940.0), approx(75.20))
    assert QN.quantity_based_nav(72.0, K.MF001).nav == approx(67.68)


def test_I_NAV_06_07_scenario_nav():
    assert QN.scenario_market_nav(80.0, K.MF001).nav == approx(80.0)
    lines = _with(_with(K.MF001, "MF001-L1", scenario_price_inr=595.0), "MF001-L2", scenario_price_inr=90.0)
    r = QN.scenario_market_nav(80.0, lines)
    assert (r.na_numerator_inr_cr, r.nav) == (approx(918.0), approx(73.44))


def test_I_NAV_08_09_one_fv_moves_only_its_fund():
    s1 = _with(K.MF001, "MF001-L1", fv_inr={"Base": 600.0, "Bear": 400.0, "Bull": 600.0})
    assert QN.weighted_adjustment_nav(80.0, s1).nav == approx(78.40)
    assert QN.weighted_adjustment_nav(150.0, K.MF002).nav == approx(166.20)
    assert set(QN.weighted_adjustment_nav(80.0, K.MF001).adjustment_by_line) == {l.line_id for l in K.MF001}


def test_I_NAV_10_11_valuation_coverage():
    c = QN.coverage_summary(K.MF001, 0.90, 0.75)
    assert (c.coverage_total_pct, c.coverage_equity_pct, c.unvalued_weight_pct) == (approx(0.9), approx(0.5 / 0.6), approx(0.1))
    assert (c.unvalued_count, c.unvalued_value_inr_cr, c.status) == (1, approx(100.0), "WARNING")
    assert c.caption == "Covers 83.3% of equity; 10.0% of net assets unvalued (adjustment 0)"
    worse = _with(K.MF001, "MF001-L2", fv_inr={"Base": None, "Bear": None, "Bull": None}, selected_fv_inr=None)
    w = QN.coverage_summary(worse, 0.90, 0.75)
    assert (w.coverage_equity_pct, w.unvalued_count, w.status) == (approx(0.5), 2, "FAIL")


def test_I_NAV_12_reconciliation():
    ok = QN.reconcile(K.MF001, 1000.0, 0.005)
    assert ok.gap_inr_cr == approx(0.0, abs=1e-9) and ok.status == "PASS"
    bad = QN.reconcile(K.MF001, 1010.0, 0.005)
    assert bad.gap_pct == approx(1000 / 1010 - 1) and bad.status == "FAIL"


def test_I_NAV_13_selected_case():
    r = QN.weighted_adjustment_nav(80.0, _with(K.MF001, "MF001-L1", selected_fv_inr=450.0), "Selected")
    assert r.nav == approx(73.60)


def test_I_NAV_14_15_holdings_coverage():
    h = QN.holdings_coverage(K.MF001, 1000.0, 0.005)
    assert (h.value_coverage_pct, h.match_pct, h.unmatched_line_ids, h.recon_status, h.status) == (
        approx(1.0), approx(1.0), (), "PASS", "PASS")
    lines = _with(_with(K.MF001, "MF001-L3", price_inr=None), "MF001-L2", security_id=None)
    assert (QN.match_status(lines[2]), QN.match_status(lines[1])) == ("NO_PRICE", "UNMATCHED")
    assert QN.coverage_status(lines[1]) == "UNVALUED"
    h2 = QN.holdings_coverage(lines, 1000.0, 0.005)
    assert (h2.match_pct, h2.unmatched_line_ids, h2.value_coverage_pct, h2.status) == (
        approx(0.5), ("MF001-L2", "MF001-L3"), approx(1.0), "FAIL")
    short = QN.holdings_coverage(K.MF001, 1010.0, 0.005)
    assert (short.value_coverage_pct, short.recon_status, short.status) == (approx(1000 / 1010), "FAIL", "FAIL")


def _dated(l1, l2):
    return _with(_with(K.MF001, "MF001-L1", financials_as_of=l1), "MF001-L2", financials_as_of=l2)


def test_I_NAV_16_17_freshness():
    V = date(2026, 10, 23)
    f = QN.freshness_summary(_dated(date(2026, 6, 30), date(2026, 3, 31)), date(2026, 9, 30), V, V, 45, 135, 3)
    assert (f.holdings_age_days, f.nav_date_gap_days, f.max_financials_age_days) == (23, 0, 206)
    assert (f.stale_valued_weight_pct, f.status) == (approx(0.2), "STALE")
    ok = _dated(date(2026, 6, 30), date(2026, 9, 30))
    fresh = QN.freshness_summary(ok, date(2026, 9, 30), V, V, 45, 135, 3)
    assert (fresh.max_financials_age_days, fresh.stale_valued_weight_pct, fresh.status) == (115, 0.0, "PASS")
    assert QN.freshness_summary(ok, date(2026, 8, 31), V, V, 45, 135, 3).status == "STALE"
    gap = QN.freshness_summary(ok, date(2026, 9, 30), date(2026, 10, 16), V, 45, 135, 3)
    assert (gap.nav_date_gap_days, gap.status) == (7, "STALE")
    und = QN.freshness_summary(_dated(None, date(2026, 9, 30)), date(2026, 9, 30), V, V, 45, 135, 3)
    assert (und.stale_valued_weight_pct, und.status) == (approx(0.30), "STALE")


# --------------------------------------------------------------------------- §7.6, §7.8
AL = dataclasses.make_dataclass("AL", ["line_id", "sector", "security_id", "sector_weight", "constituent_weight"])
HY = dataclasses.make_dataclass("HY", ["security_id", "effective_weight", "scenario_price_inr", "fair_value_inr",
                                       ("assumed_buy_price_inr", object, None), ("quantity_override", object, None)])
ALLOC = [AL("H1", "Financial Services", "S90001", 0.30, 0.20), AL("H2", "Financial Services", "S90002", 0.30, 0.80),
         AL("H3", "Information Technology", "S90004", 0.60, 1.00), AL("H4", "Not applicable", None, 0.10, 1.00)]


def test_I_CUS_01_03_custom_allocation():
    w = QN.effective_weights(ALLOC)
    assert (w["S90001"], w["S90002"], w["CASH"], sum(w.values())) == (approx(0.06), approx(0.24), approx(0.10), approx(1.0))
    assert QN.validate_allocation(ALLOC) == []
    assert QN.validate_allocation(ALLOC[:3])
    assert QN.validate_allocation([AL("H1", "Financial Services", "S90001", 0.3, 0.5)] + ALLOC[2:])
    assert QN.validate_allocation(ALLOC + [AL("H5", "Information Technology", "S90001", 0.0, 0.0)])
    assert QN.validate_allocation([AL("H1", "Financial Services", "S90001", 0.3, -0.2)] + ALLOC[1:])
    before = [vars(l).copy() for l in K.MF001]
    QN.effective_weights(ALLOC); QN.validate_allocation(ALLOC)
    assert [vars(l) for l in K.MF001] == before


def test_I_HYP_01_02_hypothetical_portfolio():
    r = QN.build_hypothetical_portfolio(1_000_000.0, [HY("S90001", 0.6, 595.0, 500.0), HY("S90002", 0.4, 90.0, 120.0)], 0.001)
    assert {h.security_id: h.quantity for h in r.lines} == {"S90001": 1007, "S90002": 4440}
    assert r.cash_remaining_inr == approx(1_000_000 - 599_165 - 599.165 - 399_600 - 399.6)
    assert r.value_market_inr == approx(1007 * 595 + 4440 * 90 + r.cash_remaining_inr)
    assert r.value_fair_inr == approx(1007 * 500 + 4440 * 120 + r.cash_remaining_inr) and r.status == "PASS"
    assert QN.build_hypothetical_portfolio(1_000_000.0, [HY("S90001", 1.0, 595.0, 500.0, None, 2000)], 0.0).status == "FAIL"


def test_I_OVL_01_overlap():
    a = {l.security_id: l.weight for l in K.MF001 if l.security_id}
    b = {l.security_id: l.weight for l in K.MF002 if l.security_id}
    assert QN.overlap_by_weight(a, b) == (approx(0.20), 1)


def test_I_PEER_01_03_peer_statistic():
    members = [{"Security_ID": s, "Included": inc} for s, inc in
               [("P1", True), ("P2", True), ("P3", True), ("P4", False), ("P5", True), ("SUBJ", True)]]
    pb = {"P1": {"Value": 2.0, "Is_Meaningful": True}, "P2": {"Value": 3.0, "Is_Meaningful": True},
          "P3": {"Value": 4.0, "Is_Meaningful": True}, "P4": {"Value": 99.0, "Is_Meaningful": True},
          "P5": {"Value": 50.0, "Is_Meaningful": False}, "SUBJ": {"Value": 10.0, "Is_Meaningful": True}}
    s = QV.peer_statistic(members, pb, "SUBJ")
    assert (s.median, s.n_valid, s.n_excluded, s.min, s.max) == (3.0, 3, 3, 2.0, 4.0)
    assert QV.peer_statistic(members[3:5], pb).median is None
    s3 = QV.peer_statistic(members, dict(pb, P3={"Value": None, "Is_Meaningful": True}), "SUBJ")
    assert (s3.median, s3.n_valid) == (2.5, 2)
