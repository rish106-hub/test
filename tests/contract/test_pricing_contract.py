"""Contract §6, spec <worked_example> and <manual_test_cases> 1-3. Owner: 03-nav."""
import dataclasses

import pytest

from src.common.enums import Case, FairValueMode as F, MarketPriceMode as M
from src.scenarios.pricing import PriceControlInputs, resolve_controls

pytestmark = pytest.mark.owner("03-nav")

BASE = PriceControlInputs(original_market_price=750.0, model_fv_base=500.0, model_fv_bear=400.0,
                          model_fv_bull=600.0, required_margin_of_safety_pct=0.20)
approx = pytest.approx


def test_T_PRC_00_defaults_are_identity():
    out = resolve_controls(BASE)
    assert out.selected_scenario_market_price == 750.0
    assert out.selected_scenario_fair_value == 500.0
    assert out.effective_shock_pct == 0.0
    assert out.fv_label == "Model output (unmodified)"
    assert out.control_status == "OK"


def test_T_PRC_01_market_shock_minus_10pct_gives_675_and_leaves_fair_value():
    inp = dataclasses.replace(BASE, market_price_mode=M.SHOCK, market_price_shock_pct=-0.10)
    out = resolve_controls(inp)
    assert out.market_price_after_shock == approx(675.0)
    assert out.selected_scenario_market_price == approx(675.0)
    assert out.selected_scenario_fair_value == 500.0
    assert inp.original_market_price == 750.0 and inp.model_fv_base == 500.0  # R008


def test_T_PRC_02_fair_value_bias_minus_10pct_gives_450_independently():
    inp = dataclasses.replace(BASE, market_price_mode=M.SHOCK, market_price_shock_pct=-0.10,
                              fair_value_mode=F.MANUAL_BIAS, fair_value_bias_pct=-0.10)
    out = resolve_controls(inp)
    assert out.fair_value_after_bias == approx(450.0)
    assert out.selected_scenario_fair_value == approx(450.0)
    assert out.selected_scenario_market_price == approx(675.0)   # unaffected by the FV control
    assert "MANUALLY BIASED" in out.fv_label                    # never labelled an unmodified model output


def test_T_PRC_03_absolute_595_overrides_market_price_only():
    inp = dataclasses.replace(BASE, market_price_mode=M.ABSOLUTE, absolute_scenario_price=595.0,
                              market_price_shock_pct=-0.10, sector_shock_pct=-0.05, global_shock_pct=-0.02,
                              fair_value_bias_pct=-0.10)
    out = resolve_controls(inp)
    assert out.selected_scenario_market_price == 595.0           # shocks ignored in absolute mode
    assert out.selected_scenario_fair_value == 500.0             # FV mode still Model Base
    assert out.fair_value_after_bias == approx(450.0)            # computed, but not selected
    assert inp.original_market_price == 750.0


def test_T_PRC_04_derived_outputs():
    inp = dataclasses.replace(BASE, market_price_mode=M.SHOCK, market_price_shock_pct=-0.10,
                              fair_value_mode=F.MANUAL_BIAS, fair_value_bias_pct=-0.10)
    out = resolve_controls(inp)
    assert out.implied_upside_to_fair_value == approx(450.0 / 675.0 - 1)   # -0.3333
    assert out.fair_value_gap == approx(450.0 / 750.0 - 1)                 # -0.40, vs ORIGINAL price
    assert out.target_purchase_price_base == approx(400.0)                 # 500 x 0.8
    assert out.target_purchase_price_selected == approx(360.0)             # 450 x 0.8


def test_T_PRC_05_shocks_compound_multiplicatively():
    inp = dataclasses.replace(BASE, market_price_mode=M.SHOCK, market_price_shock_pct=-0.10,
                              sector_shock_pct=-0.05, global_shock_pct=0.0)
    out = resolve_controls(inp)
    assert out.effective_shock_pct == approx(0.9 * 0.95 - 1)
    assert out.selected_scenario_market_price == approx(641.25)


def test_T_PRC_06_shocks_inactive_in_original_mode():
    inp = dataclasses.replace(BASE, market_price_shock_pct=-0.10, sector_shock_pct=-0.05)
    out = resolve_controls(inp)
    assert out.selected_scenario_market_price == 750.0
    assert out.market_price_after_shock == approx(641.25)  # still shown, not selected


def test_T_PRC_07_fundamental_case_selects_model_case_value():
    inp = dataclasses.replace(BASE, fair_value_mode=F.FUNDAMENTAL, fundamental_case=Case.BEAR)
    out = resolve_controls(inp)
    assert out.fundamental_case_fv == 400.0
    assert out.selected_scenario_fair_value == 400.0
    assert "Bear" in out.fv_label


def test_T_PRC_08_absolute_mode_without_price_is_visible_failure_not_fallback():
    inp = dataclasses.replace(BASE, market_price_mode=M.ABSOLUTE, absolute_scenario_price=None)
    out = resolve_controls(inp)
    assert out.selected_scenario_market_price is None
    assert out.control_status.startswith("FAIL")


def test_T_PRC_09_unvalued_security_keeps_price_controls_and_blank_fair_values():
    inp = dataclasses.replace(BASE, model_fv_base=None, model_fv_bear=None, model_fv_bull=None,
                              market_price_mode=M.SHOCK, market_price_shock_pct=-0.10)
    out = resolve_controls(inp)
    assert out.selected_scenario_market_price == approx(675.0)
    assert out.selected_scenario_fair_value is None
    assert out.target_purchase_price_base is None
    assert out.implied_upside_to_fair_value is None
    assert out.control_status == "UNVALUED"
