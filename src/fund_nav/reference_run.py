"""Python reference run of the whole fund engine from ModelData (D-020).

Computes, with the reference functions only, every tbl_NAVSummary and tbl_PriceControls value that the
workbook formulas must reproduce. 05-qa compares the recalculated workbook with this; the self-check
tests/fund_nav/test_sheet_matches_reference.py does the same on the isolated build.

Inputs are read from the same canonical rows the workbook is built from. Controls default to the
workbook defaults; pass `controls` / `global_shock` / `sector_shocks` to mirror a changed workbook.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Mapping

from src.common.enums import Case, FairValueMode, MarketPriceMode, LineRole
from src.fund_nav.coverage import coverage_summary, freshness_summary, holdings_coverage
from src.fund_nav.methods import (UnmarkableHoldingError, quantity_based_nav, reconcile_net_assets,
                                  scenario_market_nav, weighted_adjustment_nav)
from src.fund_nav.model import HoldingLine
from src.scenarios.pricing import PriceControlInputs, PriceControlOutputs, resolve_controls


def _f(x):
    return None if x in (None, "") else float(x)


def _d(x):
    return None if x in (None, "") else date.fromisoformat(x)


def global_inputs(data) -> dict[str, str]:
    return {r["Name"]: r["Value"] for r in data.rows("global_inputs")}


def price_control_inputs(data, *, controls: Mapping[str, dict] | None = None, global_shock: float | None = None,
                         sector_shocks: Mapping[str, float] | None = None) -> dict[str, PriceControlInputs]:
    """One PriceControlInputs per registry security, at workbook defaults unless overridden."""
    g = global_inputs(data)
    price_date = g["in_Price_Date"]
    prices = {r["Security_ID"]: _f(r["Close_INR"]) for r in data.rows("market_prices") if r["Price_Date"] == price_date}
    fvs = {r["Security_ID"]: r for r in data.rows("valuation_outputs")}
    shock = float(g["in_Global_Price_Shock_Pct"] or 0) if global_shock is None else global_shock
    out = {}
    for reg in data.rows("security_registry"):
        sid = reg["Security_ID"]
        v = fvs.get(sid, {})
        base = PriceControlInputs(
            original_market_price=prices.get(sid), model_fv_base=_f(v.get("FV_Base_INR")),
            model_fv_bear=_f(v.get("FV_Bear_INR")), model_fv_bull=_f(v.get("FV_Bull_INR")),
            fundamental_case=Case(g["in_Global_Case"]), required_margin_of_safety_pct=float(g["in_Default_MoS"]),
            global_shock_pct=shock, sector_shock_pct=(sector_shocks or {}).get(reg["Sector"], 0.0))
        out[sid] = replace(base, **(controls or {}).get(sid, {}))
    return out


def resolve_all(inputs: Mapping[str, PriceControlInputs]) -> dict[str, PriceControlOutputs]:
    return {sid: resolve_controls(i) for sid, i in inputs.items()}


def build_lines(data, fund_id: str, inputs: Mapping[str, PriceControlInputs],
                outputs: Mapping[str, PriceControlOutputs]) -> list[HoldingLine]:
    vo = {r["Security_ID"]: r for r in data.rows("valuation_outputs")}
    lines = []
    for r in data.rows("fund_holdings"):
        if r["Fund_ID"] != fund_id:
            continue
        sid = r["Security_ID"] or None
        known = sid in inputs
        inp, out = (inputs[sid], outputs[sid]) if known else (None, None)
        lines.append(HoldingLine(
            line_id=r["Holding_Line_ID"], line_role=LineRole(r["Line_Role"]), asset_class=r["Asset_Class"],
            sector=r["Sector"], weight=float(r["Weight_Pct_of_Scheme_NAV"]),
            market_value_inr_cr=float(r["Market_Value_INR_Cr"]), security_id=sid if known else None,
            quantity=_f(r["Quantity_Held"]),
            price_inr=inp.original_market_price if known else None,
            fv_inr={"Base": inp.model_fv_base, "Bear": inp.model_fv_bear, "Bull": inp.model_fv_bull} if known else {},
            scenario_price_inr=out.selected_scenario_market_price if known else None,
            selected_fv_inr=out.selected_scenario_fair_value if known else None,
            financials_as_of=_d(vo.get(sid, {}).get("Latest_Results_Period_End")) if known else None))
    return lines


def _safe(fn):
    try:
        return fn()
    except UnmarkableHoldingError:
        return None          # Excel: #N/A (WI-6)


def reference_summary(data, **kw) -> dict[str, dict]:
    """{Plan_ID: {NAV_SUMMARY column: value}} for the Method 1 headline, Method 2, Method 3 and the three
    data-quality measures. None means the workbook shows #N/A (an unmarkable position)."""
    g = global_inputs(data)
    inputs = price_control_inputs(data, **kw)
    outputs = resolve_all(inputs)
    price_date, val_date = date.fromisoformat(g["in_Price_Date"]), date.fromisoformat(g["in_Valuation_Date"])
    tol, warn, fail = float(g["in_Recon_Tolerance_Pct"]), float(g["in_Coverage_Warn"]), float(g["in_Coverage_Fail"])
    hs, fs, ps = int(g["in_Holdings_Stale_Days"]), int(g["in_Financials_Stale_Days"]), int(g["in_Price_Stale_Days"])
    totals = {(r["Fund_ID"], r["Portfolio_Date"]): float(r["Reported_Scheme_Net_Assets_INR_Cr"])
              for r in data.rows("fund_scheme_totals")}
    result = {}
    for plan in data.rows("fund_plans"):
        pid, fid = plan["Plan_ID"], plan["Fund_ID"]
        lines = build_lines(data, fid, inputs, outputs)
        navs = sorted((_d(r["NAV_Date"]), float(r["NAV_INR"])) for r in data.rows("official_nav")
                      if r["Plan_ID"] == pid and _d(r["NAV_Date"]) <= price_date)
        nav_date, official = navs[-1]
        pdate = max(date.fromisoformat(r["Portfolio_Date"]) for r in data.rows("fund_holdings") if r["Fund_ID"] == fid)
        reported = totals[(fid, pdate.isoformat())]
        m1 = {c: weighted_adjustment_nav(official, lines, c).nav for c in ("Base", "Bear", "Bull", "Selected")}
        m2 = _safe(lambda: quantity_based_nav(official, lines, "Base").nav)
        m3 = _safe(lambda: scenario_market_nav(official, lines).nav)
        hc = holdings_coverage(lines, reported, tol)
        cov = coverage_summary(lines, warn, fail, "Base")
        fr = freshness_summary(lines, pdate, nav_date, val_date, hs, fs, ps)
        recon = reconcile_net_assets(lines, reported, tol)
        result[pid] = {
            "Plan_ID": pid, "Fund_ID": fid, "Portfolio_Date": pdate, "NAV_Date": nav_date, "Official_NAV": official,
            "Fair_NAV_Base": m1["Base"], "Fair_NAV_Bear": m1["Bear"], "Fair_NAV_Bull": m1["Bull"],
            "Fair_NAV_Selected": m1["Selected"], "Fair_NAV_M2_Base": m2, "Scenario_Market_NAV": m3,
            "Diff_vs_Official_INR": m1["Base"] - official, "Diff_vs_Official_Pct": m1["Base"] / official - 1,
            "Holdings_Value_Coverage_Pct": hc.value_coverage_pct, "Holdings_Match_Pct": hc.match_pct,
            "Unmatched_Count": len(hc.unmatched_line_ids), "Recon_Gap_Pct": recon.gap_pct,
            "Recon_Status": hc.recon_status, "Holdings_Coverage_Status": hc.status,
            "Valuation_Coverage_Total_Pct": cov.coverage_total_pct, "Valuation_Coverage_Equity_Pct": cov.coverage_equity_pct,
            "Unvalued_Weight_Pct": cov.unvalued_weight_pct, "Unvalued_Count": cov.unvalued_count,
            "Unvalued_Value_INR_Cr": cov.unvalued_value_inr_cr, "Valuation_Coverage_Status": cov.status,
            "Coverage_Caption": cov.caption, "Holdings_Age_Days": fr.holdings_age_days,
            "NAV_Date_Gap_Days": fr.nav_date_gap_days, "Max_Financials_Age_Days": fr.max_financials_age_days,
            "Stale_Valued_Weight_Pct": fr.stale_valued_weight_pct, "Freshness_Status": fr.status,
            "Method_Drift_INR": None if m2 is None else m1["Base"] - m2,
        }
    return result
