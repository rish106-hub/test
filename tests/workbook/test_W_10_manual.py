"""W-10a–h: spec <manual_test_cases> 1–8 executed on the workbook (spec/test_plan.md W-10).

Each test sets input cells in a copy of the generated workbook (openpyxl), recalculates it in
LibreOffice and asserts (1) the intended outputs moved by the intended amount, (2) originals, model
values, imported data and unrelated funds did not move (R007/R008), and (3) every tbl_PriceControls
and tbl_NAVSummary value of the perturbed workbook still equals the clean-room recomputation.
The round trip itself is proven value-identical first (test_W_10_roundtrip.py).
The helpers take a Security_ID so the E layer can run the same tests on HDFC Bank (E-04).
"""
from __future__ import annotations

import pytest

from tests.independent._support import same
from tests.workbook import wbread as RD
from tests.workbook.conftest import require_real
from tests.workbook.test_W_static import _protected_cells
from tests.workbook.test_W_values import CLEANROOM_FNS, _pc_compare, nav_summary_diffs
from tests.independent.cleanroom import controls as QC
from tests.workbook.wbmodel import num, perturbed_values, value_diff, volatile_cells

pytestmark = pytest.mark.workbook
SHOCK, ABSOLUTE, MANUAL = "Market Price Shock", "Absolute Scenario Market Price", "Manual Fair-Value Bias"


# --------------------------------------------------------------------------- helpers
def pc_cell(wb, sid, col):
    t = wb.tables["tbl_PriceControls"]
    r = wb.row_index("tbl_PriceControls", "Security_ID", sid)
    assert r is not None, f"{sid} has no tbl_PriceControls row"
    return t.sheet, t.cell(col, r)


def vo_cell(wb, sid, col):
    t = wb.tables["tbl_ValuationOutputs"]
    r = wb.row_index("tbl_ValuationOutputs", "Security_ID", sid)
    assert r is not None, f"{sid} has no tbl_ValuationOutputs row"
    return t.sheet, t.cell(col, r)


def pc_row(wb, sid, values=None):
    return RD.by_key(wb.rows("tbl_PriceControls", values), "Security_ID")[sid]


def holders(wb, sid):
    return [f for f in RD.funds(wb) if any(r.get("Security_ID") == sid for r in wb.rows(RD.holdings_table(wb, f)))]


def nav_rows(wb, values=None):
    return RD.by_key(wb.rows("tbl_NAVSummary", values), "Plan_ID")


def pick_valued_held(wb):
    vo = RD.by_key(wb.rows("tbl_ValuationOutputs"), "Security_ID")
    pc = RD.by_key(wb.rows("tbl_PriceControls"), "Security_ID")
    cands = [s for s in pc if vo.get(s, {}).get("Valuation_Coverage_Status") == "MODEL_VALUED" and holders(wb, s)
             and num(pc[s]["Original_Market_Price"])]
    if not cands:
        pytest.skip("NOT RUN: no MODEL_VALUED security held by a fund in this build")
    return min(cands, key=lambda s: (len(holders(wb, s)), s))      # prefer one held by a single fund


def run(wb, edits, tmp_path):
    after = perturbed_values(wb, edits, tmp_path)
    return after, value_diff(wb.all_values(), after, ignore=volatile_cells(wb))


def assert_untouched(wb, diff, allowed=frozenset()):
    """R007/R008: originals, model values, imports and non-scenario NAVs never move."""
    moved = sorted(set(diff) & (_protected_cells(wb) - set(allowed)))
    assert moved == [], f"protected cells moved: {[(c, diff[c]) for c in moved[:10]]}"


def assert_consistent(wb, after):
    """The perturbed workbook still equals the clean-room everywhere (W-03 on perturbed inputs)."""
    d = _pc_compare(wb, lambda i: QC.resolve(QC.Controls(**i)), after)
    d += nav_summary_diffs(wb, CLEANROOM_FNS, after)
    assert d == [], d[:10]


