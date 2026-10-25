"""MF_SECTOR_ANALYSIS and MF_NAV_SENSITIVITY.

Sector weights per fund, contribution of each sector to the fair-NAV difference (it sums to the total),
coverage by sector, and a comparison of the two funds. Sensitivity: change in fair NAV for a +/- FV change,
by sector and for the ten largest holdings. Everything is a formula over the holdings tables, so it moves
with every control (spec manual test 8).
"""
from __future__ import annotations

from src.common.enums import Sector
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl
from src.fund_nav.audit import audit_table
from src.fund_nav.holdings import HoldingsLayout

OWNER = xl.OWNER
SECTOR_SHEET, SENS_SHEET = "MF_SECTOR_ANALYSIS", "MF_NAV_SENSITIVITY"
SENS_DELTA_CELL = "$B$3"

for _f in xl.FUND_SHEETS:
    xl.register_private_table(f"tbl_Nav_Sector_{_f}", SECTOR_SHEET)
    xl.register_private_table(f"tbl_Nav_SensSector_{_f}", SENS_SHEET)
    xl.register_private_table(f"tbl_Nav_SensTop10_{_f}", SENS_SHEET)
xl.register_private_table("tbl_Nav_SectorCompare", SECTOR_SHEET)


def _official(plan_id: str) -> str:
    return xl.lookup("tbl_NAVSummary", "Official_NAV", xl.ids(plan_id), "Plan_ID")


def _col(name: str, formula: str | None, sheet: str, number: str = "general") -> TableColumn:
    if formula is None:
        return TableColumn(name, role="imported", number=number)
    return TableColumn(name, formula=formula, role=xl.role_of(formula, sheet), number=number)


