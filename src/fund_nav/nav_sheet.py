"""MF_NAV_CALCULATOR: tbl_FundPlans, tbl_OfficialNAV, tbl_SchemeTotals, tbl_NAVSummary.

tbl_NAVSummary has one row per plan and exactly the columns of schema.NAV_SUMMARY, all uniform calculated
columns. The fund-specific sums (each plan reads its own fund's holdings table) are in the private table
tbl_Nav_PlanCalc, whose rows are written per plan. Method 1 is the headline (D-019); Method 2 is the ratio
form (D-004); Method 3 is the Scenario Market NAV. The three data-quality measures are separate columns and
are never combined (D-026). Above the tables, a statement block puts every value next to its OutputLabel (WI-9).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.common import schema as S
from src.common.enums import OutputLabel
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl

OWNER = xl.OWNER
SHEET = "MF_NAV_CALCULATOR"
SUMMARY, CALC = "tbl_NAVSummary", "tbl_Nav_PlanCalc"
xl.register_private_table(CALC, SHEET)

GAP = 3


@dataclass(frozen=True)
class NavLayout:
    plan_ids: tuple[str, ...]
    plan_fund: dict[str, str]
    summary_top: int
    calc_top: int
    statement_top: int


def _calc_columns(T: str) -> list[tuple[str, str | None, str]]:
    """(name, formula using [@Col] and holdings table T, number format). formula None = a value column."""
    w, st = f"{T}[Weight_Pct_of_Scheme_NAV]", f"{T}[Valuation_Coverage_Status]"
    role, asset, fin = f"{T}[Line_Role]", f"{T}[Asset_Class]", f"{T}[Financials_As_Of]"
    return [
        ("Plan_ID", None, "general"),
        ("Fund_ID", "=" + xl.lookup("tbl_FundPlans", "Fund_ID", "[@Plan_ID]", "Plan_ID"), "general"),
        ("Holdings_Lines", f"=COUNTA({T}[Holding_Line_ID])", "count"),
        ("Portfolio_Date", f'=IF(COUNT({T}[Portfolio_Date])=0,"",MAX({T}[Portfolio_Date]))', "date"),
        ("Reported_NA_Cr", ('=IF(COUNTIFS(tbl_SchemeTotals[Fund_ID],[@Fund_ID],tbl_SchemeTotals[Portfolio_Date],[@Portfolio_Date])=0,"",'
                            "SUMIFS(tbl_SchemeTotals[Reported_Scheme_Net_Assets_INR_Cr],tbl_SchemeTotals[Fund_ID],[@Fund_ID],"
                            "tbl_SchemeTotals[Portfolio_Date],[@Portfolio_Date]))"), "inr_cr"),
        ("Disclosed_Total_Cr", f"=SUM({T}[Market_Value_INR_Cr])", "inr_cr"),
        ("Sum_Adj_Base", f"=SUM({T}[Adj_Base])", "pct"),
        ("Sum_Adj_Bear", f"=SUM({T}[Adj_Bear])", "pct"),
        ("Sum_Adj_Bull", f"=SUM({T}[Adj_Bull])", "pct"),
        ("Sum_Adj_Selected", f"=SUM({T}[Adj_Selected])", "pct"),
        ("NA_Mkt_Cr", f"=SUM({T}[MV_Mkt_INR_Cr])", "inr_cr"),
        ("NA_Fair_Base_Cr", f"=SUM({T}[MV_Fair_Base_INR_Cr])", "inr_cr"),
        ("NA_Scenario_Cr", f"=SUM({T}[MV_Scenario_INR_Cr])", "inr_cr"),
        ("Marked_MV_Cr", (f'=SUMIFS({T}[MV_Mkt_INR_Cr],{role},"POSITION")-SUMIFS({T}[MV_Mkt_INR_Cr],{st},"MARKET_PASS_THROUGH")'), "inr_cr"),
        ("Position_Weight", f'=SUMIFS({w},{role},"POSITION")', "pct"),
        ("Matched_Weight", f'=SUMIFS({w},{T}[Holdings_Match_Status],"MATCHED")', "pct"),
        ("Unmatched_Count", f'=COUNTIFS({role},"POSITION",{T}[Holdings_Match_Status],"<>MATCHED")', "count"),
        ("No_Price_Count", f'=COUNTIFS({T}[Holdings_Match_Status],"NO_PRICE")', "count"),
        ("Equity_Weight", (f'=SUMIFS({w},{role},"POSITION",{asset},"Indian listed equity")'
                           f'+SUMIFS({w},{role},"POSITION",{asset},"Foreign listed equity")'), "pct"),
        ("Valued_Weight", f'=SUMIFS({w},{st},"MODEL_VALUED")', "pct"),
        ("Covered_Weight", f'=SUMIFS({w},{st},"<>UNVALUED")', "pct"),
        ("Unvalued_Weight", f'=SUMIFS({w},{st},"UNVALUED")', "pct"),
        ("Unvalued_Count", f'=COUNTIFS({st},"UNVALUED")', "count"),
        ("Unvalued_Value_Cr", f'=SUMIFS({T}[Market_Value_INR_Cr],{st},"UNVALUED")', "inr_cr"),
        ("Stale_Cutoff_Date", '=IF(OR(in_Valuation_Date="",in_Financials_Stale_Days=""),"",in_Valuation_Date-in_Financials_Stale_Days)', "date"),
        ("Fresh_Valued_Weight", f'=IF([@Stale_Cutoff_Date]="","",SUMIFS({w},{st},"MODEL_VALUED",{fin},">="&[@Stale_Cutoff_Date]))', "pct"),
        ("Stale_Valued_Weight", '=IF([@Stale_Cutoff_Date]="","",[@Valued_Weight]-[@Fresh_Valued_Weight])', "pct"),
        ("Oldest_Financials_Date", f'=IF(COUNTIFS({st},"MODEL_VALUED",{fin},">0")=0,"",MINIFS({fin},{st},"MODEL_VALUED"))', "date"),
    ]


def _pc(col: str) -> str:
    """Value of a tbl_Nav_PlanCalc column for this row's plan."""
    return xl.lookup(CALC, col, "[@Plan_ID]", "Plan_ID")