def other_funds_unchanged(wb, diff, sid):
    held = set(holders(wb, sid))
    for f in RD.funds(wb):
        if f in held:
            continue
        t = wb.tables[RD.holdings_table(wb, f)]
        assert not [c for c in diff if c[0] == t.sheet], f"{f} does not hold {sid} but its holdings moved"
        for plan, r in nav_rows(wb).items():
            if r["Fund_ID"] == f:
                row = r["__row__"]
                ns = wb.tables["tbl_NAVSummary"]
                assert not [h for h in ns.headers if (ns.sheet, ns.cell(h, row)) in diff], f"{plan} moved"


def _setup(built):
    require_real(built, "tbl_PriceControls", "tbl_NAVSummary", "tbl_ValuationOutputs")


# --------------------------------------------------------------------------- shared scenario bodies
def manual_1_shock(wb, sid, tmp_path):
    p0 = num(pc_row(wb, sid)["Original_Market_Price"])
    after, diff = run(wb, [(*pc_cell(wb, sid, "Market_Price_Scenario_Mode"), SHOCK),
                           (*pc_cell(wb, sid, "Market_Price_Shock_Pct"), -0.10)], tmp_path)
    r = pc_row(wb, sid, after)
    assert num(r["Selected_Scenario_Market_Price"]) == pytest.approx(p0 * 0.9, rel=1e-9)
    assert same(r["Selected_Scenario_Fair_Value"], pc_row(wb, sid)["Selected_Scenario_Fair_Value"])
    assert_untouched(wb, diff)
    for f in holders(wb, sid):
        assert any(not same(num(x["Scenario_Market_NAV"]), num(nav_rows(wb)[p]["Scenario_Market_NAV"]))
                   for p, x in nav_rows(wb, after).items() if x["Fund_ID"] == f), f"{f} Scenario NAV did not move"
    other_funds_unchanged(wb, diff, sid)
    assert_consistent(wb, after)
    return f"{sid}: price {p0} -> {num(r['Selected_Scenario_Market_Price'])}; {len(diff)} cells moved, none protected"


def manual_2_bias(wb, sid, tmp_path):
    p0 = num(pc_row(wb, sid)["Original_Market_Price"])
    fv0 = num(pc_row(wb, sid)["Model_FV_Base"])
    after, diff = run(wb, [(*pc_cell(wb, sid, "Market_Price_Scenario_Mode"), SHOCK),
                           (*pc_cell(wb, sid, "Market_Price_Shock_Pct"), -0.10),
                           (*pc_cell(wb, sid, "Fair_Value_Scenario_Mode"), MANUAL),
                           (*pc_cell(wb, sid, "Fair_Value_Bias_Pct"), -0.10)], tmp_path)
    r = pc_row(wb, sid, after)
    assert num(r["Selected_Scenario_Fair_Value"]) == pytest.approx(fv0 * 0.9, rel=1e-9)
    assert num(r["Selected_Scenario_Market_Price"]) == pytest.approx(p0 * 0.9, rel=1e-9)
    assert "MANUALLY BIASED" in str(r["FV_Label"])
    assert num(r["Target_Purchase_Price"]) == pytest.approx(fv0 * 0.9 * (1 - num(r["Required_Margin_of_Safety_Pct"])), rel=1e-9)
    assert_untouched(wb, diff)
    other_funds_unchanged(wb, diff, sid)
    assert_consistent(wb, after)
    return f"{sid}: FV {fv0} -> {num(r['Selected_Scenario_Fair_Value'])}, price {p0} -> {num(r['Selected_Scenario_Market_Price'])}"


def manual_3_absolute(wb, sid, tmp_path):
    row = pc_row(wb, sid)
    p0, fv0 = num(row["Original_Market_Price"]), num(row["Model_FV_Base"])
    absolute = round(p0 * 595 / 750, 2)
    edits = [(*pc_cell(wb, sid, "Market_Price_Scenario_Mode"), ABSOLUTE),
             (*pc_cell(wb, sid, "Absolute_Scenario_Price"), absolute),
             (*pc_cell(wb, sid, "Market_Price_Shock_Pct"), -0.10),
             (*pc_cell(wb, sid, "Fair_Value_Bias_Pct"), -0.10)]
    ss = RD.by_key(wb.rows("tbl_SectorShocks"), "Sector") if "tbl_SectorShocks" in wb.tables else {}
    if row["Sector"] in ss:
        t = wb.tables["tbl_SectorShocks"]
        edits.append((t.sheet, t.cell("Sector_Price_Shock_Pct", ss[row["Sector"]]["__row__"]), -0.05))
    after, diff = run(wb, edits, tmp_path)
    r = pc_row(wb, sid, after)
    assert num(r["Selected_Scenario_Market_Price"]) == pytest.approx(absolute, rel=1e-12)
    assert num(r["Selected_Scenario_Fair_Value"]) == pytest.approx(fv0, rel=1e-12)
    assert num(r["Original_Market_Price"]) == pytest.approx(p0, rel=1e-15)
    assert "Price shocks set but ignored" in str(r["Control_Warning"])
    assert "Fair-value bias set but ignored" in str(r["Control_Warning"])
    assert_untouched(wb, diff)
    assert_consistent(wb, after)
    return f"{sid}: absolute {absolute} selected; warning '{r['Control_Warning']}'"


