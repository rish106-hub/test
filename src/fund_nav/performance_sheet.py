"""FUND_PERFORMANCE: contract 7.9 metrics from tbl_OfficialNAV history and tbl_BenchmarkTRI, and overlap (7.8).

Windows 1Y / 3Y / 5Y / 10Y end at the NAV used (tbl_NAVSummary[NAV_Date]) and start 365 x k days earlier. A
metric is blank, with the reason in Status, when the NAV history does not reach back to the window start; it
is never computed from a shorter history. Each row shows n (number of daily returns) and its window dates.
The benchmark is the plan's stated benchmark and only a TRI series is used; expense ratios are already inside
NAV and are not deducted again. Any return derived from current holdings is labelled a static-portfolio scenario.
"""
from __future__ import annotations

from datetime import date as _date, datetime as _dt

from src.common import schema as S
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl
from src.fund_nav.holdings import HoldingsLayout
from src.fund_nav.performance import DAYS_PER_YEAR_RETURN, TRADING_DAYS

OWNER = xl.OWNER
SHEET = "FUND_PERFORMANCE"
PERF, OVERLAP = "tbl_Nav_Perf", "tbl_Nav_Overlap"
WINDOWS = (("1Y", 1), ("3Y", 3), ("5Y", 5), ("10Y", 10))
RF, MAR, MARD = "$B$4", "$B$5", "$B$6"
xl.register_private_table(PERF, SHEET)
xl.register_private_table(OVERLAP, SHEET)


def hist_table(plan_id: str) -> str:
    return f"tbl_Nav_Hist_{xl.safe_name(plan_id)}"


def _c(name, formula, number="general"):
    if formula is None:
        return TableColumn(name, role="imported", number=number)
    return TableColumn(name, formula=formula, role=xl.role_of(formula, SHEET), number=number)


def _hist_columns(plan_id: str) -> list[TableColumn]:
    H = hist_table(plan_id)
    cols = [
        _c("Idx", None, "count"), _c("NAV_Date", None, "date"),
        _c("NAV", f"=SUMIFS(tbl_OfficialNAV[NAV_INR],tbl_OfficialNAV[Plan_ID],{xl.ids(plan_id)},tbl_OfficialNAV[NAV_Date],[@NAV_Date])", "inr"),
        _c("Prev_NAV", f'=IF([@Idx]=1,"",INDEX({H}[NAV],MATCH([@Idx]-1,{H}[Idx],0)))', "inr"),
        _c("Ret", '=IF([@Prev_NAV]="","",[@NAV]/[@Prev_NAV]-1)', "pct"),
    ]
    for w, _ in WINDOWS:
        key = xl.ids(f"{plan_id}|{w}")
        base = f"INDEX({PERF}[Base_Date],MATCH({key},{PERF}[Key],0))"
        end = f"INDEX({PERF}[End_Date],MATCH({key},{PERF}[Key],0))"
        cols += [
            _c(f"Ret_{w}", f'=IF(OR({base}="",[@Ret]=""),"",IF(AND([@NAV_Date]>{base},[@NAV_Date]<={end}),[@Ret],""))', "pct"),
            _c(f"DownSq_{w}", f'=IF(OR([@Ret_{w}]="",{MARD}=""),"",MIN([@Ret_{w}]-{MARD},0)^2)', "general"),
            _c(f"Peak_{w}", (f'=IF({base}="","",IF(OR([@NAV_Date]<{base},[@NAV_Date]>{end}),"",'
                             f'MAXIFS({H}[NAV],{H}[NAV_Date],">="&{base},{H}[Idx],"<="&[@Idx])))'), "inr"),
            _c(f"DD_{w}", f'=IF([@Peak_{w}]="","",[@NAV]/[@Peak_{w}]-1)', "pct"),
        ]
    return cols