def summary_formulas() -> dict[str, str]:
    V, PD = "in_Valuation_Date", "in_Price_Date"
    off = "[@Official_NAV]"
    lines0 = f"{_pc('Holdings_Lines')}=0"

    def fair(sum_col: str) -> str:
        return f'=IF({off}="","",IF({lines0},NA(),{off}*(1+{_pc(sum_col)})))'

    def ratio(num: str) -> str:
        return f'=IF({off}="","",IF({lines0},NA(),IF({_pc("NA_Mkt_Cr")}=0,NA(),{off}*{_pc(num)}/{_pc("NA_Mkt_Cr")})))'

    reported = _pc("Reported_NA_Cr")
    equity = "[@Valuation_Coverage_Equity_Pct]"
    return {
        "Fund_ID": "=" + xl.lookup("tbl_FundPlans", "Fund_ID", "[@Plan_ID]", "Plan_ID"),
        "Portfolio_Date": "=" + _pc("Portfolio_Date"),
        # NAV used: the latest NAV on or before in_Price_Date; the gap is NAV_Date_Gap_Days (7.1).
        "NAV_Date": ('=IF(COUNTIFS(tbl_OfficialNAV[Plan_ID],[@Plan_ID],tbl_OfficialNAV[NAV_Date],"<="&' + PD + ")=0,\"\","
                     "MAXIFS(tbl_OfficialNAV[NAV_Date],tbl_OfficialNAV[Plan_ID],[@Plan_ID],tbl_OfficialNAV[NAV_Date],\"<=\"&" + PD + "))"),
        "Official_NAV": ('=IF([@NAV_Date]="","",SUMIFS(tbl_OfficialNAV[NAV_INR],tbl_OfficialNAV[Plan_ID],[@Plan_ID],'
                         "tbl_OfficialNAV[NAV_Date],[@NAV_Date]))"),
        "Fair_NAV_Base": fair("Sum_Adj_Base"), "Fair_NAV_Bear": fair("Sum_Adj_Bear"),
        "Fair_NAV_Bull": fair("Sum_Adj_Bull"), "Fair_NAV_Selected": fair("Sum_Adj_Selected"),
        "Fair_NAV_M2_Base": ratio("NA_Fair_Base_Cr"),
        "Scenario_Market_NAV": ratio("NA_Scenario_Cr"),
        "Diff_vs_Official_INR": f'=IF({off}="","",[@Fair_NAV_Base]-{off})',
        "Diff_vs_Official_Pct": f'=IF({off}="","",[@Fair_NAV_Base]/{off}-1)',
        "Price_Date": f'=IF({PD}="","",{PD})', "Valuation_Date": f'=IF({V}="","",{V})',
        # (1) holdings coverage, 7.5a
        "Holdings_Value_Coverage_Pct": f'=IF({reported}="","",{_pc("Disclosed_Total_Cr")}/{reported})',
        "Holdings_Match_Pct": (f'=IF({_pc("Position_Weight")}=0,IF({lines0},"",1),{_pc("Matched_Weight")}/{_pc("Position_Weight")})'),
        "Unmatched_Count": f'=IF({lines0},"",{_pc("Unmatched_Count")})',
        "Recon_Gap_Pct": f'=IF({reported}="","",{_pc("Disclosed_Total_Cr")}/{reported}-1)',
        "Recon_Status": '=IF([@Recon_Gap_Pct]="","MISSING",IF(ABS([@Recon_Gap_Pct])>in_Recon_Tolerance_Pct,"FAIL","PASS"))',
        "Holdings_Coverage_Status": ('=IF([@Recon_Status]="MISSING","MISSING",IF(AND([@Recon_Status]="PASS",[@Unmatched_Count]=0),"PASS","FAIL"))'),
        # (2) valuation coverage, 7.5b
        "Valuation_Coverage_Total_Pct": f'=IF({lines0},"",{_pc("Covered_Weight")})',
        "Valuation_Coverage_Equity_Pct": f'=IF(OR({lines0},{_pc("Equity_Weight")}=0),"",{_pc("Valued_Weight")}/{_pc("Equity_Weight")})',
        "Unvalued_Weight_Pct": f'=IF({lines0},"",{_pc("Unvalued_Weight")})',
        "Unvalued_Count": f'=IF({lines0},"",{_pc("Unvalued_Count")})',
        "Unvalued_Value_INR_Cr": f'=IF({lines0},"",{_pc("Unvalued_Value_Cr")})',
        "Valuation_Coverage_Status": (f'=IF({lines0},"MISSING",IF({equity}="",IF([@Unvalued_Count]=0,"PASS","FAIL"),'
                                      f'IF({equity}<in_Coverage_Fail,"FAIL",IF({equity}<in_Coverage_Warn,"WARNING","PASS"))))'),
        "Coverage_Caption": (f'=IF({lines0},"No holdings imported","Covers "&IF({equity}="","n/a",TEXT({equity}*100,"0.0")&"%")'
                             '&" of equity; "&TEXT([@Unvalued_Weight_Pct]*100,"0.0")&"% of net assets unvalued (adjustment 0)")'),
        # (3) freshness, 7.5c
        "Holdings_Age_Days": f'=IF(OR({V}="",[@Portfolio_Date]=""),"",{V}-[@Portfolio_Date])',
        "NAV_Date_Gap_Days": f'=IF(OR({V}="",[@NAV_Date]=""),"",{V}-[@NAV_Date])',
        "Max_Financials_Age_Days": f'=IF(OR({V}="",{_pc("Oldest_Financials_Date")}=""),"",{V}-{_pc("Oldest_Financials_Date")})',
        "Stale_Valued_Weight_Pct": f'=IF({V}="","",{_pc("Stale_Valued_Weight")})',
        "Freshness_Status": ('=IF(OR([@Holdings_Age_Days]="",[@NAV_Date_Gap_Days]=""),"MISSING",'
                             'IF(OR([@Holdings_Age_Days]>in_Holdings_Stale_Days,[@NAV_Date_Gap_Days]>in_Price_Stale_Days,'
                             'ROUND([@Stale_Valued_Weight_Pct],12)>0),"STALE","PASS"))'),
        "Method_Drift_INR": '=IF(OR([@Fair_NAV_Base]="",[@Fair_NAV_M2_Base]=""),"",[@Fair_NAV_Base]-[@Fair_NAV_M2_Base])',
    }


