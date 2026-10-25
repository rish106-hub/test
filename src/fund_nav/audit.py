"""MF_COVERAGE_AUDIT: what is unvalued, unmatched or stale, and why (brief item 5, contract 7.5, spec manual test 8).

No FILTER or dynamic arrays (D-002). For each fund a private index table `tbl_Nav_Audit_<fund>` has one row per
holdings line with 0/1 flags and a running sequence number per list (COUNTIFS on an explicit Idx key, never a
row position). The visible lists look up "the k-th flagged line", so they re-evaluate whenever a control or an
input changes. The index tables are also the feed for MF_NAV_SENSITIVITY's top-10 holdings.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.common import link_patterns as L
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl
from src.fund_nav.holdings import HoldingsLayout

OWNER = xl.OWNER
SHEET = "MF_COVERAGE_AUDIT"
INDEX_LEFT = 16          # column Q: index tables sit to the right of the visible lists


def audit_table(fund_id: str) -> str:
    return f"tbl_Nav_Audit_{fund_id}"


for _f in xl.FUND_SHEETS:
    xl.register_private_table(audit_table(_f), SHEET)
    for _k in ("Unvalued", "NotMatched", "StaleValued", "ControlIssue"):
        xl.register_private_table(f"tbl_Nav_Audit{_k}_{_f}", SHEET)


@dataclass(frozen=True)
class AuditLayout:
    fund_id: str
    table: str
    top: int
    n: int


def _index_columns(T: str, fund_id: str) -> list[TableColumn]:
    A = audit_table(fund_id)
    ix = lambda col: xl.lookup(T, col, "[@Holding_Line_ID]", "Holding_Line_ID")       # noqa: E731
    bs = lambda col: f'IF({ix(col)}="","",{ix(col)})'                                  # noqa: E731
    cols = [
        ("Idx", None, "count"), ("Holding_Line_ID", None, "general"),
        ("Line_Role", "=" + bs("Line_Role"), "general"),
        ("Instrument", "=" + bs("Instrument_Name_As_Disclosed"), "general"),
        ("Security_ID", "=" + bs("Security_ID"), "general"),
        ("Sector", "=" + bs("Sector"), "general"),
        ("Asset_Class", "=" + bs("Asset_Class"), "general"),
        ("Weight_Pct", "=" + ix("Weight_Pct_of_Scheme_NAV"), "pct"),
        ("Disclosed_Value_INR_Cr", "=" + ix("Market_Value_INR_Cr"), "inr_cr"),
        ("Match_Status", "=" + bs("Holdings_Match_Status"), "general"),
        ("Coverage_Status", "=" + ix("Valuation_Coverage_Status"), "general"),
        ("Financials_As_Of", "=" + bs("Financials_As_Of"), "date"),
        ("Entity_ID", '=IF([@Security_ID]="","",' + L.blank_safe("tbl_Registry", "Entity_ID") + ")", "general"),
        ("Control_Status", '=IF([@Security_ID]="","",' + L.blank_safe("tbl_PriceControls", "Control_Status") + ")", "general"),
        ("Control_Warning", '=IF([@Security_ID]="","",' + L.blank_safe("tbl_PriceControls", "Control_Warning") + ")", "general"),
        ("Is_Unvalued", '=IF([@Coverage_Status]="UNVALUED",1,0)', "count"),
        ("Is_Not_Matched", '=IF(AND([@Line_Role]="POSITION",[@Match_Status]<>"MATCHED"),1,0)', "count"),
        ("Is_Stale_Valued", ('=IF(AND([@Coverage_Status]="MODEL_VALUED",in_Valuation_Date<>""),'
                             'IF([@Financials_As_Of]="",1,IF(in_Valuation_Date-[@Financials_As_Of]>in_Financials_Stale_Days,1,0)),0)'), "count"),
        ("Is_Control_Issue", '=IF(OR(LEFT([@Control_Status],4)="FAIL",[@Control_Warning]<>""),1,0)', "count"),
        ("Seq_Unvalued", f'=IF([@Is_Unvalued]=1,COUNTIFS({A}[Is_Unvalued],1,{A}[Idx],"<="&[@Idx]),"")', "count"),
        ("Seq_Not_Matched", f'=IF([@Is_Not_Matched]=1,COUNTIFS({A}[Is_Not_Matched],1,{A}[Idx],"<="&[@Idx]),"")', "count"),
        ("Seq_Stale_Valued", f'=IF([@Is_Stale_Valued]=1,COUNTIFS({A}[Is_Stale_Valued],1,{A}[Idx],"<="&[@Idx]),"")', "count"),
        ("Seq_Control_Issue", f'=IF([@Is_Control_Issue]=1,COUNTIFS({A}[Is_Control_Issue],1,{A}[Idx],"<="&[@Idx]),"")', "count"),
        ("Pos_Weight", '=IF([@Line_Role]="POSITION",[@Weight_Pct],"")', "pct"),
        ("Pos_Rank", (f'=IF([@Pos_Weight]="","",COUNTIFS({A}[Pos_Weight],">"&[@Pos_Weight])'
                      f'+COUNTIFS({A}[Pos_Weight],[@Pos_Weight],{A}[Idx],"<"&[@Idx])+1)'), "count"),
        ("Latest_Price_Date", ('=IF(OR([@Line_Role]<>"POSITION",[@Security_ID]=""),"",IF(COUNTIFS(tbl_MarketPrices[Security_ID],[@Security_ID])=0,"",'
                              "MAXIFS(tbl_MarketPrices[Price_Date],tbl_MarketPrices[Security_ID],[@Security_ID])))"), "date"),
        ("FX_Gap_Days", ('=IF(AND([@Asset_Class]="Foreign listed equity",[@Match_Status]="MATCHED"),'
                         "in_Price_Date-MAXIFS(tbl_MarketPrices[FX_Date],tbl_MarketPrices[Security_ID],[@Security_ID],"
                         'tbl_MarketPrices[Price_Date],in_Price_Date),"")'), "count"),
        ("Local_Close_Timestamp", ('=IF(AND([@Asset_Class]="Foreign listed equity",[@Match_Status]="MATCHED"),'
                                   "IF(INDEX(tbl_MarketPrices[Local_Close_Timestamp],MATCH(1,INDEX((tbl_MarketPrices[Security_ID]=[@Security_ID])"
                                   "*(tbl_MarketPrices[Price_Date]=in_Price_Date),0),0))=\"\",\"not stated\","
                                   "INDEX(tbl_MarketPrices[Local_Close_Timestamp],MATCH(1,INDEX((tbl_MarketPrices[Security_ID]=[@Security_ID])"
                                   '*(tbl_MarketPrices[Price_Date]=in_Price_Date),0),0))),"")'), "general"),
        ("Open_Missing_Items", ('=IF([@Security_ID]="",0,COUNTIFS(tbl_MissingData[Entity_or_Fund_ID],[@Security_ID],tbl_MissingData[Status],"Open")'
                               '+IF([@Entity_ID]="",0,COUNTIFS(tbl_MissingData[Entity_or_Fund_ID],[@Entity_ID],tbl_MissingData[Status],"Open")))'), "count"),
        ("Reason", ('=IF([@Is_Not_Matched]=1,IF([@Match_Status]="UNMATCHED","Not matched: no registry Security_ID for this line",'
                    '"Not priced: security known but no price at the price date"),'
                    'IF([@Is_Unvalued]=1,"No valid model fair value for this security (tbl_ValuationOutputs)",""))'), "general"),
    ]
    return [TableColumn(n, formula=f, role=xl.role_of(f, SHEET) if f else "imported", number=num) for n, f, num in cols]


def _list_table(ctx, name: str, top: int, A: str, n: int, seq_col: str, fields: list[tuple[str, str, str]]) -> None:
    """fields: (header, source column in the index table or '#expr', number). Visible 'k-th flagged line' list."""
    look = lambda col: (f'=IF([@Holding_Line_ID]="","",INDEX({A}[{col}],MATCH([@Holding_Line_ID],{A}[Holding_Line_ID],0)))')   # noqa: E731
    cols = [TableColumn("K", role="imported", number="count"),
            TableColumn("Holding_Line_ID", formula=f'=IF(ISNA(MATCH([@K],{A}[{seq_col}],0)),"",INDEX({A}[Holding_Line_ID],MATCH([@K],{A}[{seq_col}],0)))',
                        role="calc")]
    for header, src, num in fields:
        f = src[1:] if src.startswith("#") else look(src)
        cols.append(TableColumn(header, formula=f, role=xl.role_of(f, SHEET), number=num))
    ctx.add_table(OWNER, SHEET, top, 0, name, cols, [[k] for k in range(1, n + 1)])


def build_audit_sheet(ctx: WorkbookContext, data, layouts: dict[str, HoldingsLayout], plan_ids, plan_fund) -> dict[str, AuditLayout]:
    ws = ctx.sheet(OWNER, SHEET)
    xl.ws_note(ctx, SHEET, "A2", "Coverage audit (contract 7.5). Every list below is formula-driven and updates when any control or input "
               "changes. Nothing here is hidden or zero-filled (R009).", bold=True)
    # ---- warnings block, one column per plan
    head = ctx.wb.add_format({"bold": True, "bg_color": "#DDEBF7", "font_name": "Calibri", "font_size": 10})
    ws.write(3, 0, "Plan_ID", head)
    for j, pid in enumerate(plan_ids):
        ctx.write_value(OWNER, SHEET, f"{xl.col_name(0, j + 1)}4", pid, role="imported")
    audits: dict[str, AuditLayout] = {}
    rows_top = 12
    # index tables first so their positions are known
    idx_top = 4
    for fid, lay in layouts.items():
        n = max(len(lay.line_ids), 1)
        ctx.add_table(OWNER, SHEET, idx_top, INDEX_LEFT, audit_table(fid), _index_columns(lay.table, fid),
                      [[i + 1, lid] for i, lid in enumerate(lay.line_ids)] or [[1, None]])
        xl.ws_note(ctx, SHEET, f"{xl.col_name(INDEX_LEFT, 0)}{idx_top}", f"{audit_table(fid)}: one row per holdings line of {fid} (helper for the lists)", bold=True)
        audits[fid] = AuditLayout(fid, audit_table(fid), idx_top, n)
        idx_top += n + 5

    msgs = [
        ("Holdings date (D1)", lambda pid, A, col: (
            f'=IF(INDEX(tbl_NAVSummary[Holdings_Age_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))="","MISSING: holdings or valuation date not available",'
            f'IF(INDEX(tbl_NAVSummary[Holdings_Age_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))>in_Holdings_Stale_Days,'
            f'"WARNING: holdings snapshot is "&INDEX(tbl_NAVSummary[Holdings_Age_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))&" days old (limit "&in_Holdings_Stale_Days&")",'
            f'"OK: holdings snapshot is "&INDEX(tbl_NAVSummary[Holdings_Age_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))&" days old"))')),
        ("NAV date gap", lambda pid, A, col: (
            f'=IF(INDEX(tbl_NAVSummary[NAV_Date_Gap_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))="","MISSING: NAV date not available",'
            f'IF(INDEX(tbl_NAVSummary[NAV_Date_Gap_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))>in_Price_Stale_Days,'
            f'"WARNING: official NAV is "&INDEX(tbl_NAVSummary[NAV_Date_Gap_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))&" days before the valuation date (limit "&in_Price_Stale_Days&")",'
            f'"OK: official NAV is "&INDEX(tbl_NAVSummary[NAV_Date_Gap_Days],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))&" days before the valuation date"))')),
        ("Price date mix (D3)", lambda pid, A, col: (
            f'=IF(COUNTIFS({A}[Match_Status],"NO_PRICE")>0,"WARNING: "&COUNTIFS({A}[Match_Status],"NO_PRICE")&" position(s) have no price dated "'
            f'&TEXT(in_Price_Date,"yyyy-mm-dd")&" (latest available dates are in the index table)","OK: every matched position is priced at the price date")')),
        ("FX timestamps (D4)", lambda pid, A, col: (
            f'=IF(COUNTIFS({A}[Asset_Class],"Foreign listed equity")=0,"OK: no foreign-listed lines",'
            f'"INFO: "&COUNTIFS({A}[Asset_Class],"Foreign listed equity")&" foreign line(s); largest FX-date gap vs price date: "&MAX({A}[FX_Gap_Days])&" day(s)")')),
        ("Unvalued lines", lambda pid, A, col: f"=SUM({A}[Is_Unvalued])"),
        ("Lines not MATCHED", lambda pid, A, col: f"=SUM({A}[Is_Not_Matched])"),
        ("Valued lines on stale financials", lambda pid, A, col: f"=SUM({A}[Is_Stale_Valued])"),
        ("Held securities with a control FAIL or ignored-input warning", lambda pid, A, col: f"=SUM({A}[Is_Control_Issue])"),
    ]
    for i, (label, fn) in enumerate(msgs):
        r = 5 + i
        ws.write(r - 1, 0, label, ctx.wb.add_format({"font_name": "Calibri", "font_size": 10}))
        for j, pid in enumerate(plan_ids):
            col = xl.col_name(0, j + 1)
            ctx.write_formula(OWNER, SHEET, f"{col}{r}", fn(pid, audit_table(plan_fund[pid]), col), role="link")
    ctx.reserve_chart_zone(OWNER, "AUDIT_COVERAGE_BY_SECTOR", SHEET, "I4",
                           "Sector valuation coverage showing valued, partially valued and unvalued positions (reads tbl_Nav_Sector_*)")
    ws.set_column(0, 0, 44)
    ws.set_column(1, 15, 22)
    ws.set_column(INDEX_LEFT, INDEX_LEFT + 40, 16)

    # ---- visible lists, per fund
    top = rows_top + len(msgs)
    lists = [
        ("Unvalued", "UNVALUED lines (weight and value at risk): market price used, adjustment 0, flagged", "Seq_Unvalued",
         [("Instrument", "Instrument", "general"), ("Weight_Pct", "Weight_Pct", "pct"), ("Disclosed_Value_INR_Cr", "Disclosed_Value_INR_Cr", "inr_cr"),
          ("Reason", "Reason", "general"), ("Open_Missing_Items", "Open_Missing_Items", "count")]),
        ("NotMatched", "Lines not MATCHED (7.5a): the line cannot be marked, Methods 2 and 3 show #N/A until resolved", "Seq_Not_Matched",
         [("Instrument", "Instrument", "general"), ("Weight_Pct", "Weight_Pct", "pct"), ("Match_Status", "Match_Status", "general"),
          ("Reason", "Reason", "general")]),
        ("StaleValued", "Valued lines resting on stale or undated financials (7.5c)", "Seq_Stale_Valued",
         [("Instrument", "Instrument", "general"), ("Weight_Pct", "Weight_Pct", "pct"), ("Financials_As_Of", "Financials_As_Of", "date"),
          ("Financials_Age_Days", '#IF([@Holding_Line_ID]="","",IF([@Financials_As_Of]="","undated",in_Valuation_Date-[@Financials_As_Of]))', "count")]),
        ("ControlIssue", "Held securities whose price controls FAIL or carry an ignored-input warning", "Seq_Control_Issue",
         [("Security_ID", "Security_ID", "general"), ("Control_Status", "Control_Status", "general"), ("Control_Warning", "Control_Warning", "general")]),
    ]
    for fid, lay in layouts.items():
        A, n = audit_table(fid), audits[fid].n
        xl.ws_note(ctx, SHEET, f"A{top}", f"FUND {fid} ({lay.sheet})", bold=True)
        top += 1
        for key, title, seq, fields in lists:
            xl.ws_note(ctx, SHEET, f"A{top}", title, bold=True)
            _list_table(ctx, f"tbl_Nav_Audit{key}_{fid}", top, A, n, seq, fields)
            top += n + 4
    return audits
