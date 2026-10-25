"""Self-test of the W-layer scanners: each must FAIL on a workbook seeded with the violation it
exists to catch. Without this, a scan that never matches anything would report PASS forever.
"""
import json
import shutil

import pytest
import xlsxwriter

from tests.workbook import test_W_static as W
from tests.workbook.wbmodel import Workbook

pytestmark = [pytest.mark.workbook,
              pytest.mark.skipif(shutil.which("soffice") is None, reason="NOT RUN: LibreOffice not installed")]

PC_HEADERS = ["Security_ID", "Original_Market_Price", "Model_FV_Base", "Market_Price_Shock_Pct",
              "Effective_Shock_Pct", "Market_Price_After_Shock", "Selected_Scenario_Market_Price", "Control_Warning"]


@pytest.fixture(scope="module")
def broken(tmp_path_factory):
    from build.recalc import recalc
    d = tmp_path_factory.mktemp("broken")
    path = d / "broken.xlsx"
    w = xlsxwriter.Workbook(str(path))
    green = w.add_format({"font_color": "#007A33"})
    black = w.add_format({"font_color": "#000000"})
    grey = w.add_format({"font_color": "#6E6E6E"})
    sa, vo, nav, val = (w.add_worksheet(n) for n in ("SCENARIO_ANALYSIS", "VALUATION_OUTPUTS", "MF_NAV_CALCULATOR", "VAL_HDFC_BANK"))
    vo.add_table("A1:C3", {"name": "tbl_ValuationOutputs", "columns": [
        {"header": "Security_ID", "format": grey}, {"header": "FV_Base_INR", "format": grey},
        {"header": "Valuation_Coverage_Status", "format": grey}],
        "data": [["S1", 500, "MODEL_VALUED"], ["S2", None, "UNVALUED"]]})
    q = lambda c: f"tbl_PriceControls[[#This Row],[{c}]]"  # noqa: E731
    cols = [{"header": "Security_ID", "format": grey},
            {"header": "Original_Market_Price", "formula": f"=750*(1+{q('Market_Price_Shock_Pct')})", "format": green},  # W-06
            {"header": "Model_FV_Base", "format": grey},
            {"header": "Market_Price_Shock_Pct", "format": grey},
            {"header": "Effective_Shock_Pct", "formula": f"={q('Market_Price_Shock_Pct')}", "format": black},
            {"header": "Market_Price_After_Shock", "formula": f"={q('Original_Market_Price')}*(1+{q('Market_Price_Shock_Pct')})", "format": black},  # W-17
            {"header": "Selected_Scenario_Market_Price", "formula": f"={q('Market_Price_After_Shock')}", "format": black},
            {"header": "Control_Warning", "format": grey}]
    sa.add_table("A1:H2", {"name": "tbl_PriceControls", "columns": cols, "data": [["S1", None, 500, -0.1, None, None, None, ""]]})
    val.write("B2", 1.0, grey)
    nav.write_formula("A1", "='VAL_HDFC_BANK'!B2", black)                       # W-05 raw cross-owner ref, W-07 colour
    nav.write_formula("A2", '=INDEX(tbl_ValuationOutputs[FV_Base_INR],MATCH("S2",tbl_ValuationOutputs[Security_ID],0))', green)  # W-15
    nav.write_formula("A3", "=OFFSET(A1,0,0)", black)                            # W-04
    w.close()
    owners = {"tbl_ValuationOutputs": "02-valuation", "tbl_PriceControls": "03-nav"}
    cols_by = {"tbl_ValuationOutputs": ["Security_ID", "FV_Base_INR", "Valuation_Coverage_Status"],
               "tbl_PriceControls": PC_HEADERS}
    (d / "manifest.json").write_text(json.dumps({
        "tables": {k: {"owner": v, "columns": cols_by[k]} for k, v in owners.items()},
        "names": {}, "references": {}}))
    return Workbook(path, recalc(path, d / "recalc"), d)


def _must_fail(fn, wb):
    with pytest.raises(AssertionError):
        fn(wb, lambda *a: None)