def build_nav_sheet(ctx: WorkbookContext, data, fund_tables: dict[str, str]) -> NavLayout:
    """fund_tables: Fund_ID -> holdings table name. Returns the layout other sheets rely on."""
    ws = ctx.sheet(OWNER, SHEET)
    plans = data.rows("fund_plans")
    plan_ids = tuple(r["Plan_ID"] for r in plans)
    plan_fund = {r["Plan_ID"]: r["Fund_ID"] for r in plans}
    unknown = sorted({f for f in plan_fund.values() if f not in fund_tables})
    if unknown:
        raise ValueError(f"no holdings table for fund(s) {unknown}")
    n = max(len(plan_ids), 1)

    stmt = _statement_items()
    statement_top = 2
    summary_top = statement_top + len(stmt) + 3 + GAP
    calc_top = summary_top + n + 1 + GAP + 1
    plans_top = calc_top + n + 1 + GAP + 1
    totals_top = plans_top + n + 1 + GAP + 1
    nav_top = totals_top + max(len(data.rows("fund_scheme_totals")), 1) + 1 + GAP + 1

    # ---- imported tables
    ctx.add_table(OWNER, SHEET, plans_top, 0, "tbl_FundPlans", xl.schema_table_columns(S.FUND_PLANS),
                  xl.stored_rows(S.FUND_PLANS, plans))
    ctx.add_table(OWNER, SHEET, totals_top, 0, "tbl_SchemeTotals", xl.schema_table_columns(S.FUND_SCHEME_TOTALS),
                  xl.stored_rows(S.FUND_SCHEME_TOTALS, data.rows("fund_scheme_totals")))
    ctx.add_table(OWNER, SHEET, nav_top, 0, "tbl_OfficialNAV", xl.schema_table_columns(S.OFFICIAL_NAV),
                  xl.stored_rows(S.OFFICIAL_NAV, data.rows("official_nav")))
    for top, title in ((plans_top, "tbl_FundPlans: imported, one row per plan"),
                       (totals_top, "tbl_SchemeTotals: reported scheme net assets at each Portfolio_Date"),
                       (nav_top, "tbl_OfficialNAV: published NAV history, never computed or overwritten (7.1)"),
                       (summary_top, "tbl_NAVSummary: one row per plan, headline = Method 1 (D-019)"),
                       (calc_top, "tbl_Nav_PlanCalc: per-plan sums over the plan's fund holdings table (helper for tbl_NAVSummary)")):
        xl.ws_note(ctx, SHEET, f"A{top}", title, bold=True)

    # ---- tbl_Nav_PlanCalc: each plan reads its own fund's holdings table
    col_specs = None
    calc_cols = []
    for i, pid in enumerate(plan_ids):
        specs = _calc_columns(fund_tables[plan_fund[pid]])
        if col_specs is None:
            col_specs = specs
            calc_cols = [TableColumn(name, role="imported" if f is None else "calc", number=num) for name, f, num in specs]
    if col_specs is None:
        col_specs = _calc_columns(next(iter(fund_tables.values())))
        calc_cols = [TableColumn(name, role="imported" if f is None else "calc", number=num) for name, f, num in col_specs]
    ctx.add_table(OWNER, SHEET, calc_top, 0, CALC, calc_cols, [[pid] + [None] * (len(calc_cols) - 1) for pid in plan_ids])
    for i, pid in enumerate(plan_ids):
        for j, (name, f, num) in enumerate(_calc_columns(fund_tables[plan_fund[pid]])):
            if f is not None:
                xl.write_row_formula(ctx, SHEET, CALC, calc_top, 0, i, j, f, number=num)

    # ---- tbl_NAVSummary: uniform calculated columns
    cols = xl.schema_table_columns(S.NAV_SUMMARY, summary_formulas(), sheet=SHEET)
    ctx.add_table(OWNER, SHEET, summary_top, 0, SUMMARY, cols, [[pid] for pid in plan_ids])
    _statement(ctx, ws, plan_ids, stmt, statement_top)
    zone_col = xl.col_name(0, len(plan_ids) + 3)
    ctx.reserve_chart_zone(OWNER, "NAV_COMPARE", SHEET, f"{zone_col}3",
                           "Official NAV, base/bear/bull fair NAV and scenario NAV comparison per plan (reads tbl_NAVSummary); "
                           "official NAV history versus modelled fair NAV range")
    ctx.reserve_chart_zone(OWNER, "NAV_COVERAGE_FRESHNESS", SHEET, f"{zone_col}25",
                           "Valuation coverage and source freshness: the three data-quality measures side by side, never one score")
    ws.set_column(0, 0, 70)
    ws.set_column(1, max(len(cols), len(calc_cols)), 18)
    return NavLayout(plan_ids, plan_fund, summary_top, calc_top, statement_top)


