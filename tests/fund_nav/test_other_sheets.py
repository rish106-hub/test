"""Workbook checks for the sheets beyond the core NAV: rebalancing, audit, sector, grid, performance, overlap."""
import math
import shutil
from datetime import date, timedelta

import pytest

from src.common.enums import MarketPriceMode as M
from src.fund_nav import performance as P
from src.fund_nav import reference_run as R
from src.fund_nav.custom_allocation import AllocationLine, validate_allocation
from src.fund_nav.rebalance import HypoLineInput, build_hypothetical_portfolio
from src.scenarios.pricing import resolve_controls
from tests.fund_nav.harness import build_isolated, same

pytestmark = [pytest.mark.workbook, pytest.mark.owner("03-nav"),
              pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")]
approx = pytest.approx


def _hypo_reference(built, capital, tc, allocation, **kw):
    inputs = R.price_control_inputs(built.data, **kw)
    outs = R.resolve_all(inputs)
    lines = []
    for sid, w, buy, qty in allocation:
        o = outs[sid]
        lines.append(HypoLineInput(sid, w, o.selected_scenario_market_price, o.selected_scenario_fair_value, buy, qty))
    return build_hypothetical_portfolio(capital, lines, tc)


def test_hypothetical_portfolio_matches_reference_and_flags_overspend(tmp_path):
    b = build_isolated(tmp_path)
    ref = _hypo_reference(b, 1_000_000.0, 0.001, [("S90001", 0.06, None, None), ("S90002", 0.24, None, None), ("S90004", 0.60, None, None)])
    rows = {r["Line_ID"]: r for r in b.table("tbl_Nav_Hypo")}
    assert [rows[i]["Quantity"] for i in ("H1", "H2", "H3")] == [l.quantity for l in ref.lines]
    assert b.labelled("PORTFOLIO_REBALANCING", "Cash remaining") == approx(ref.cash_remaining_inr)
    assert b.labelled("PORTFOLIO_REBALANCING", "Hypothetical Rebalanced Portfolio Value (not an existing fund) | at scenario") == approx(ref.value_market_inr)
    assert b.labelled("PORTFOLIO_REBALANCING", "Hypothetical Rebalanced Portfolio Value (not an existing fund) | at selected") == approx(ref.value_fair_inr)
    assert b.labelled("PORTFOLIO_REBALANCING", "Allocation status") == "PASS"
    # actual holdings never read this sheet (T-CUS-03): NAVs equal the plain reference
    for pid, e in R.reference_summary(b.data).items():
        assert same(e["Fair_NAV_Base"], b.row("tbl_NAVSummary", "Plan_ID", pid)["Fair_NAV_Base"])

    def edit(data):
        data.tables["custom_allocation"] = [
            {"Line_ID": "H1", "Sector": "Financial Services", "Security_ID": "S90001", "Sector_Weight_Pct": "1",
             "Constituent_Weight_Pct": "1", "Assumed_Buy_Price_INR": "", "Quantity_Override": "2000"}]
    over = build_isolated(tmp_path / "over", edit=edit) if (tmp_path / "over").mkdir() is None else None
    assert over.labelled("PORTFOLIO_REBALANCING", "Portfolio status") == "FAIL"
    assert over.labelled("PORTFOLIO_REBALANCING", "Cash remaining") < 0


def test_invalid_allocation_is_reported(tmp_path):
    def edit(data):
        data.tables["custom_allocation"] = [   # no explicit cash line: sector weights 0.9 -> must fail (T-CUS-02)
            {"Line_ID": "H1", "Sector": "Financial Services", "Security_ID": "S90001", "Sector_Weight_Pct": "0.3",
             "Constituent_Weight_Pct": "0.2", "Assumed_Buy_Price_INR": "", "Quantity_Override": ""},
            {"Line_ID": "H2", "Sector": "Financial Services", "Security_ID": "S90002", "Sector_Weight_Pct": "0.3",
             "Constituent_Weight_Pct": "0.8", "Assumed_Buy_Price_INR": "", "Quantity_Override": ""},
            {"Line_ID": "H3", "Sector": "Information Technology", "Security_ID": "S90004", "Sector_Weight_Pct": "0.6",
             "Constituent_Weight_Pct": "1", "Assumed_Buy_Price_INR": "", "Quantity_Override": ""}]
    b = build_isolated(tmp_path, edit=edit)
    py = validate_allocation([AllocationLine("H1", "Financial Services", "S90001", 0.3, 0.2),
                              AllocationLine("H2", "Financial Services", "S90002", 0.3, 0.8),
                              AllocationLine("H3", "Information Technology", "S90004", 0.6, 1.0)])
    assert py and b.labelled("PORTFOLIO_REBALANCING", "Allocation status") == "FAIL"
    assert b.labelled("PORTFOLIO_REBALANCING", "Sector weights + explicit cash") == approx(0.9)


def test_audit_lists_sector_sums_and_overlap_follow_inputs(tmp_path):
    def edit(data):
        for r in data.tables["valuation_outputs"]:
            if r["Security_ID"] == "S90002":
                r["FV_Base_INR"] = r["FV_Bear_INR"] = r["FV_Bull_INR"] = ""    # S90002 loses its model value
    b = build_isolated(tmp_path, edit=edit)
    ref = R.reference_summary(b.data)
    for pid, e in ref.items():
        row = b.row("tbl_NAVSummary", "Plan_ID", pid)
        for col in ("Fair_NAV_Base", "Valuation_Coverage_Equity_Pct", "Unvalued_Count", "Coverage_Caption", "Valuation_Coverage_Status"):
            assert same(e[col], row[col]), (pid, col, row[col], e[col])
    unv = [r["Holding_Line_ID"] for r in b.table("tbl_Nav_AuditUnvalued_MF001") if r["Holding_Line_ID"]]
    assert unv == ["MF001-L2", "MF001-L3"]                                    # nothing hidden, nothing zeroed
    assert [r["Weight_Pct"] for r in b.table("tbl_Nav_AuditUnvalued_MF001") if r["Holding_Line_ID"]] == [approx(0.2), approx(0.1)]
    assert b.row("tbl_Holdings_MF001", "Holding_Line_ID", "MF001-L2")["Valuation_Coverage_Status"] == "UNVALUED"
    # sector contributions sum to the total fair-NAV difference
    for fid, plan in (("MF001", "MF001-DIR-GR"), ("MF002", "MF002-DIR-GR")):
        total = sum(r[f"Contribution_INR_{plan.replace('-', '_')}"] for r in b.table(f"tbl_Nav_Sector_{fid}"))
        s = b.row("tbl_NAVSummary", "Plan_ID", plan)
        assert total == approx(s["Fair_NAV_Base"] - s["Official_NAV"])
    assert b.labelled("FUND_PERFORMANCE", "Overlap by weight") == approx(0.2)           # T-OVL-01
    assert b.labelled("FUND_PERFORMANCE", "Common securities") == 1


def test_uniform_grid_equals_method3_when_every_security_is_shocked(tmp_path):
    ctl = {}
    for sid in ("S90001", "S90002", "S90003", "S90004", "S90005"):
        ctl[(sid, "Market_Price_Scenario_Mode")] = M.SHOCK.value
        ctl[(sid, "Market_Price_Shock_Pct")] = -0.10
    b = build_isolated(tmp_path, controls=ctl)
    nav = b.row("tbl_NAVSummary", "Plan_ID", "MF001-DIR-GR")["Scenario_Market_NAV"]
    grid = {r: v for r, v in b.values["MF_SCENARIO_BUILDER"].items() if r.startswith("A") and isinstance(v, float)}
    row = next(k[1:] for k, v in grid.items() if v == approx(-0.10))
    assert b.values["MF_SCENARIO_BUILDER"][f"B{row}"] == approx(nav)                  # 80 x (1000 - 0.1 x 600) / 1000 = 75.2


def _series(start: date, end: date, base: float, drift: float, amp: float):
    out, d, i = [], start, 0
    while d <= end:
        if d.weekday() < 5:
            out.append((d, base * math.exp(drift * i) * (1 + amp * math.sin(i / 3.0))))
            i += 1
        d += timedelta(days=1)
    return out


def test_performance_windows_match_reference_and_short_history_is_blank(tmp_path):
    end = date(2026, 10, 23)
    nav = _series(date(2022, 6, 1), end, 50.0, 0.0004, 0.01)
    # a TRI that ends on the NAV date (a benchmark that stops earlier gives no benchmark return)
    tri = _series(date(2022, 5, 1), end, 10000.0, 0.0003, 0.012)

    def edit(data):
        data.tables["official_nav"] = [r for r in data.tables["official_nav"] if r["Plan_ID"] != "MF001-DIR-GR"]
        data.tables["official_nav"] += [{"Plan_ID": "MF001-DIR-GR", "NAV_Date": d.isoformat(), "NAV_INR": repr(v),
                                         "Source_ID": "SRC-SYNTH-000001", "Data_Status": "SYNTHETIC TEST FIXTURE"} for d, v in nav]
        data.tables["benchmark_tri"] = [{"Benchmark_Name": "SYNTHETIC TRI", "Date": d.isoformat(), "Index_Value": repr(v),
                                         "Is_TRI": "TRUE", "Source_ID": "SRC-SYNTH-000001",
                                         "Data_Status": "SYNTHETIC TEST FIXTURE"} for d, v in tri]
    b = build_isolated(tmp_path, edit=edit)
    rows = {r["Key"]: r for r in b.table("tbl_Nav_Perf")}
    rf = 0.065
    for w, days in (("1Y", 365), ("3Y", 3 * 365)):
        e = P.window_metrics(nav, end, days, rf, rf, tri)
        r = rows[f"MF001-DIR-GR|{w}"]
        assert r["Status"] == "OK" and r["N_Returns"] == e["n_returns"]
        for col, key in (("Return", "return"), ("CAGR", "cagr"), ("Volatility", "vol"), ("Max_Drawdown", "max_drawdown"),
                         ("Downside_Deviation", "downside_dev"), ("Sharpe", "sharpe"), ("Sortino", "sortino"),
                         ("Bench_Return", "bench_return"), ("Excess_Return", "excess_return")):
            assert same(e[key], r[col], 1e-8), (w, col, r[col], e[key])
    for w in ("5Y", "10Y"):                       # history starts 2022-06: too short, so blank, not computed
        r = rows[f"MF001-DIR-GR|{w}"]
        assert str(r["Status"]).startswith("Insufficient history")
        assert all(r[c] in (None, "") for c in ("Return", "CAGR", "Volatility", "Max_Drawdown", "Sharpe", "Excess_Return"))
    other = rows["MF002-DIR-GR|1Y"]               # one NAV only
    assert other["Return"] in (None, "") and str(other["Status"]).startswith("Insufficient history")