def _perf_columns(plan_id: str, w: str) -> list[tuple[str, str | None, str]]:
    H, B = hist_table(plan_id), "tbl_BenchmarkTRI"
    pid = xl.ids(plan_id)
    name = xl.lookup("tbl_FundPlans", "Benchmark_Name", pid, "Plan_ID")
    tri = f"{B}[Is_TRI],TRUE"

    def bench_date(limit, require_reach):
        reach = f'COUNTIFS({B}[Benchmark_Name],[@Benchmark_Name],{B}[Date],">="&[@End_Date],{tri})=0' if require_reach else "FALSE"
        return (f'=IF(OR([@End_Date]="",[@Start_Target]="",{reach}),"",'
                f'IF(COUNTIFS({B}[Benchmark_Name],[@Benchmark_Name],{B}[Date],"<="&[@{limit}],{tri})=0,"",'
                f'MAXIFS({B}[Date],{B}[Benchmark_Name],[@Benchmark_Name],{B}[Date],"<="&[@{limit}],{tri})))')

    def bench_value(date_col):
        return (f'=IF([@{date_col}]="","",SUMIFS({B}[Index_Value],{B}[Benchmark_Name],[@Benchmark_Name],{B}[Date],[@{date_col}],{tri}))')

    return [
        ("Key", None, "general"), ("Plan_ID", None, "general"), ("Window", None, "general"), ("Days", None, "count"),
        ("End_Date", f'=IF(INDEX(tbl_NAVSummary[NAV_Date],MATCH([@Plan_ID],tbl_NAVSummary[Plan_ID],0))="","",INDEX(tbl_NAVSummary[NAV_Date],MATCH([@Plan_ID],tbl_NAVSummary[Plan_ID],0)))', "date"),
        ("Start_Target", '=IF([@End_Date]="","",[@End_Date]-[@Days])', "date"),
        ("Base_Date", f'=IF([@Start_Target]="","",IF(COUNTIFS({H}[NAV_Date],"<="&[@Start_Target])=0,"",MAXIFS({H}[NAV_Date],{H}[NAV_Date],"<="&[@Start_Target])))', "date"),
        ("N_Returns", f'=IF(OR([@Base_Date]="",[@End_Date]=""),0,COUNTIFS({H}[NAV_Date],">"&[@Base_Date],{H}[NAV_Date],"<="&[@End_Date]))', "count"),
        ("NAV_Base", f'=IF([@Base_Date]="","",SUMIFS({H}[NAV],{H}[NAV_Date],[@Base_Date]))', "inr"),
        ("NAV_End", f'=IF([@Base_Date]="","",SUMIFS({H}[NAV],{H}[NAV_Date],[@End_Date]))', "inr"),
        ("Return", '=IF([@Base_Date]="","",[@NAV_End]/[@NAV_Base]-1)', "pct"),
        ("CAGR", f'=IF([@Base_Date]="","",([@NAV_End]/[@NAV_Base])^({DAYS_PER_YEAR_RETURN}/[@Days])-1)', "pct"),
        ("Benchmark_Name", "=" + name, "general"),
        ("Bench_Base_Date", bench_date("Start_Target", False), "date"),
        ("Bench_End_Date", bench_date("End_Date", True), "date"),
        ("Bench_Base_Value", bench_value("Bench_Base_Date"), "general"),
        ("Bench_End_Value", bench_value("Bench_End_Date"), "general"),
        ("Bench_Return", '=IF(OR([@Bench_Base_Value]="",[@Bench_End_Value]="",[@Base_Date]=""),"",[@Bench_End_Value]/[@Bench_Base_Value]-1)', "pct"),
        ("Excess_Return", '=IF(OR([@Return]="",[@Bench_Return]=""),"",[@Return]-[@Bench_Return])', "pct"),
        ("Volatility", f'=IF(COUNT({H}[Ret_{w}])<2,"",STDEV.S({H}[Ret_{w}])*SQRT({TRADING_DAYS}))', "pct"),
        ("Max_Drawdown", f'=IF(COUNT({H}[DD_{w}])=0,"",MIN({H}[DD_{w}]))', "pct"),
        ("Downside_Deviation", f'=IF(OR(COUNT({H}[DownSq_{w}])=0,{MARD}=""),"",SQRT(AVERAGE({H}[DownSq_{w}]))*SQRT({TRADING_DAYS}))', "pct"),
        ("Sharpe", f'=IF(OR([@CAGR]="",[@Volatility]="",{RF}=""),"",IF([@Volatility]=0,"",([@CAGR]-{RF})/[@Volatility]))', "general"),
        ("Sortino", f'=IF(OR([@CAGR]="",[@Downside_Deviation]="",{MAR}=""),"",IF([@Downside_Deviation]=0,"",([@CAGR]-{MAR})/[@Downside_Deviation]))', "general"),
        ("Status", ('=IF([@End_Date]="","No NAV at or before the price date",IF([@Base_Date]="",'
                    '"Insufficient history: no NAV on or before "&TEXT([@Start_Target],"yyyy-mm-dd"),'
                    'IF([@N_Returns]<2,"Too few observations","OK")))'), "general"),
    ]