# --------------------------------------------------------------------------- statement block (WI-9)
def _statement_items() -> list[tuple[str, str, str]]:
    """(kind, label, field/number). kind: 'h' section header, 'v' summary value, 'c' calc-table value."""
    fair = OutputLabel.FAIR_NAV.value
    return [
        ("h", "OFFICIAL NAV (imported, never modelled)", ""),
        ("v", OutputLabel.OFFICIAL_NAV.value, "Official_NAV|inr"),
        ("v", "NAV date used (latest on or before the price date)", "NAV_Date|date"),
        ("h", "MODELLED INTRINSIC VALUE PER UNIT (estimate, not official NAV)", ""),
        ("v", f"{fair} | Method 1 Base (headline, D-019)", "Fair_NAV_Base|inr"),
        ("v", f"{fair} | Method 1 Bear", "Fair_NAV_Bear|inr"),
        ("v", f"{fair} | Method 1 Bull", "Fair_NAV_Bull|inr"),
        ("v", f"{fair} | Method 1 Selected scenario (current fair-value controls)", "Fair_NAV_Selected|inr"),
        ("v", f"{fair} | Method 2 Base (quantity-based, ratio form, D-004)", "Fair_NAV_M2_Base|inr"),
        ("v", "Coverage caption for the Fair NAV outputs above", "Coverage_Caption|general"),
        ("v", "Fair NAV (Base) minus Official NAV, INR per unit", "Diff_vs_Official_INR|inr"),
        ("v", "Fair NAV (Base) over Official NAV, minus 1", "Diff_vs_Official_Pct|pct"),
        ("v", "D2 Method drift: Method 1 minus Method 2, INR per unit", "Method_Drift_INR|inr"),
        ("h", "SCENARIO MARKET NAV (hypothetical prices, not official NAV)", ""),
        ("v", OutputLabel.SCENARIO_MARKET_NAV.value, "Scenario_Market_NAV|inr"),
        ("h", "HYPOTHETICAL REBALANCED PORTFOLIO VALUE: see PORTFOLIO_REBALANCING (not an existing fund)", ""),
        ("h", "(1) HOLDINGS COVERAGE: is the official portfolio imported and markable?", ""),
        ("v", "Imported value / reported scheme net assets", "Holdings_Value_Coverage_Pct|pct"),
        ("v", "Positions matched and priced (weight)", "Holdings_Match_Pct|pct"),
        ("v", "Positions not MATCHED (count)", "Unmatched_Count|count"),
        ("v", "Reconciliation gap vs reported net assets", "Recon_Gap_Pct|pct"),
        ("v", "Reconciliation status", "Recon_Status|general"),
        ("v", "Holdings coverage status", "Holdings_Coverage_Status|general"),
        ("h", "(2) VALUATION COVERAGE: how much has a valid fair value?", ""),
        ("v", "Valued weight, share of total net assets", "Valuation_Coverage_Total_Pct|pct"),
        ("v", "Valued weight, share of equity", "Valuation_Coverage_Equity_Pct|pct"),
        ("v", "Unvalued weight of net assets", "Unvalued_Weight_Pct|pct"),
        ("v", "Unvalued lines (count)", "Unvalued_Count|count"),
        ("v", "Unvalued lines (INR crore, disclosed value)", "Unvalued_Value_INR_Cr|inr_cr"),
        ("v", "Valuation coverage status", "Valuation_Coverage_Status|general"),
        ("h", "(3) DATA FRESHNESS: how old is each input? (each date shown separately)", ""),
        ("v", "Portfolio_Date (holdings disclosure)", "Portfolio_Date|date"),
        ("v", "NAV_Date", "NAV_Date|date"),
        ("v", "Price_Date", "Price_Date|date"),
        ("v", "Valuation_Date", "Valuation_Date|date"),
        ("v", "D1 Holdings age (days)", "Holdings_Age_Days|count"),
        ("v", "NAV date gap (days)", "NAV_Date_Gap_Days|count"),
        ("v", "Oldest financials behind a valued line (days)", "Max_Financials_Age_Days|count"),
        ("v", "Weight valued on stale or undated financials", "Stale_Valued_Weight_Pct|pct"),
        ("v", "Freshness status", "Freshness_Status|general"),
        ("h", "DIAGNOSTICS", ""),
        ("c", "D3 Price-date mix: positions with no price at the price date (listed on MF_COVERAGE_AUDIT)", "No_Price_Count|count"),
    ]


