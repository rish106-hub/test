"""PORTFOLIO_REBALANCING: custom allocation (purple inputs) and the Method 4 hypothetical portfolio (R011).

Everything here is labelled OutputLabel.HYPOTHETICAL_PORTFOLIO and is never attached to a fund's NAV. This
sheet reads Selected_Scenario_* from tbl_PriceControls and the actual holdings (for the sector comparison);
no actual-holdings formula reads anything on this sheet (T-CUS-03).
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.common import link_patterns as L
from src.common import schema as S
from src.common.enums import OutputLabel, Sector
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl
from src.fund_nav.holdings import HoldingsLayout
from src.scenarios.sheets import TOP_SECTOR

OWNER = xl.OWNER
SHEET = "PORTFOLIO_REBALANCING"
CA, CHK, HYPO, HSEC = "tbl_CustomAllocation", "tbl_Nav_AllocCheck", "tbl_Nav_Hypo", "tbl_Nav_HypoSector"
for _t in (CHK, HYPO, HSEC):
    xl.register_private_table(_t, SHEET)
SYNTHETIC_ALLOCATION = Path(__file__).resolve().parents[2] / "tests" / "fund_nav" / "fixtures" / "custom_allocation_synthetic.csv"
N_LINES = 25
CAP, TC, TOL = "$B$4", "$B$5", "$B$6"      # capital, transaction cost, validation tolerance cells


def allocation_rows(data) -> list[dict]:
    """User rows from data/scenarios/custom_allocation.csv; a test build with none uses the synthetic example."""
    rows = list(data.rows("custom_allocation"))
    if not rows and data.test_build and SYNTHETIC_ALLOCATION.exists():
        with SYNTHETIC_ALLOCATION.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    return rows


def _col(name, formula, number="general", role=None):
    if formula is None:
        return TableColumn(name, role=role or "imported", number=number)
    return TableColumn(name, formula=formula, role=role or xl.role_of(formula, SHEET), number=number)


def build_rebalancing_sheet(ctx: WorkbookContext, data, layouts: dict[str, HoldingsLayout]) -> None:
    ws = ctx.sheet(OWNER, SHEET)
    plain = ctx.wb.add_format({"font_name": "Calibri", "font_size": 10})
    head = ctx.wb.add_format({"bold": True, "bg_color": "#EADCF4", "font_name": "Calibri", "font_size": 10})
    xl.ws_note(ctx, SHEET, "A2", OutputLabel.HYPOTHETICAL_PORTFOLIO.value + ". Purple cells are hypothetical inputs. "
               "Rebalancing does not change an existing fund's NAV (R011).", bold=True)
    for r, (label, f, role, num) in enumerate((
            ("Capital (INR; GLOBAL_ASSUMPTIONS in_Hypo_Capital_INR)", '=IF(in_Hypo_Capital_INR="","",in_Hypo_Capital_INR)', "link", "inr"),
            ("Transaction cost (decimal; in_Default_TC_Pct)", '=IF(in_Default_TC_Pct="","",in_Default_TC_Pct)', "link", "pct")), start=4):
        ws.write(r - 1, 0, label, plain)
        ctx.write_formula(OWNER, SHEET, f"B{r}", f, role=role, number=num)
    ws.write(5, 0, "Validation tolerance on weight sums (contract 7.6)", plain)
    ctx.write_value(OWNER, SHEET, "B6", 1e-6, role="input")

    # ---- tbl_CustomAllocation (purple inputs)
    top = 9
    user = allocation_rows(data)
    ids = [r["Line_ID"] for r in user] + [f"CA-{i:03d}" for i in range(len(user) + 1, N_LINES + 1)]
    n = len(ids)
    by_id = {r["Line_ID"]: r for r in user}
    value_cols = [c for c in S.CUSTOM_ALLOCATION.stored_columns]

    def val(line_id, c):
        raw = (by_id.get(line_id) or {}).get(c.name, "")
        return None if raw in ("", None) else (float(raw) if c.dtype == "float" else raw)
    cols = []
    for c in S.CUSTOM_ALLOCATION.columns:
        if c.origin == "stored":
            cols.append(TableColumn(c.name, role="imported" if c.name == "Line_ID" else "override", number=xl.number_for(c)))
        else:
            f = '=IF(OR(NOT(ISNUMBER([@Sector_Weight_Pct])),NOT(ISNUMBER([@Constituent_Weight_Pct]))),"",[@Sector_Weight_Pct]*[@Constituent_Weight_Pct])'
            cols.append(TableColumn(c.name, formula=f, role="calc", number="pct"))
    xl.ws_note(ctx, SHEET, f"A{top}", "Custom allocation (hypothetical only). Effective weight = sector weight x constituent weight. "
               "A line with no Security_ID is explicit cash / unallocated.", bold=True)
    ctx.add_table(OWNER, SHEET, top, 0, CA, cols, [[val(i, c) if c.name != "Line_ID" else i for c in value_cols] for i in ids])
    first, last = top + 1, top + n
    ws.data_validation(first, 1, last, 1, {"validate": "list", "source": f"=SCENARIO_ANALYSIS!$A${TOP_SECTOR + 2}:$A${TOP_SECTOR + 1 + len(Sector)}"})
    for cidx in (3, 4):
        ws.data_validation(first, cidx, last, cidx, {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 1,
                                                     "ignore_blank": True, "error_message": "A weight as a decimal from 0 to 1."})
    ws.data_validation(first, 5, last, 5, {"validate": "decimal", "criteria": ">", "value": 0, "ignore_blank": True})
    ws.data_validation(first, 6, last, 6, {"validate": "decimal", "criteria": ">=", "value": 0, "ignore_blank": True})

    # ---- tbl_Nav_AllocCheck: contract 7.6 validation, one row per allocation line
    ctop = last + 4
    cl = lambda col: xl.lookup(CA, col, "[@Line_ID]", "Line_ID")                                 # noqa: E731
    bs = lambda col: f'IF({cl(col)}="","",{cl(col)})'                                            # noqa: E731
    cc = [
        _col("Line_ID", None), _col("Sector", "=" + bs("Sector")), _col("Security_ID", "=" + bs("Security_ID")),
        _col("SW", "=" + bs("Sector_Weight_Pct"), "pct"), _col("CW", "=" + bs("Constituent_Weight_Pct"), "pct"),
        _col("Is_Cash", '=IF(AND([@Sector]<>"",[@Security_ID]=""),1,0)', "count"),
        _col("Is_Sec", '=IF(AND([@Sector]<>"",[@Security_ID]<>""),1,0)', "count"),
        _col("Negative", '=IF(OR(AND(ISNUMBER([@SW]),[@SW]<0),AND(ISNUMBER([@CW]),[@CW]<0)),1,0)', "count"),
        _col("Duplicate", f'=IF([@Is_Sec]=1,IF(COUNTIFS({CHK}[Security_ID],[@Security_ID],{CHK}[Is_Sec],1)>1,1,0),0)', "count"),
        _col("SW_Share", f'=IF([@Is_Sec]=1,[@SW]/COUNTIFS({CHK}[Sector],[@Sector],{CHK}[Is_Sec],1),0)', "pct"),
        _col("Cash_Weight", '=IF([@Is_Cash]=1,[@SW]*[@CW],0)', "pct"),
        _col("Sector_Weights_Differ", f'=IF([@Sector]="",0,IF(MAXIFS({CHK}[SW],{CHK}[Sector],[@Sector])<>MINIFS({CHK}[SW],{CHK}[Sector],[@Sector]),1,0))', "count"),
        _col("Constituents_Not_One", (f'=IF(OR([@Sector]="",NOT(ISNUMBER([@SW]))),0,IF([@SW]=0,0,'
                                      f'IF(ABS(SUMIFS({CHK}[CW],{CHK}[Sector],[@Sector])-1)>{TOL},1,0)))'), "count"),
    ]
    xl.ws_note(ctx, SHEET, f"A{ctop}", "tbl_Nav_AllocCheck: validation helper (contract 7.6)", bold=True)
    ctx.add_table(OWNER, SHEET, ctop, 0, CHK, cc, [[i] for i in ids])
    vtop = ctop + n + 3
    checks = [
        ("Sector weights + explicit cash = 1 (total)", f"=SUM({CHK}[SW_Share])+SUM({CHK}[Cash_Weight])", "pct"),
        ("Check: total differs from 1 beyond tolerance (1 = problem)", f"=IF(ABS(B{vtop + 1}-1)>{TOL},1,0)", "count"),
        ("Lines with a negative weight", f"=SUM({CHK}[Negative])", "count"),
        ("Duplicate Security_ID lines", f"=SUM({CHK}[Duplicate])", "count"),
        ("Lines of one sector that state different sector weights", f"=SUM({CHK}[Sector_Weights_Differ])", "count"),
        ("Lines in a sector whose constituent weights do not sum to 1", f"=SUM({CHK}[Constituents_Not_One])", "count"),
        ("Lines in use", f"=SUM({CHK}[Is_Sec])+SUM({CHK}[Is_Cash])", "count"),
        ("Allocation status", f'=IF(B{vtop + 7}=0,"EMPTY",IF(B{vtop + 2}+B{vtop + 3}+B{vtop + 4}+B{vtop + 5}+B{vtop + 6}=0,"PASS","FAIL"))', "general"),
    ]
    xl.ws_note(ctx, SHEET, f"A{vtop}", "Allocation validation", bold=True)
    for i, (label, f, num) in enumerate(checks):
        ws.write(vtop + i, 0, label, plain)
        ctx.write_formula(OWNER, SHEET, f"B{vtop + 1 + i}", f, role="calc", number=num)
    status_cell = f"$B${vtop + 8}"

    # ---- tbl_Nav_Hypo: Method 4, per allocation line
    htop = vtop + len(checks) + 3
    pcl = lambda col: L.blank_safe("tbl_PriceControls", col, "[@Security_ID]")                   # noqa: E731
    sec = '[@Security_ID]=""'
    hc = [
        _col("Line_ID", None), _col("Sector", f'=INDEX({CHK}[Sector],MATCH([@Line_ID],{CHK}[Line_ID],0))'),
        _col("Security_ID", f'=INDEX({CHK}[Security_ID],MATCH([@Line_ID],{CHK}[Line_ID],0))'),
        _col("Effective_Weight_Pct", f'=IF({sec},"",{cl("Effective_Weight_Pct")})', "pct"),
        _col("Scenario_Price_INR", f'=IF({sec},"",INDEX(tbl_PriceControls[Selected_Scenario_Market_Price],MATCH([@Security_ID],tbl_PriceControls[Security_ID],0)))', "inr"),
        _col("Scenario_Fair_Value_INR", f'=IF({sec},"",{pcl("Selected_Scenario_Fair_Value")})', "inr"),
        _col("Assumed_Buy_Price_INR", f'=IF({sec},"",{bs("Assumed_Buy_Price_INR")})', "inr"),
        _col("Quantity_Override", f'=IF({sec},"",{bs("Quantity_Override")})', "count"),
        _col("Buy_Price_INR", f'=IF({sec},"",IF([@Assumed_Buy_Price_INR]<>"",[@Assumed_Buy_Price_INR],[@Scenario_Price_INR]))', "inr"),
        _col("Target_Value_INR", f'=IF(OR({sec},{CAP}=""),"",{CAP}*[@Effective_Weight_Pct])', "inr"),
        _col("Quantity", (f'=IF({sec},"",IF([@Quantity_Override]<>"",[@Quantity_Override],IF(OR([@Target_Value_INR]="",{TC}=""),"",'
                          f'INT([@Target_Value_INR]/([@Buy_Price_INR]*(1+{TC}))))))'), "count"),
        _col("Cost_INR", f'=IF(OR({sec},[@Quantity]=""),"",[@Quantity]*[@Buy_Price_INR])', "inr"),
        _col("Fee_INR", f'=IF(OR([@Cost_INR]="",{TC}=""),"",[@Cost_INR]*{TC})', "inr"),
        _col("Market_Value_INR", f'=IF(OR({sec},[@Quantity]=""),"",[@Quantity]*[@Scenario_Price_INR])', "inr"),
        _col("Fair_Basis", f'=IF({sec},"",IF([@Scenario_Fair_Value_INR]="","AT MARKET (unvalued, flagged)","FAIR VALUE"))'),
        _col("Fair_Or_Market_Value_INR", (f'=IF(OR({sec},[@Quantity]=""),"",IF([@Scenario_Fair_Value_INR]="",[@Market_Value_INR],'
                                          "[@Quantity]*[@Scenario_Fair_Value_INR]))"), "inr"),
        _col("Weight_Squared", f'=IF({sec},0,IF(ISNUMBER([@Effective_Weight_Pct]),[@Effective_Weight_Pct]^2,0))', "general"),
    ]
    xl.ws_note(ctx, SHEET, f"A{htop}", "Method 4 hypothetical portfolio, per line: " + OutputLabel.HYPOTHETICAL_PORTFOLIO.value, bold=True)
    ctx.add_table(OWNER, SHEET, htop, 0, HYPO, hc, [[i] for i in ids])
    ototal = htop + n + 3
    cash_f = (f'=IF(OR({CAP}="",{TC}=""),"",{CAP}-SUM({HYPO}[Cost_INR])-SUM({HYPO}[Fee_INR]))')
    outs = [
        ("Cash remaining after purchases and fees (INR)", cash_f, "inr"),
        ("Portfolio status (cash must be >= 0)", f'=IF(B{ototal + 1}="","MISSING INPUT",IF(ROUND(B{ototal + 1},6)>=0,"PASS","FAIL"))', "general"),
        (OutputLabel.HYPOTHETICAL_PORTFOLIO.value + " | at scenario market prices (INR)",
         f'=IF(B{ototal + 1}="","",SUM({HYPO}[Market_Value_INR])+B{ototal + 1})', "inr"),
        (OutputLabel.HYPOTHETICAL_PORTFOLIO.value + " | at selected fair values, unvalued lines at market (INR)",
         f'=IF(B{ototal + 1}="","",SUM({HYPO}[Fair_Or_Market_Value_INR])+B{ototal + 1})', "inr"),
        ("Fair over market value, minus 1 (a valuation gap, not a return forecast)", f'=IF(OR(B{ototal + 3}="",B{ototal + 4}=""),"",B{ototal + 4}/B{ototal + 3}-1)', "pct"),
        ("Unvalued lines carried at market (count)", f'=COUNTIFS({HYPO}[Fair_Basis],"AT MARKET*")', "count"),
        ("Largest single-security weight", f"=MAX({HYPO}[Effective_Weight_Pct])", "pct"),
        ("Concentration (sum of squared weights, HHI)", f"=SUM({HYPO}[Weight_Squared])", "general"),
        ("Allocation validation status", f"={status_cell}", "general"),
    ]
    xl.ws_note(ctx, SHEET, f"A{ototal}", "Hypothetical portfolio outputs (never an existing fund's NAV)", bold=True)
    for i, (label, f, num) in enumerate(outs):
        ws.write(ototal + i, 0, label, plain)
        ctx.write_formula(OWNER, SHEET, f"B{ototal + 1 + i}", f, role=xl.role_of(f, SHEET), number=num)

    # ---- sector comparison: custom vs actual funds (chart feed)
    stop = ototal + len(outs) + 3
    sc = [_col("Sector", None), _col("Custom_Weight_Pct", (f"=SUMIFS({HYPO}[Effective_Weight_Pct],{HYPO}[Sector],[@Sector])"
                                                     f"+SUMIFS({CHK}[Cash_Weight],{CHK}[Sector],[@Sector])"), "pct")]
    for fid, lay in layouts.items():
        T = lay.table
        sc.append(_col(f"Actual_Weight_Pct_{fid}", f"=SUMIFS({T}[Weight_Pct_of_Scheme_NAV],{T}[Sector],[@Sector])", "pct"))
    xl.ws_note(ctx, SHEET, f"A{stop}", "Hypothetical sector weights versus the actual funds", bold=True)
    ctx.add_table(OWNER, SHEET, stop, 0, HSEC, sc, [[s.value] for s in Sector])
    ctx.reserve_chart_zone(OWNER, "HYPO_SECTOR_WEIGHTS", SHEET, f"{xl.col_name(0, len(sc) + 2)}{stop}",
                           "Custom hypothetical sector allocation versus actual fund allocation; hypothetical portfolio's sector "
                           "and constituent weights after rebalancing")
    ws.set_column(0, 0, 62)
    ws.set_column(1, 20, 18)