def build_sector_sheet(ctx: WorkbookContext, data, layouts: dict[str, HoldingsLayout], plan_fund: dict[str, str]) -> None:
    ws = ctx.sheet(OWNER, SECTOR_SHEET)
    xl.ws_note(ctx, SECTOR_SHEET, "A2", "Sector analysis (Method 1 Base). Contribution = official NAV x the sum of line adjustments in the "
               "sector; contributions sum to the total fair-NAV difference exactly.", bold=True)
    sectors = [[s.value] for s in Sector]
    top = 4
    fmt_b = ctx.wb.add_format({"bold": True, "font_name": "Calibri", "font_size": 10})
    for fid, lay in layouts.items():
        T = lay.table
        plans = [p for p, f in plan_fund.items() if f == fid]
        w, st, sec = f"{T}[Weight_Pct_of_Scheme_NAV]", f"{T}[Valuation_Coverage_Status]", f"{T}[Sector]"
        cols = [
            _col("Sector", None, SECTOR_SHEET),
            _col("Weight_Pct", f"=SUMIFS({w},{sec},[@Sector])", SECTOR_SHEET, "pct"),
            _col("Disclosed_Value_INR_Cr", f"=SUMIFS({T}[Market_Value_INR_Cr],{sec},[@Sector])", SECTOR_SHEET, "inr_cr"),
            _col("Adj_Base_Sum", f"=SUMIFS({T}[Adj_Base],{sec},[@Sector])", SECTOR_SHEET, "pct"),
            _col("Valued_Weight_Pct", f'=SUMIFS({w},{sec},[@Sector],{st},"MODEL_VALUED")', SECTOR_SHEET, "pct"),
            _col("Unvalued_Weight_Pct", f'=SUMIFS({w},{sec},[@Sector],{st},"UNVALUED")', SECTOR_SHEET, "pct"),
            _col("Valued_Count", f'=COUNTIFS({sec},[@Sector],{st},"MODEL_VALUED")', SECTOR_SHEET, "count"),
            _col("Unvalued_Count", f'=COUNTIFS({sec},[@Sector],{st},"UNVALUED")', SECTOR_SHEET, "count"),
            _col("Sector_Coverage_Pct", '=IF([@Valued_Weight_Pct]+[@Unvalued_Weight_Pct]=0,"",[@Valued_Weight_Pct]/([@Valued_Weight_Pct]+[@Unvalued_Weight_Pct]))',
                 SECTOR_SHEET, "pct"),
            _col("Coverage_State", ('=IF([@Valued_Count]+[@Unvalued_Count]=0,"No valued or unvalued positions",'
                                    'IF([@Unvalued_Count]=0,"Valued",IF([@Valued_Count]=0,"Unvalued","Partially valued")))'), SECTOR_SHEET),
        ]
        for p in plans:
            cols.append(_col(f"Contribution_INR_{xl.safe_name(p)}",
                             f'=IF({_official(p)}="","",{_official(p)}*[@Adj_Base_Sum])', SECTOR_SHEET, "inr"))
        name = f"tbl_Nav_Sector_{fid}"
        xl.ws_note(ctx, SECTOR_SHEET, f"A{top}", f"FUND {fid}: sector weights, contribution to fair NAV (Method 1 Base) and coverage", bold=True)
        ctx.add_table(OWNER, SECTOR_SHEET, top, 0, name, cols, sectors)
        tot_row = top + len(sectors) + 3          # Excel row of the totals line (one blank row below the table)
        ws.write(tot_row - 1, 0, "Total / check", fmt_b)
        for j, c in enumerate(cols):
            if c.header in ("Weight_Pct", "Disclosed_Value_INR_Cr", "Adj_Base_Sum", "Valued_Weight_Pct", "Unvalued_Weight_Pct",
                            "Valued_Count", "Unvalued_Count") or c.header.startswith("Contribution_INR_"):
                ctx.write_formula(OWNER, SECTOR_SHEET, f"{xl.col_name(0, j)}{tot_row}", f"=SUM({name}[{c.header}])",
                                  role="calc", number=c.number)
        ws.write(tot_row, 0, "Difference vs tbl_NAVSummary (must be 0)", fmt_b)
        for p in plans:
            hdr = f"Contribution_INR_{xl.safe_name(p)}"
            j = [c.header for c in cols].index(hdr)
            ctx.write_formula(OWNER, SECTOR_SHEET, f"{xl.col_name(0, j)}{tot_row + 1}",
                              f'=IF({_official(p)}="","",{xl.col_name(0, j)}{tot_row}-('
                              f'{xl.lookup("tbl_NAVSummary", "Fair_NAV_Base", xl.ids(p), "Plan_ID")}-{_official(p)}))',
                              role="link", number="inr")
        ctx.reserve_chart_zone(OWNER, f"{fid}_SECTOR_ALLOC", SECTOR_SHEET, f"{xl.col_name(0, len(cols) + 2)}{top}",
                               f"Actual sector allocation of {fid} (doughnut/bar); sector exposure vs technology, consumer, metals, defence; "
                               f"sector valuation-adjustment contribution (waterfall); sector valuation coverage")
        top += len(sectors) + 8

    # ---- comparison of the funds (first two funds, side by side)
    fids = list(layouts)
    xl.ws_note(ctx, SECTOR_SHEET, f"A{top}", "Comparison of funds: sector weight and market value", bold=True)
    cols = [_col("Sector", None, SECTOR_SHEET)]
    for fid in fids:
        T = layouts[fid].table
        cols.append(_col(f"Weight_Pct_{fid}", f"=SUMIFS({T}[Weight_Pct_of_Scheme_NAV],{T}[Sector],[@Sector])", SECTOR_SHEET, "pct"))
        cols.append(_col(f"Value_INR_Cr_{fid}", f"=SUMIFS({T}[Market_Value_INR_Cr],{T}[Sector],[@Sector])", SECTOR_SHEET, "inr_cr"))
    if len(fids) >= 2:
        a, b = fids[:2]
        cols.append(_col(f"Weight_Diff_{a}_minus_{b}", f"=[@Weight_Pct_{a}]-[@Weight_Pct_{b}]", SECTOR_SHEET, "pct"))
    ctx.add_table(OWNER, SECTOR_SHEET, top, 0, "tbl_Nav_SectorCompare", cols, sectors)
    ctx.reserve_chart_zone(OWNER, "MF_SECTOR_COMPARE", SECTOR_SHEET, f"{xl.col_name(0, len(cols) + 2)}{top}",
                           "Sector market value and sector weight comparison between the two mutual funds")
    ws.set_column(0, 0, 40)
    ws.set_column(1, 20, 20)