def _statement(ctx: WorkbookContext, ws, plan_ids, items, top: int) -> None:
    head = ctx.wb.add_format({"bold": True, "bg_color": "#DDEBF7", "font_name": "Calibri", "font_size": 10})
    xl.ws_note(ctx, SHEET, "A2", "NAV statement. Each value sits next to its fixed caption (WI-9). The five value outputs are "
               "never interchangeable; the three data-quality measures are never combined.", bold=True)
    hdr_row = top + 1
    ws.write(hdr_row - 1, 0, "Plan_ID", head)
    for j, pid in enumerate(plan_ids):
        ctx.write_value(OWNER, SHEET, f"{xl.col_name(0, j + 1)}{hdr_row}", pid, role="imported")
    for i, (kind, label, spec) in enumerate(items):
        r = hdr_row + 1 + i
        if kind == "h":
            ws.write(r - 1, 0, label, head)
            continue
        ws.write(r - 1, 0, label, ctx.wb.add_format({"font_name": "Calibri", "font_size": 10}))
        field, number = spec.split("|")
        table = SUMMARY if kind == "v" else CALC
        for j, _ in enumerate(plan_ids):
            col = xl.col_name(0, j + 1)
            f = f"=INDEX({table}[{field}],MATCH({col}${hdr_row},{table}[Plan_ID],0))"
            ctx.write_formula(OWNER, SHEET, f"{col}{r}", f, role="calc", number=number)