def manual_5_fair_value(wb, sid, tmp_path):
    fv0 = num(pc_row(wb, sid)["Model_FV_Base"])
    after, diff = run(wb, [(*vo_cell(wb, sid, "FV_Base_INR"), fv0 * 1.2)], tmp_path)
    before_nav, after_nav = nav_rows(wb), nav_rows(wb, after)
    for f in holders(wb, sid):
        for p, x in after_nav.items():
            if x["Fund_ID"] == f:
                assert num(x["Fair_NAV_Base"]) > num(before_nav[p]["Fair_NAV_Base"]), p
    for p, x in after_nav.items():
        assert same(num(x["Scenario_Market_NAV"]), num(before_nav[p]["Scenario_Market_NAV"])), p
        assert same(num(x["Official_NAV"]), num(before_nav[p]["Official_NAV"])), p
    other_funds_unchanged(wb, diff, sid)
    assert_consistent(wb, after)
    return f"{sid}: FV_Base {fv0} -> {fv0 * 1.2}; holders {holders(wb, sid)} moved, others unchanged"


def manual_7_unvalued(wb, sid, tmp_path):
    edits = [(*vo_cell(wb, sid, c), None) for c in ("FV_Base_INR", "FV_Bear_INR", "FV_Bull_INR")]
    edits.append((*vo_cell(wb, sid, "Valuation_Coverage_Status"), "UNVALUED"))
    after, diff = run(wb, edits, tmp_path)
    before_nav, after_nav = nav_rows(wb), nav_rows(wb, after)
    for f in holders(wb, sid):
        t = RD.holdings_table(wb, f)
        for r in wb.rows(t, after):
            if r.get("Security_ID") == sid:
                assert r["Valuation_Coverage_Status"] == "UNVALUED"
                assert num(r["Adj_Base"]) == 0.0, "unvalued line must have adjustment 0, never -w (R009)"
        for p, x in after_nav.items():
            if x["Fund_ID"] == f:
                b = before_nav[p]
                assert num(x["Unvalued_Count"]) > num(b["Unvalued_Count"])
                assert num(x["Valuation_Coverage_Equity_Pct"]) < num(b["Valuation_Coverage_Equity_Pct"])
                assert x["Coverage_Caption"] != b["Coverage_Caption"]
    other_funds_unchanged(wb, diff, sid)
    assert_consistent(wb, after)
    return f"{sid} made unvalued: coverage and captions updated for {holders(wb, sid)}"


def manual_8_sector(wb, sid, tmp_path):
    row = pc_row(wb, sid)
    if "tbl_SectorShocks" not in wb.tables or row["Sector"] not in RD.by_key(wb.rows("tbl_SectorShocks"), "Sector"):
        pytest.skip(f"NOT RUN: no tbl_SectorShocks row for {row['Sector']}")
    t = wb.tables["tbl_SectorShocks"]
    srow = RD.by_key(wb.rows("tbl_SectorShocks"), "Sector")[row["Sector"]]["__row__"]
    p0 = num(row["Original_Market_Price"])
    after, diff = run(wb, [(t.sheet, t.cell("Sector_Price_Shock_Pct", srow), -0.05),
                           (*pc_cell(wb, sid, "Market_Price_Scenario_Mode"), SHOCK),
                           (*pc_cell(wb, sid, "Market_Price_Shock_Pct"), -0.10)], tmp_path)
    assert num(pc_row(wb, sid, after)["Selected_Scenario_Market_Price"]) == pytest.approx(p0 * 0.95 * 0.9, rel=1e-9)
    for other, r in RD.by_key(wb.rows("tbl_PriceControls", after), "Security_ID").items():
        if other != sid and r["Sector"] == row["Sector"] and r["Market_Price_Scenario_Mode"] == "Original Market Price":
            assert same(r["Selected_Scenario_Market_Price"], pc_row(wb, other)["Selected_Scenario_Market_Price"])
            assert "Price shocks set but ignored" in str(r["Control_Warning"])
    assert_untouched(wb, diff)
    assert_consistent(wb, after)
    return f"{sid}: {p0} x 0.95 x 0.90 selected; same-sector securities in Original mode flagged, not moved"


