"""A small value-only workbook in the shape of an integrated build, for self-testing the W-layer
readers and comparisons before the workers' sheets exist. QA SELF-TEST ONLY: it is never shipped.

Contents follow the synthetic fixtures (tests/fixtures/synthetic, tests/contract/cases.py) at
default controls; Fair NAV values are the hand-derived T-NAV numbers where the contract gives them.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

import xlsxwriter

from src.common import schema as S
from tests.contract import cases as K
from tests.independent.cleanroom import controls as QC, nav as QN

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
V = date(2026, 10, 23)


def _read(name):
    with (FIX / f"{name}.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def _dt(d):
    return datetime(d.year, d.month, d.day) if isinstance(d, date) else d


def build(path: Path, mutate=None) -> Path:
    """mutate(nav_rows, None) / mutate(None, price_control_rows) edits a table just before it is written."""
    path = Path(path)
    w = xlsxwriter.Workbook(str(path))
    datef = w.add_format({"num_format": "yyyy-mm-dd"})
    sheets = {n: w.add_worksheet(n) for n in ("GLOBAL_ASSUMPTIONS", "VALUATION_OUTPUTS", "SCENARIO_ANALYSIS",
                                              "PPFAS_FLEXICAP_HOLDINGS", "HDFC_MIDCAP_HOLDINGS", "MF_NAV_CALCULATOR",
                                              "EXECUTIVE_DASHBOARD")}
    tables, row_at = {}, {}

    def table(sheet, name, headers, rows):
        top = row_at.get(sheet, 1)
        data = [[_dt(r.get(h)) for h in headers] for r in rows]
        sheets[sheet].add_table(top, 0, top + len(data), len(headers) - 1,
                                {"name": name, "columns": [{"header": h, "format": datef} if any(
                                    isinstance(x[i], datetime) for x in data) else {"header": h}
                                    for i, h in enumerate(headers)], "data": data})
        row_at[sheet] = top + len(data) + 3
        tables[name] = {"owner": "QA-SELFTEST", "columns": headers}

    # global inputs as named cells
    for i, r in enumerate(_read("global_inputs")):
        v = r["Value"]
        val = (datetime.fromisoformat(v) if r["Value_Type"] == "date" else float(v) if r["Value_Type"] in ("decimal", "int")
               else v) if v else None
        sheets["GLOBAL_ASSUMPTIONS"].write(i, 0, r["Name"])
        if val is not None:
            sheets["GLOBAL_ASSUMPTIONS"].write(i, 1, val, datef if isinstance(val, datetime) else None)
        w.define_name(r["Name"], f"=GLOBAL_ASSUMPTIONS!$B${i + 1}")

    vo = []
    for r in _read("valuation_outputs"):
        row = {h: r.get(h) for h in [c.name for c in S.VALUATION_OUTPUTS.columns]}
        for c in S.VALUATION_OUTPUTS.columns:
            if c.dtype == "float" and row[c.name]:
                row[c.name] = float(row[c.name])
            if c.dtype == "date" and row[c.name]:
                row[c.name] = date.fromisoformat(row[c.name])
            if row[c.name] == "":
                row[c.name] = None
        vo.append(row)
    table("VALUATION_OUTPUTS", "tbl_ValuationOutputs", [c.name for c in S.VALUATION_OUTPUTS.columns], vo)

    reg = {r["Security_ID"]: r for r in _read("security_registry")}
    table("SCENARIO_ANALYSIS", "tbl_SectorShocks", ["Sector", "Sector_Price_Shock_Pct"],
          [{"Sector": s, "Sector_Price_Shock_Pct": 0.0} for s in sorted({r["Sector"] for r in reg.values()})])
    pcs, sel_price, sel_fv = [], {}, {}
    for sid in reg:
        fv = K.FV.get(sid, {"Base": None, "Bear": None, "Bull": None})
        c = QC.Controls(K.PRICE[sid], fv["Base"], fv["Bear"], fv["Bull"], required_margin_of_safety_pct=0.20)
        o = QC.resolve(c)
        sel_price[sid], sel_fv[sid] = o.selected_scenario_market_price, o.selected_scenario_fair_value
        row = {"Security_ID": sid, "Sector": reg[sid]["Sector"], "Original_Market_Price": c.original_market_price,
               "Model_FV_Base": c.model_fv_base, "Model_FV_Bear": c.model_fv_bear, "Model_FV_Bull": c.model_fv_bull,
               "Market_Price_Scenario_Mode": c.market_price_mode, "Market_Price_Shock_Pct": 0.0,
               "Absolute_Scenario_Price": None, "Fair_Value_Scenario_Mode": c.fair_value_mode,
               "Fundamental_Case": "Base", "Fair_Value_Bias_Pct": 0.0, "Required_Margin_of_Safety_Pct": 0.20}
        for col, field in [("Effective_Shock_Pct", "effective_shock_pct"), ("Market_Price_After_Shock", "market_price_after_shock"),
                           ("Selected_Scenario_Market_Price", "selected_scenario_market_price"),
                           ("Fair_Value_After_Bias", "fair_value_after_bias"), ("Fundamental_Case_FV", "fundamental_case_fv"),
                           ("Selected_Scenario_Fair_Value", "selected_scenario_fair_value"),
                           ("Implied_Upside_To_Fair_Value", "implied_upside_to_fair_value"), ("Fair_Value_Gap", "fair_value_gap"),
                           ("Target_Purchase_Price", "target_purchase_price"), ("FV_Label", "fv_label"),
                           ("Control_Status", "control_status"), ("Control_Warning", "control_warning")]:
            row[col] = getattr(o, field)
        pcs.append(row)
    if mutate:
        mutate(None, pcs)
    table("SCENARIO_ANALYSIS", "tbl_PriceControls", [c.name for c in S.PRICE_CONTROLS.columns], pcs)
    sheets["SCENARIO_ANALYSIS"].write(0, 30, "Controls_At_Default")
    sheets["SCENARIO_ANALYSIS"].write_boolean(0, 31, True)

    hold_cols = [c.name for c in S.FUND_HOLDINGS.columns]
    for fund, sheet, lines in (("MF001", "PPFAS_FLEXICAP_HOLDINGS", K.MF001), ("MF002", "HDFC_MIDCAP_HOLDINGS", K.MF002)):
        csvrows = {r["Holding_Line_ID"]: r for r in _read("fund_holdings")}
        rows = []
        for l in lines:
            r = {h: csvrows[l.line_id].get(h) or None for h in hold_cols}
            for h in ("Quantity_Held", "Market_Value_INR_Cr", "Weight_Pct_of_Scheme_NAV"):
                r[h] = float(r[h]) if r[h] else None
            r["Portfolio_Date"] = date(2026, 9, 30)
            pos = l.line_role == "POSITION"
            st = QN.coverage_status(l)
            r.update(Current_Market_Price=l.price_inr if pos else None, Selected_Scenario_Price=sel_price.get(l.security_id),
                     Base_Fair_Value=l.fv_inr.get("Base") if pos else None, Scenario_Fair_Value=sel_fv.get(l.security_id),
                     Holdings_Match_Status=QN.match_status(l), Valuation_Coverage_Status=st,
                     Financials_As_Of=date(2026, 9, 30) if st == "MODEL_VALUED" else None,
                     MV_Mkt_INR_Cr=l.quantity * l.price_inr / 1e7 if pos else l.market_value_inr_cr,
                     MV_Fair_Base_INR_Cr=(l.quantity * (l.fv_inr["Base"] if st == "MODEL_VALUED" else l.price_inr) / 1e7)
                     if pos else l.market_value_inr_cr)
            for case in ("Base", "Bear", "Bull", "Selected"):
                r[f"Adj_{case}"] = QN.weighted_adjustment_nav(1.0, lines, case).adjustment_by_line[l.line_id]
            rows.append(r)
        table(sheet, f"tbl_Holdings_{fund}", hold_cols, rows)

    table("MF_NAV_CALCULATOR", "tbl_SchemeTotals", ["Fund_ID", "Portfolio_Date", "Reported_Scheme_Net_Assets_INR_Cr"],
          [{"Fund_ID": "MF001", "Portfolio_Date": date(2026, 9, 30), "Reported_Scheme_Net_Assets_INR_Cr": 1000.0},
           {"Fund_ID": "MF002", "Portfolio_Date": date(2026, 9, 30), "Reported_Scheme_Net_Assets_INR_Cr": 500.0}])
    navs = {**K.MF001_NAV, **K.MF002_NAV}
    table("MF_NAV_CALCULATOR", "tbl_OfficialNAV", ["Plan_ID", "NAV_Date", "NAV_INR"],
          [{"Plan_ID": p, "NAV_Date": V, "NAV_INR": v} for p, v in navs.items()])
    hand = {"MF001-DIR-GR": (75.20, 67.20, 83.20), "MF001-REG-GR": (67.68, 72 * 0.84, 72 * 1.04),
            "MF002-DIR-GR": (166.20, 141.90, 190.50)}
    nav_rows = []
    for plan, off in navs.items():
        fund = plan[:5]
        lines = K.MF001 if fund == "MF001" else K.MF002
        b, be, bu = hand[plan]
        cov = QN.coverage_summary(lines, 0.9, 0.75)
        h = QN.holdings_coverage(lines, 1000.0 if fund == "MF001" else 500.0, 0.005)
        dated = [__import__("dataclasses").replace(l, financials_as_of=date(2026, 9, 30)) for l in lines]
        f = QN.freshness_summary(dated, date(2026, 9, 30), V, V, 45, 135, 3)
        m2 = QN.quantity_based_nav(off, lines).nav
        nav_rows.append({
            "Plan_ID": plan, "Fund_ID": fund, "Portfolio_Date": date(2026, 9, 30), "NAV_Date": V, "Official_NAV": off,
            "Fair_NAV_Base": b, "Fair_NAV_Bear": be, "Fair_NAV_Bull": bu, "Fair_NAV_Selected": b, "Fair_NAV_M2_Base": m2,
            "Scenario_Market_NAV": off, "Diff_vs_Official_INR": b - off, "Diff_vs_Official_Pct": b / off - 1,
            "Price_Date": V, "Valuation_Date": V, "Holdings_Value_Coverage_Pct": h.value_coverage_pct,
            "Holdings_Match_Pct": h.match_pct, "Unmatched_Count": 0, "Recon_Gap_Pct": 0.0, "Recon_Status": h.recon_status,
            "Holdings_Coverage_Status": h.status, "Valuation_Coverage_Total_Pct": cov.coverage_total_pct,
            "Valuation_Coverage_Equity_Pct": cov.coverage_equity_pct, "Unvalued_Weight_Pct": cov.unvalued_weight_pct,
            "Unvalued_Count": cov.unvalued_count, "Unvalued_Value_INR_Cr": cov.unvalued_value_inr_cr,
            "Valuation_Coverage_Status": cov.status, "Coverage_Caption": cov.caption,
            "Holdings_Age_Days": f.holdings_age_days, "NAV_Date_Gap_Days": f.nav_date_gap_days,
            "Max_Financials_Age_Days": f.max_financials_age_days, "Stale_Valued_Weight_Pct": f.stale_valued_weight_pct,
            "Freshness_Status": f.status, "Method_Drift_INR": b - m2})
    if mutate:
        mutate(nav_rows, None)
    table("MF_NAV_CALCULATOR", "tbl_NAVSummary", [c.name for c in S.NAV_SUMMARY.columns], nav_rows)
    dash = sheets["EXECUTIVE_DASHBOARD"]
    for j, plan in enumerate(navs):
        dash.write(3, 1 + j, plan)
    for i, col in enumerate(["Official_NAV", "Fair_NAV_Base", "Scenario_Market_NAV", "Coverage_Caption", "Unvalued_Count",
                             "Unvalued_Weight_Pct", "Holdings_Age_Days", "Price_Date", "NAV_Date_Gap_Days",
                             "Holdings_Coverage_Status", "Valuation_Coverage_Status", "Freshness_Status"]):
        dash.write(4 + i, 0, col)
        for j in range(len(navs)):
            c = chr(ord("B") + j)
            dash.write_formula(4 + i, 1 + j, f'=IFERROR(INDEX(tbl_NAVSummary[{col}],MATCH({c}$4,tbl_NAVSummary[Plan_ID],0)),"MISSING")')
    w.close()
    (path.parent / "manifest.json").write_text(json.dumps({"tables": tables, "names": {}, "references": {}, "test_build": True}))
    (path.parent / "build_report.json").write_text(json.dumps({"test_build": True, "not_implemented": {}, "unbuilt_sheets": []}))
    return path
