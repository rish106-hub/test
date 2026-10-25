"""Rebuild reference-function inputs from a recalculated workbook (W-03, W-10, E layer).

Inputs are read from the same workbook the outputs come from, so Excel and Python see identical
inputs (spec/test_plan.md W-03). Fair values and prices come from tbl_PriceControls, which itself
links tbl_ValuationOutputs / tbl_MarketPrices; financials dates come from tbl_ValuationOutputs.
"""
from __future__ import annotations

from datetime import date

from src.fund_nav.model import HoldingLine
from tests.workbook.wbmodel import Workbook, as_date, blankish, num

PC_OUT = {
    "Effective_Shock_Pct": "effective_shock_pct", "Market_Price_After_Shock": "market_price_after_shock",
    "Selected_Scenario_Market_Price": "selected_scenario_market_price", "Fair_Value_After_Bias": "fair_value_after_bias",
    "Fundamental_Case_FV": "fundamental_case_fv", "Selected_Scenario_Fair_Value": "selected_scenario_fair_value",
    "Implied_Upside_To_Fair_Value": "implied_upside_to_fair_value", "Fair_Value_Gap": "fair_value_gap",
    "Target_Purchase_Price": "target_purchase_price", "FV_Label": "fv_label", "Control_Status": "control_status",
    "Control_Warning": "control_warning",
}


def cell(v):
    """Workbook value -> Python reference value: '', None and #N/A are None."""
    return None if blankish(v) else v


def by_key(rows, key):
    return {r[key]: r for r in rows if r.get(key) not in (None, "")}


def pc_inputs(wb: Workbook, row: dict, values: dict | None = None) -> dict:
    sector_shock = 0.0
    if "tbl_SectorShocks" in wb.tables:
        ss = by_key(wb.rows("tbl_SectorShocks", values), "Sector")
        sector_shock = num(ss.get(row.get("Sector"), {}).get("Sector_Price_Shock_Pct")) or 0.0
    g = wb.names.get("in_Global_Price_Shock_Pct")
    global_shock = num((values or {}).get(g[0], {}).get(g[1]) if values else wb.value(*g)) if g else 0.0
    return dict(
        original_market_price=num(row["Original_Market_Price"]), model_fv_base=num(row["Model_FV_Base"]),
        model_fv_bear=num(row["Model_FV_Bear"]), model_fv_bull=num(row["Model_FV_Bull"]),
        market_price_mode=row["Market_Price_Scenario_Mode"], market_price_shock_pct=num(row["Market_Price_Shock_Pct"]) or 0.0,
        absolute_scenario_price=num(row["Absolute_Scenario_Price"]), fair_value_mode=row["Fair_Value_Scenario_Mode"],
        fundamental_case=row["Fundamental_Case"], fair_value_bias_pct=num(row["Fair_Value_Bias_Pct"]) or 0.0,
        required_margin_of_safety_pct=num(row["Required_Margin_of_Safety_Pct"]) or 0.0,
        sector_shock_pct=sector_shock, global_shock_pct=global_shock or 0.0)


def holdings_table(wb: Workbook, fund_id: str) -> str:
    return f"tbl_Holdings_{fund_id}"


def lines_from_workbook(wb: Workbook, fund_id: str, values: dict | None = None) -> list[HoldingLine]:
    pc = by_key(wb.rows("tbl_PriceControls", values), "Security_ID")
    vo = by_key(wb.rows("tbl_ValuationOutputs", values), "Security_ID") if "tbl_ValuationOutputs" in wb.tables else {}
    out = []
    for r in wb.rows(holdings_table(wb, fund_id), values):
        sid = cell(r.get("Security_ID"))
        p = pc.get(sid) if sid else None
        pos = r["Line_Role"] == "POSITION"
        out.append(HoldingLine(
            line_id=r["Holding_Line_ID"], line_role=r["Line_Role"], asset_class=r["Asset_Class"], sector=r["Sector"],
            weight=num(r["Weight_Pct_of_Scheme_NAV"]), market_value_inr_cr=num(r["Market_Value_INR_Cr"]),
            security_id=sid if (p is not None or not pos) else None,
            quantity=num(r.get("Quantity_Held")),
            price_inr=num(p["Original_Market_Price"]) if p else None,
            fv_inr={c: num(p[f"Model_FV_{c}"]) if p else None for c in ("Base", "Bear", "Bull")},
            scenario_price_inr=num(p["Selected_Scenario_Market_Price"]) if p else None,
            selected_fv_inr=num(p["Selected_Scenario_Fair_Value"]) if p else None,
            financials_as_of=as_date(vo.get(sid, {}).get("Latest_Results_Period_End")) if sid else None))
    return out


def global_input(wb: Workbook, name: str, values: dict | None = None):
    s, c = wb.names[name]
    return (values or {}).get(s, {}).get(c) if values else wb.value(s, c)


def scheme_net_assets(wb: Workbook, fund_id: str, portfolio_date: date, values=None) -> float | None:
    for r in wb.rows("tbl_SchemeTotals", values):
        if r["Fund_ID"] == fund_id and as_date(r["Portfolio_Date"]) == portfolio_date:
            return num(r["Reported_Scheme_Net_Assets_INR_Cr"])
    return None


def portfolio_date(wb: Workbook, fund_id: str, values=None) -> date | None:
    ds = {as_date(r["Portfolio_Date"]) for r in wb.rows(holdings_table(wb, fund_id), values)}
    return ds.pop() if len(ds) == 1 else None


def funds(wb: Workbook) -> list[str]:
    return sorted(t.removeprefix("tbl_Holdings_") for t in wb.tables if t.startswith("tbl_Holdings_"))