# --------------------------------------------------------------------------- W-10a–h
def test_W_10a_manual_test_1_market_shock(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_1_shock(built, pick_valued_held(built), tmp_path))


def test_W_10b_manual_test_2_fair_value_bias(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_2_bias(built, pick_valued_held(built), tmp_path))


def test_W_10c_manual_test_3_absolute_price(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_3_absolute(built, pick_valued_held(built), tmp_path))


def test_W_10d_manual_test_4_custom_allocation_isolated(built, tmp_path, record_property):
    _setup(built)
    require_real(built, "tbl_CustomAllocation")
    t = built.tables["tbl_CustomAllocation"]
    rows = built.rows("tbl_CustomAllocation")
    if not rows:
        pytest.skip("NOT RUN: tbl_CustomAllocation has no rows")
    r = rows[0]["__row__"]
    edits = [(t.sheet, t.cell("Sector_Weight_Pct", r), 0.123), (t.sheet, t.cell("Constituent_Weight_Pct", r), 0.456)]
    after, diff = run(built, edits, tmp_path)
    actual = {(t2.sheet) for n, t2 in built.tables.items()
              if n.startswith("tbl_Holdings_") or n in ("tbl_NAVSummary", "tbl_PriceControls")}
    moved = [c for c in diff if c[0] in actual and built.table_of(*c) and
             built.table_of(*c)[0].name != "tbl_CustomAllocation"]
    record_property("qa_evidence", f"custom allocation edited; {len(moved)} actual-holdings/NAV/control cells moved")
    assert moved == [], moved[:10]


def test_W_10e_manual_test_5_one_fair_value(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_5_fair_value(built, pick_valued_held(built), tmp_path))


def test_W_10f_manual_test_6_security_held_by_no_fund(built, tmp_path, record_property):
    _setup(built)
    held = {s for f in RD.funds(built) for s in (r.get("Security_ID") for r in built.rows(RD.holdings_table(built, f))) if s}
    free = [s for s in RD.by_key(built.rows("tbl_PriceControls"), "Security_ID") if s not in held]
    if not free:
        pytest.skip("NOT RUN: every security with a control row is held by a fund")
    sid = free[0]
    after, diff = run(built, [(*pc_cell(built, sid, "Market_Price_Scenario_Mode"), SHOCK),
                              (*pc_cell(built, sid, "Market_Price_Shock_Pct"), -0.50),
                              (*pc_cell(built, sid, "Fair_Value_Scenario_Mode"), MANUAL),
                              (*pc_cell(built, sid, "Fair_Value_Bias_Pct"), 0.50)], tmp_path)
    sheets = {built.tables[n].sheet for n in built.tables if n.startswith("tbl_Holdings_") or n == "tbl_NAVSummary"}
    fund_cells = [c for c in diff if c[0] in sheets]
    record_property("qa_evidence", f"{sid} (no fund holds it) shocked -50% and biased +50%: {len(fund_cells)} fund cells moved")
    assert fund_cells == [], fund_cells[:10]
    assert_consistent(built, after)


def test_W_10g_manual_test_7_unvalued_coverage(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_7_unvalued(built, pick_valued_held(built), tmp_path))


def test_W_10h_manual_test_8_sector_and_security_shock(built, tmp_path, record_property):
    _setup(built)
    record_property("qa_evidence", manual_8_sector(built, pick_valued_held(built), tmp_path))
