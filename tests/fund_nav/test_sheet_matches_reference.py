"""Self-check (brief item 9): the recalculated 03-nav workbook equals T-NAV-02..07 and the Python reference.

Builds `--test-build --only 03-nav` equivalents (interfaces stubbed from the synthetic fixtures), recalculates in
LibreOffice and compares every tbl_NAVSummary and tbl_PriceControls value with src/fund_nav/reference_run.py.
"""
import shutil

import pytest

from src.common.enums import FairValueMode as F, MarketPriceMode as M
from src.fund_nav import reference_run as R
from src.scenarios.pricing import resolve_controls
from tests.fund_nav.harness import build_isolated, same, set_global

pytestmark = [pytest.mark.workbook, pytest.mark.owner("03-nav"),
              pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")]
approx = pytest.approx


def _assert_summary(built, **kw):
    ref = R.reference_summary(built.data, **kw)
    for pid, expected in ref.items():
        row = built.row("tbl_NAVSummary", "Plan_ID", pid)
        for col, e in expected.items():
            assert same(e, row[col]), f"{pid}.{col}: workbook {row[col]!r} != reference {e!r}"
    return ref


def _assert_controls(built, **kw):
    inputs = R.price_control_inputs(built.data, **kw)
    for sid, inp in inputs.items():
        e = resolve_controls(inp)
        row = built.row("tbl_PriceControls", "Security_ID", sid)
        for col, val in [("Effective_Shock_Pct", e.effective_shock_pct), ("Market_Price_After_Shock", e.market_price_after_shock),
                         ("Selected_Scenario_Market_Price", e.selected_scenario_market_price),
                         ("Fair_Value_After_Bias", e.fair_value_after_bias), ("Fundamental_Case_FV", e.fundamental_case_fv),
                         ("Selected_Scenario_Fair_Value", e.selected_scenario_fair_value),
                         ("Implied_Upside_To_Fair_Value", e.implied_upside_to_fair_value),
                         ("Fair_Value_Gap", e.fair_value_gap), ("Target_Purchase_Price", e.target_purchase_price),
                         ("FV_Label", e.fv_label), ("Control_Status", e.control_status),
                         ("Control_Warning", e.control_warning or None)]:
            got = row[col]
            if val == "":
                val = None
            if val is None and isinstance(got, str) and got.startswith("#"):
                continue
            assert same(val, got), f"{sid}.{col}: workbook {got!r} != reference {val!r}"


def test_defaults_match_hand_values_and_reference(tmp_path):
    b = build_isolated(tmp_path)
    ref = _assert_summary(b)
    _assert_controls(b)
    d, r, m = (b.row("tbl_NAVSummary", "Plan_ID", p) for p in ("MF001-DIR-GR", "MF001-REG-GR", "MF002-DIR-GR"))
    # T-NAV-02, 03, 04, 05, 06 hand values
    assert (d["Fair_NAV_Base"], d["Fair_NAV_Bear"], d["Fair_NAV_Bull"]) == (approx(75.20), approx(67.20), approx(83.20))
    assert (m["Fair_NAV_Base"], m["Fair_NAV_Bear"], m["Fair_NAV_Bull"]) == (approx(166.20), approx(141.90), approx(190.50))
    assert d["Fair_NAV_M2_Base"] == approx(75.20) and r["Fair_NAV_M2_Base"] == approx(67.68)
    assert all(x["Scenario_Market_NAV"] == x["Official_NAV"] for x in (d, r, m))      # W-11 identity, exactly
    assert d["Coverage_Caption"] == "Covers 83.3% of equity; 10.0% of net assets unvalued (adjustment 0)"
    assert (d["Holdings_Coverage_Status"], d["Valuation_Coverage_Status"], d["Freshness_Status"]) == ("PASS", "WARNING", "PASS")
    status = b.table("tbl_Nav_ControlsStatus")[0]
    assert status["Controls_At_Default"] is True
    assert ref["MF001-DIR-GR"]["Fair_NAV_Base"] == approx(75.20)


def test_T_NAV_07_absolute_and_shock_controls(tmp_path):
    ctl = {("S90001", "Market_Price_Scenario_Mode"): M.ABSOLUTE.value, ("S90001", "Absolute_Scenario_Price"): 595.0,
           ("S90002", "Market_Price_Scenario_Mode"): M.SHOCK.value, ("S90002", "Market_Price_Shock_Pct"): -0.10}
    b = build_isolated(tmp_path, controls=ctl)
    kw = {"controls": {"S90001": {"market_price_mode": M.ABSOLUTE, "absolute_scenario_price": 595.0},
                       "S90002": {"market_price_mode": M.SHOCK, "market_price_shock_pct": -0.10}}}
    _assert_summary(b, **kw)
    _assert_controls(b, **kw)
    d = b.row("tbl_NAVSummary", "Plan_ID", "MF001-DIR-GR")
    assert d["Scenario_Market_NAV"] == approx(73.44)                       # T-NAV-07
    assert d["Fair_NAV_Base"] == approx(75.20) and d["Official_NAV"] == 80    # prices never move fair value or official NAV
    assert b.table("tbl_Nav_ControlsStatus")[0]["Controls_At_Default"] is False
    h = b.row("tbl_Holdings_MF001", "Holding_Line_ID", "MF001-L1")
    assert h["Current_Market_Price"] == 750 and h["Selected_Scenario_Price"] == 595      # R008: original untouched


def test_fair_value_bias_global_and_sector_shock_apply_once(tmp_path):
    ctl = {("S90001", "Fair_Value_Scenario_Mode"): F.MANUAL_BIAS.value, ("S90001", "Fair_Value_Bias_Pct"): -0.10,
           ("S90001", "Market_Price_Scenario_Mode"): M.SHOCK.value, ("S90001", "Market_Price_Shock_Pct"): 0.02,
           ("S90002", "Market_Price_Scenario_Mode"): M.SHOCK.value}

    def edit(data):
        set_global(data, "in_Global_Price_Shock_Pct", "-0.1")
    b = build_isolated(tmp_path, edit=edit, controls=ctl, sector_shocks={"Financial Services": -0.05})
    kw = {"controls": {"S90001": {"fair_value_mode": F.MANUAL_BIAS, "fair_value_bias_pct": -0.10,
                                  "market_price_mode": M.SHOCK, "market_price_shock_pct": 0.02},
                       "S90002": {"market_price_mode": M.SHOCK}},
          "global_shock": -0.1, "sector_shocks": {"Financial Services": -0.05}}
    _assert_summary(b, **kw)
    _assert_controls(b, **kw)
    pc = b.row("tbl_PriceControls", "Security_ID", "S90001")
    assert pc["Market_Price_After_Shock"] == approx(750 * 0.90 * 0.95 * 1.02)         # 654.075, applied once
    assert pc["Selected_Scenario_Fair_Value"] == approx(450.0) and "MANUALLY BIASED" in pc["FV_Label"]
    d = b.row("tbl_NAVSummary", "Plan_ID", "MF001-DIR-GR")
    assert d["Fair_NAV_Base"] == approx(75.20)                                        # Base is unaffected by the bias
    assert d["Fair_NAV_Selected"] == approx(80 * (1 + 0.3 * (450 / 750 - 1) + 0.2 * 0.2))   # T-NAV-13


def test_unmatched_position_is_na_not_zero_and_fails_holdings_coverage(tmp_path):
    def edit(data):
        for r in data.tables["fund_holdings"]:
            if r["Holding_Line_ID"] == "MF001-L2":
                r["Security_ID"] = "S99999"           # not in the registry
    b = build_isolated(tmp_path, edit=edit)
    d = b.row("tbl_NAVSummary", "Plan_ID", "MF001-DIR-GR")
    ref = _assert_summary(b)
    assert ref["MF001-DIR-GR"]["Fair_NAV_M2_Base"] is None
    assert d["Fair_NAV_M2_Base"] == "#N/A" and d["Scenario_Market_NAV"] == "#N/A"
    assert d["Holdings_Coverage_Status"] == "FAIL" and d["Unmatched_Count"] == 1
    assert d["Fair_NAV_Base"] == approx(80 * (1 + 0.3 * (500 / 750 - 1)))             # Method 1 still computed, line adj 0
    h = b.row("tbl_Holdings_MF001", "Holding_Line_ID", "MF001-L2")
    assert h["Holdings_Match_Status"] == "UNMATCHED" and h["Valuation_Coverage_Status"] == "UNVALUED"
    assert h["Current_Market_Price"] == "#N/A"
