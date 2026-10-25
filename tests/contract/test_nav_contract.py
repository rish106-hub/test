"""Contract §7 and spec <manual_test_cases> 5-7. Owner: 03-nav. Cases in cases.py."""
import dataclasses

import pytest

from src.common.enums import CoverageStatus
from src.fund_nav.classify import coverage_status
from src.fund_nav.coverage import coverage_summary
from src.fund_nav.methods import (quantity_based_nav, reconcile_net_assets, scenario_market_nav,
                                  weighted_adjustment_nav)
from tests.contract import cases as K

pytestmark = pytest.mark.owner("03-nav")
approx = pytest.approx


def _with(lines, line_id, **changes):
    return [dataclasses.replace(l, **changes) if l.line_id == line_id else l for l in lines]


def test_T_NAV_01_classification():
    st = {l.line_id: coverage_status(l) for l in K.MF001}
    assert st == {"MF001-L1": CoverageStatus.MODEL_VALUED, "MF001-L2": CoverageStatus.MODEL_VALUED,
                  "MF001-L3": CoverageStatus.UNVALUED, "MF001-L4": CoverageStatus.CARRYING_VALUE,
                  "MF001-L5": CoverageStatus.CARRYING_VALUE}


@pytest.mark.parametrize("case,expected", [("Base", 75.20), ("Bear", 67.20), ("Bull", 83.20)])
def test_T_NAV_02_method1_mf001(case, expected):
    r = weighted_adjustment_nav(80.0, K.MF001, case)
    assert r.nav == approx(expected)
    assert r.adjustment_by_line["MF001-L3"] == 0.0          # unvalued: zero adjustment, but flagged
    assert sum(r.adjustment_by_sector.values()) == approx(r.sum_adjustment)


@pytest.mark.parametrize("case,expected", [("Base", 166.20), ("Bear", 141.90), ("Bull", 190.50)])
def test_T_NAV_03_method1_mf002_with_fx(case, expected):
    assert weighted_adjustment_nav(150.0, K.MF002, case).nav == approx(expected)


def test_T_NAV_04_method2_equals_method1_when_weights_are_consistent():
    m2 = quantity_based_nav(80.0, K.MF001, "Base")
    assert m2.na_market_inr_cr == approx(1000.0)
    assert m2.na_numerator_inr_cr == approx(940.0)
    assert m2.nav == approx(75.20)


def test_T_NAV_05_plan_ratio_method_applies_same_pct_to_every_plan():
    d = quantity_based_nav(K.MF001_NAV["MF001-DIR-GR"], K.MF001, "Base").nav
    r = quantity_based_nav(K.MF001_NAV["MF001-REG-GR"], K.MF001, "Base").nav
    assert d == approx(75.20) and r == approx(67.68)
    assert d / 80.0 == approx(r / 72.0)


def test_T_NAV_06_scenario_nav_identity_at_default_controls():
    assert scenario_market_nav(80.0, K.MF001).nav == approx(80.0)


def test_T_NAV_07_scenario_nav_absolute_and_shock():
    lines = _with(K.MF001, "MF001-L1", scenario_price_inr=595.0)
    lines = _with(lines, "MF001-L2", scenario_price_inr=90.0)
    r = scenario_market_nav(80.0, lines)
    assert r.na_numerator_inr_cr == approx(918.0)   # 238 + 180 + 100 + 410 - 10
    assert r.nav == approx(73.44)


def test_T_NAV_08_changing_one_fair_value_moves_only_the_holding_fund_by_its_weight():
    """spec manual test 5."""
    s1 = _with(K.MF001, "MF001-L1", fv_inr={"Base": 600.0, "Bear": 400.0, "Bull": 600.0})
    assert weighted_adjustment_nav(80.0, s1, "Base").nav == approx(78.40)   # 80 x (1 - 0.06 + 0.04)
    assert weighted_adjustment_nav(150.0, K.MF002, "Base").nav == approx(166.20)  # MF002 lacks S90001


def test_T_NAV_09_absent_security_contributes_zero_exposure():
    """spec manual test 6: S90005 is in the registry but in neither fund."""
    for lines in (K.MF001, K.MF002):
        assert all(l.security_id != "S90005" for l in lines)
    r = weighted_adjustment_nav(80.0, K.MF001, "Base")
    assert "S90005" not in {l.security_id for l in K.MF001}
    assert set(r.adjustment_by_line) == {l.line_id for l in K.MF001}


def test_T_NAV_10_coverage_and_unvalued_disclosure():
    """spec manual test 7."""
    c = coverage_summary(K.MF001, warn=0.90, fail=0.75)
    assert c.coverage_total_pct == approx(0.90)
    assert c.coverage_equity_pct == approx(0.5 / 0.6)
    assert c.unvalued_weight_pct == approx(0.10)
    assert c.unvalued_count == 1
    assert c.unvalued_value_inr_cr == approx(100.0)
    assert c.status == "WARNING"                       # 83.3% < 90% warn, > 75% fail
    assert "83.3%" in c.caption and "10.0%" in c.caption


def test_T_NAV_11_adding_an_unvalued_holding_reduces_coverage():
    worse = _with(K.MF001, "MF001-L2", fv_inr={"Base": None, "Bear": None, "Bull": None}, selected_fv_inr=None)
    c = coverage_summary(worse, warn=0.90, fail=0.75)
    assert c.coverage_equity_pct == approx(0.3 / 0.6)
    assert c.unvalued_count == 2
    assert c.status == "FAIL"


def test_T_NAV_12_reconciliation():
    ok = reconcile_net_assets(K.MF001, K.MF001_REPORTED_NA, 0.005)
    assert ok.gap_inr_cr == approx(0.0, abs=1e-9) and ok.status == "PASS"
    bad = reconcile_net_assets(K.MF001, 1010.0, 0.005)
    assert bad.gap_pct == approx(1000.0 / 1010.0 - 1) and bad.status == "FAIL"


def test_T_NAV_13_selected_case_uses_selected_fair_value():
    lines = _with(K.MF001, "MF001-L1", selected_fv_inr=450.0)   # e.g. manual bias -10%
    r = weighted_adjustment_nav(80.0, lines, "Selected")
    assert r.nav == approx(80.0 * (1 + 0.3 * (450 / 750 - 1) + 0.2 * 0.2))   # 73.60
