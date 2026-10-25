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