def test_W_SELF_01_scanners_catch_seeded_violations(broken):
    for fn in (W.test_W_04_whitelisted_functions_only, W.test_W_05_no_raw_reference_to_another_owners_sheet,
               W.test_W_06_originals_model_values_and_imports_never_depend_on_scenario_inputs,
               W.test_W_07_font_colour_matches_content, W.test_W_15_links_to_possibly_blank_sources_are_blank_safe,
               W.test_W_17_shocks_are_read_once):
        _must_fail(fn, broken)
    assert broken.value("MF_NAV_CALCULATOR", "A2") == 0     # the WI-7 hazard itself: INDEX of a blank is 0


# --------------------------------------------------------------------------- value comparisons
def _synth(tmp_path_factory, name, mutate=None):
    from build.recalc import recalc
    from tests.workbook import qa_synth_wb
    d = tmp_path_factory.mktemp(name)
    p = qa_synth_wb.build(d / "synth.xlsx", mutate)
    return Workbook(p, recalc(p, d / "recalc"), d)


def _run(fn, wb):
    try:
        fn(wb, lambda *a: None)
        return True
    except AssertionError:
        return False


def test_W_SELF_02_value_checks_pass_on_a_correct_workbook_and_fail_on_mutants(tmp_path_factory):
    """Positive control: a value-only workbook holding the hand-derived T-NAV results passes W-03a/c,
    W-11, W-12, W-14a, W-16, W-18. Negative controls: one wrong number or caption fails W-03."""
    from tests.workbook import test_W_values as V
    good = _synth(tmp_path_factory, "good")
    for fn in (V.test_W_03a_price_controls_equal_cleanroom, V.test_W_03c_nav_summary_equals_cleanroom,
               V.test_W_11_reset_identity_at_default_controls, V.test_W_14a_tv_share_present_for_every_valued_security,
               V.test_W_12_dashboard_shows_coverage_unvalued_and_date_warnings, V.test_W_16_units_rederived,
               V.test_W_18_three_quality_measures_separate_no_composite):
        assert _run(fn, good), fn.__name__

    def bear_off(navs, pcs):
        if navs:
            navs[0]["Fair_NAV_Bear"] += 1e-6

    def caption(navs, pcs):
        if navs:
            navs[2]["Coverage_Caption"] = navs[2]["Coverage_Caption"].replace("100.0%", "100%")

    def tpp(navs, pcs):
        if pcs:
            pcs[0]["Target_Purchase_Price"] = pcs[0]["Model_FV_Base"]          # MoS not applied

    def scen(navs, pcs):
        if navs:
            navs[1]["Scenario_Market_NAV"] *= 0.999                            # identity broken at defaults
    assert not _run(V.test_W_03c_nav_summary_equals_cleanroom, _synth(tmp_path_factory, "m1", bear_off))
    assert not _run(V.test_W_03c_nav_summary_equals_cleanroom, _synth(tmp_path_factory, "m2", caption))
    assert not _run(V.test_W_03a_price_controls_equal_cleanroom, _synth(tmp_path_factory, "m3", tpp))
    assert not _run(V.test_W_11_reset_identity_at_default_controls, _synth(tmp_path_factory, "m4", scen))


def test_W_SELF_03_manual_tests_fail_when_inputs_do_not_propagate(tmp_path_factory, tmp_path):
    """Negative control for W-10: on a value-only workbook (no formulas) a perturbed input cannot move
    any output, so each manual-test body must fail rather than pass vacuously."""
    from tests.workbook import test_W_10_manual as M
    wb = _synth(tmp_path_factory, "static")
    sid = M.pick_valued_held(wb)
    assert sid == "S90001"
    for i, body in enumerate((M.manual_1_shock, M.manual_2_bias, M.manual_3_absolute, M.manual_5_fair_value,
                              M.manual_7_unvalued, M.manual_8_sector)):
        with pytest.raises(AssertionError):
            body(wb, sid, tmp_path / str(i))