def build_sensitivity_sheet(ctx: WorkbookContext, data, layouts: dict[str, HoldingsLayout], plan_fund: dict[str, str]) -> None:
    ws = ctx.sheet(OWNER, SENS_SHEET)
    xl.ws_note(ctx, SENS_SHEET, "A2", "Fair-NAV sensitivity (Method 1 Base). Change in fair NAV if the model fair values of the "
               "VALUED lines move by +/- the percentage below. UNVALUED lines have no fair value and no sensitivity (flagged).", bold=True)
    ws.write(2, 0, "Fair-value change tested (decimal, blue input)", ctx.wb.add_format({"font_name": "Calibri", "font_size": 10}))
    ctx.write_value(OWNER, SENS_SHEET, "B3", 0.10, role="input", number="pct")
    ws.data_validation("B3", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 0.99})
    sectors = [[s.value] for s in Sector]
    top = 5
    for fid, lay in layouts.items():
        T, A = lay.table, audit_table(fid)
        plans = [p for p, f in plan_fund.items() if f == fid]
        w, st, sec = f"{T}[Weight_Pct_of_Scheme_NAV]", f"{T}[Valuation_Coverage_Status]", f"{T}[Sector]"
        # sum of w x FV/P over valued lines = sum(Adj) + sum(w), because Adj = w (FV/P - 1)
        cols = [_col("Sector", None, SENS_SHEET),
                _col("FV_Exposure_Pct", f'=SUMIFS({T}[Adj_Base],{sec},[@Sector])+SUMIFS({w},{sec},[@Sector],{st},"MODEL_VALUED")', SENS_SHEET, "pct"),
                _col("Delta_NAV_Pct", f"=[@FV_Exposure_Pct]*{SENS_DELTA_CELL}", SENS_SHEET, "pct")]
        for p in plans:
            n = xl.safe_name(p)
            cols.append(_col(f"Delta_Up_INR_{n}", f'=IF({_official(p)}="","",{_official(p)}*[@Delta_NAV_Pct])', SENS_SHEET, "inr"))
            cols.append(_col(f"Delta_Down_INR_{n}", f'=IF({_official(p)}="","",-{_official(p)}*[@Delta_NAV_Pct])', SENS_SHEET, "inr"))
        xl.ws_note(ctx, SENS_SHEET, f"A{top}", f"FUND {fid}: change in fair NAV per unit for a +/- FV change, by sector", bold=True)
        ctx.add_table(OWNER, SENS_SHEET, top, 0, f"tbl_Nav_SensSector_{fid}", cols, sectors)
        top += len(sectors) + 4

        look = lambda col: (f'=IF([@Holding_Line_ID]="","",INDEX({A}[{col}],MATCH([@Holding_Line_ID],{A}[Holding_Line_ID],0)))')   # noqa: E731
        cols = [_col("Rank", None, SENS_SHEET, "count"),
                _col("Holding_Line_ID", f'=IF(ISNA(MATCH([@Rank],{A}[Pos_Rank],0)),"",INDEX({A}[Holding_Line_ID],MATCH([@Rank],{A}[Pos_Rank],0)))', SENS_SHEET),
                _col("Instrument", look("Instrument"), SENS_SHEET), _col("Sector", look("Sector"), SENS_SHEET),
                _col("Weight_Pct", look("Weight_Pct"), SENS_SHEET, "pct"),
                _col("Coverage_Status", look("Coverage_Status"), SENS_SHEET),
                _col("FV_Exposure_Pct", (f'=IF([@Coverage_Status]="MODEL_VALUED",INDEX({T}[Adj_Base],MATCH([@Holding_Line_ID],{T}[Holding_Line_ID],0))+[@Weight_Pct],"")'),
                     SENS_SHEET, "pct"),
                _col("Delta_NAV_Pct", f'=IF([@FV_Exposure_Pct]="","",[@FV_Exposure_Pct]*{SENS_DELTA_CELL})', SENS_SHEET, "pct")]
        for p in plans:
            n = xl.safe_name(p)
            cols.append(_col(f"Delta_Up_INR_{n}", f'=IF(OR([@Delta_NAV_Pct]="",{_official(p)}=""),"",{_official(p)}*[@Delta_NAV_Pct])', SENS_SHEET, "inr"))
            cols.append(_col(f"Delta_Down_INR_{n}", f'=IF(OR([@Delta_NAV_Pct]="",{_official(p)}=""),"",-{_official(p)}*[@Delta_NAV_Pct])', SENS_SHEET, "inr"))
        xl.ws_note(ctx, SENS_SHEET, f"A{top}", f"FUND {fid}: ten largest positions by weight (an UNVALUED position shows no sensitivity)", bold=True)
        ctx.add_table(OWNER, SENS_SHEET, top, 0, f"tbl_Nav_SensTop10_{fid}", cols, [[k] for k in range(1, 11)])
        ctx.reserve_chart_zone(OWNER, f"{fid}_TOP10", SENS_SHEET, f"{xl.col_name(0, len(cols) + 2)}{top}",
                               f"Top ten holdings of {fid} by portfolio weight; largest positive and negative contributors; "
                               "fund NAV sensitivity to selected sectors and material holdings")
        top += 10 + 5
    ws.set_column(0, 0, 40)
    ws.set_column(1, 20, 20)