def build_performance_sheet(ctx: WorkbookContext, data, layouts: dict[str, HoldingsLayout], plan_ids, plan_fund) -> None:
    ws = ctx.sheet(OWNER, SHEET)
    plain = ctx.wb.add_format({"font_name": "Calibri", "font_size": 10})
    head = ctx.wb.add_format({"bold": True, "bg_color": "#DDEBF7", "font_name": "Calibri", "font_size": 10})
    xl.ws_note(ctx, SHEET, "A2", "Fund performance (contract 7.9). Metrics come from the Official NAV history and the stated benchmark TRI; "
               "a blank cell means the history is too short, never zero.", bold=True)
    ws.write(2, 0, "Risk-free rate and MAR are inputs (GLOBAL_ASSUMPTIONS in_Risk_Free_Rate); blank keeps Sharpe, Sortino and downside deviation blank.", plain)
    for r, (label, f, role, num) in enumerate((
            ("Risk-free rate for Sharpe (decimal)", '=IF(in_Risk_Free_Rate="","",in_Risk_Free_Rate)', "link", "pct"),
            ("Minimum acceptable return for Sortino / downside (default = risk-free rate; overtype to change)", '=IF(in_Risk_Free_Rate="","",in_Risk_Free_Rate)', "link", "pct"),
            ("Daily MAR = (1 + MAR)^(1/252) - 1", f'=IF({MAR}="","",(1+{MAR})^(1/{TRADING_DAYS})-1)', "calc", "general")), start=4):
        ws.write(r - 1, 0, label, plain)
        ctx.write_formula(OWNER, SHEET, f"B{r}", f, role=role, number=num)

    # ---- overlap (7.8) between the first two funds
    fids = list(layouts)
    top = 8
    if len(fids) >= 2:
        a, b = fids[:2]
        Ta, Tb = layouts[a].table, layouts[b].table
        secs = sorted({r["Security_ID"] for r in data.rows("fund_holdings")
                       if r["Line_Role"] == "POSITION" and r["Security_ID"]})
        cols = [_c("Security_ID", None),
                _c(f"Weight_{a}", f'=SUMIFS({Ta}[Weight_Pct_of_Scheme_NAV],{Ta}[Security_ID],[@Security_ID],{Ta}[Line_Role],"POSITION")', "pct"),
                _c(f"Weight_{b}", f'=SUMIFS({Tb}[Weight_Pct_of_Scheme_NAV],{Tb}[Security_ID],[@Security_ID],{Tb}[Line_Role],"POSITION")', "pct"),
                _c("Common", f"=IF(AND([@Weight_{a}]>0,[@Weight_{b}]>0),1,0)", "count"),
                _c("Min_Weight", f"=IF([@Common]=1,MIN([@Weight_{a}],[@Weight_{b}]),0)", "pct"),
                _c(f"Value_INR_Cr_{a}", f'=SUMIFS({Ta}[Market_Value_INR_Cr],{Ta}[Security_ID],[@Security_ID],{Ta}[Line_Role],"POSITION")', "inr_cr"),
                _c(f"Value_INR_Cr_{b}", f'=SUMIFS({Tb}[Market_Value_INR_Cr],{Tb}[Security_ID],[@Security_ID],{Tb}[Line_Role],"POSITION")', "inr_cr"),
                _c("Min_Value_INR_Cr", f"=IF([@Common]=1,MIN([@Value_INR_Cr_{a}],[@Value_INR_Cr_{b}]),0)", "inr_cr")]
        xl.ws_note(ctx, SHEET, f"A{top}", f"Overlap between {a} and {b} (contract 7.8): sum of the smaller weight of each common security", bold=True)
        ctx.add_table(OWNER, SHEET, top, 0, OVERLAP, cols, [[s] for s in secs])
        n = max(len(secs), 1)
        r = top + n + 3
        for i, (label, f, num) in enumerate((
                ("Overlap by weight (sum of min weights)", f"=SUM({OVERLAP}[Min_Weight])", "pct"),
                ("Common securities (count)", f"=SUM({OVERLAP}[Common])", "count"),
                ("Overlap by market value (sum of min value, INR crore)", f"=SUM({OVERLAP}[Min_Value_INR_Cr])", "inr_cr"))):
            ws.write(r + i - 1, 0, label, plain)
            ctx.write_formula(OWNER, SHEET, f"B{r + i}", f, role="calc", number=num)
        top = r + 5

    # ---- static-portfolio scenario (labelled, not a forecast)
    xl.ws_note(ctx, SHEET, f"A{top}", "STATIC-PORTFOLIO SCENARIO: a return derived from current holdings is not a forecast of the actively managed fund", bold=True)
    ws.write(top, 0, "Plan_ID", head)
    for j, pid in enumerate(plan_ids):
        ctx.write_value(OWNER, SHEET, f"{xl.col_name(0, j + 1)}{top + 1}", pid, role="imported")
    ws.write(top + 1, 0, "Fair NAV (Base) over Official NAV, minus 1: static-portfolio mark-to-model scenario", plain)
    for j, pid in enumerate(plan_ids):
        col = xl.col_name(0, j + 1)
        ctx.write_formula(OWNER, SHEET, f"{col}{top + 2}", f"=INDEX(tbl_NAVSummary[Diff_vs_Official_Pct],MATCH({col}${top + 1},tbl_NAVSummary[Plan_ID],0))",
                          role="link", number="pct")
    top += 6

    # ---- tbl_Nav_Perf
    rows = [(p, w, k) for p in plan_ids for w, k in WINDOWS]
    specs0 = _perf_columns(plan_ids[0] if plan_ids else "NONE", "1Y")
    cols = [TableColumn(n, role="imported" if f is None else "calc", number=num) for n, f, num in specs0]   # cells carry per-plan formulas
    xl.ws_note(ctx, SHEET, f"A{top}", "Performance metrics by plan and window (stated benchmark TRI; n and window dates shown; blank = insufficient history)", bold=True)
    ctx.add_table(OWNER, SHEET, top, 0, PERF, cols,
                  [[f"{p}|{w}", p, w, k * DAYS_PER_YEAR_RETURN] + [None] * (len(cols) - 4) for p, w, k in rows])
    for i, (p, w, k) in enumerate(rows):
        for j, (n, f, num) in enumerate(_perf_columns(p, w)):
            if f is not None:
                xl.write_row_formula(ctx, SHEET, PERF, top, 0, i, j, f, number=num)
    perf_end = top + len(rows) + 1
    ctx.reserve_chart_zone(OWNER, "PERF_NAV_HISTORY", SHEET, f"{xl.col_name(0, len(cols) + 2)}{top}",
                           "Official NAV history versus modelled fair NAV range; rolling returns (reads tbl_OfficialNAV and tbl_NAVSummary)")

    # ---- benchmark TRI (imported) and per-plan NAV history helpers, to the right of the metrics
    left = len(cols) + 3
    xl.ws_note(ctx, SHEET, f"{xl.col_name(left, 0)}{top}", "tbl_BenchmarkTRI: imported benchmark index history (TRI only is used)", bold=True)
    ctx.add_table(OWNER, SHEET, top, left, "tbl_BenchmarkTRI", xl.schema_table_columns(S.BENCHMARK_TRI),
                  xl.stored_rows(S.BENCHMARK_TRI, data.rows("benchmark_tri")))
    left += len(S.BENCHMARK_TRI.columns) + 2
    for pid in plan_ids:
        H = hist_table(pid)
        xl.register_private_table(H, SHEET)
        dates = sorted({r["NAV_Date"] for r in data.rows("official_nav") if r["Plan_ID"] == pid})
        cols_h = _hist_columns(pid)
        vals = [[i + 1, _dt.combine(_date.fromisoformat(d), _dt.min.time())] for i, d in enumerate(dates)] or [[1, None]]
        xl.ws_note(ctx, SHEET, f"{xl.col_name(left, 0)}{top}", f"{H}: NAV history of {pid} with window helper columns", bold=True)
        ctx.add_table(OWNER, SHEET, top, left, H, cols_h, vals)
        left += len(cols_h) + 2
    ws.set_column(0, 0, 70)
    ws.set_column(1, 30, 16)
