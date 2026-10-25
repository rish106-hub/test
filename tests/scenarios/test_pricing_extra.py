"""Edge cases of the section 6 reference beyond the frozen contract tests. Owner: 03-nav."""
import dataclasses

import pytest

from src.common.enums import FairValueMode as F, MarketPriceMode as M
from src.scenarios.pricing import PriceControlInputs, bias_text, control_warning, resolve_controls

BASE = PriceControlInputs(original_market_price=750.0, model_fv_base=500.0, model_fv_bear=400.0, model_fv_bull=600.0,
                          required_margin_of_safety_pct=0.2)


def test_missing_market_price_is_a_visible_failure_not_zero():
    out = resolve_controls(dataclasses.replace(BASE, original_market_price=None))
    assert out.selected_scenario_market_price is None and out.control_status.startswith("FAIL")
    assert out.implied_upside_to_fair_value is None and out.fair_value_gap is None


def test_warnings_join_in_contract_order():
    w = control_warning(-0.1, 0.0, 0.0, M.ORIGINAL, 595.0, F.MODEL_BASE, -0.1)
    assert w == ("Price shocks set but ignored (mode: Original Market Price); "
                 "Absolute price set but ignored (mode: Original Market Price); "
                 "Fair-value bias set but ignored (mode: Model Base Fair Value)")


def test_bias_text_matches_excel_round():
    assert bias_text(-0.10) == "-10" and bias_text(0.055) == "5.5" and bias_text(0.0) == "0"


def test_original_mode_never_reads_the_absolute_price():
    out = resolve_controls(dataclasses.replace(BASE, absolute_scenario_price=595.0))
    assert out.selected_scenario_market_price == 750.0
