"""MF_SCENARIO_BUILDER: Scenario Market NAV under the current controls, plus a uniform market-move grid.

The grid is a what-if computed by formula from tbl_Nav_PlanCalc: it moves the ORIGINAL price of every marked
position by the percentage in column A and touches no control (spec manual test 8 uses the real controls on
SCENARIO_ANALYSIS; this table only shows the shape of the exposure).
"""
from __future__ import annotations

from src.common.enums import OutputLabel
from src.common.workbook import WorkbookContext
from src.fund_nav import xl

OWNER = xl.OWNER
SHEET = "MF_SCENARIO_BUILDER"
MOVES = (-0.30, -0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20, 0.30)


def build_scenario_builder(ctx: WorkbookContext, data, plan_ids) -> None:
    ws = ctx.sheet(OWNER, SHEET)
    head = ctx.wb.add_format({"bold": True, "bg_color": "#DDEBF7", "font_name": "Calibri", "font_size": 10})
    plain = ctx.wb.add_format({"font_name": "Calibri", "font_size": 10})
    xl.ws_note(ctx, SHEET, "A2", "Scenario builder. Controls are changed only on SCENARIO_ANALYSIS; this sheet reads their result.", bold=True)
    ws.write(3, 0, "Plan_ID", head)
    for j, pid in enumerate(plan_ids):
        ctx.write_value(OWNER, SHEET, f"{xl.col_name(0, j + 1)}4", pid, role="imported")

    def ns(field, col):
        return f"INDEX(tbl_NAVSummary[{field}],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0))"

    rows = [
        ("h", "SCENARIO MARKET NAV under the current price controls", None, None),
        ("f", OutputLabel.OFFICIAL_NAV.value, lambda c: "=" + ns("Official_NAV", c), "inr"),
        ("f", OutputLabel.SCENARIO_MARKET_NAV.value, lambda c: "=" + ns("Scenario_Market_NAV", c), "inr"),
        ("f", "Scenario Market NAV minus Official NAV, INR per unit", lambda c: f'=IF({c}6="","",{c}7-{c}6)', "inr"),
        ("f", "Scenario Market NAV over Official NAV, minus 1", lambda c: f'=IF({c}6="","",{c}7/{c}6-1)', "pct"),
        ("h", "FAIR VALUE under the current fair-value controls (separate output, never mixed with the market scenario)", None, None),
        ("f", OutputLabel.FAIR_NAV.value + " | Selected scenario", lambda c: "=" + ns("Fair_NAV_Selected", c), "inr"),
        ("f", "Coverage caption", lambda c: "=" + ns("Coverage_Caption", c), "general"),
    ]
    r = 5
    for kind, label, fn, number in rows:
        if kind == "h":
            ws.write(r - 1, 0, label, head)
        else:
            ws.write(r - 1, 0, label, plain)
            for j, _ in enumerate(plan_ids):
                col = xl.col_name(0, j + 1)
                ctx.write_formula(OWNER, SHEET, f"{col}{r}", fn(col), role="link" if "tbl_" in fn(col) else "calc", number=number)
        r += 1
    r += 1
    ws.write(r - 1, 0, "Controls in force (SCENARIO_ANALYSIS)", head)
    r += 1
    for label, field in (("Controls_At_Default", "Controls_At_Default"), ("Securities with an ignored-input warning", "Controls_With_Warning"),
                         ("Securities whose price control FAILS", "Controls_FAIL"), ("Securities UNVALUED", "Controls_UNVALUED")):
        ws.write(r - 1, 0, label, plain)
        ctx.write_formula(OWNER, SHEET, f"B{r}", f"=INDEX(tbl_Nav_ControlsStatus[{field}],1)", role="link")
        r += 1

    r += 1
    grid_head = r
    ws.write(r - 1, 0, "UNIFORM MARKET-MOVE GRID: what-if only; every marked position's ORIGINAL price moves by the % in column A. "
             "No control is touched. Scenario Market NAV per unit:", head)
    r += 1
    ws.write(r - 1, 0, "Uniform market move (decimal; blue, editable)", plain)
    for j, pid in enumerate(plan_ids):
        ctx.write_formula(OWNER, SHEET, f"{xl.col_name(0, j + 1)}{r}", f"={xl.col_name(0, j + 1)}$4", role="calc")
    hdr = r
    r += 1
    for m in MOVES:
        ctx.write_value(OWNER, SHEET, f"A{r}", m, role="input", number="pct")
        for j, pid in enumerate(plan_ids):
            col = xl.col_name(0, j + 1)
            pc = lambda c: xl.lookup("tbl_Nav_PlanCalc", c, f"{col}${hdr}", "Plan_ID")      # noqa: E731
            f = (f'=IF(OR({ns("Official_NAV", col)}="",{pc("NA_Mkt_Cr")}=0),"",'
                 f'{ns("Official_NAV", col)}*({pc("NA_Mkt_Cr")}+$A{r}*{pc("Marked_MV_Cr")})/{pc("NA_Mkt_Cr")})')
            ctx.write_formula(OWNER, SHEET, f"{col}{r}", f, role="link", number="inr")
        r += 1
    ws.write(r, 0, "Caption: " + OutputLabel.SCENARIO_MARKET_NAV.value + ". Ordinary and pass-through lines are held at their disclosed value.", plain)
    ctx.reserve_chart_zone(OWNER, "SCENARIO_NAV_GRID", SHEET, f"{xl.col_name(0, len(plan_ids) + 3)}4",
                           "Scenario NAV under user-controlled price shocks (uniform-move grid, G rows below the header)")
    ctx.reserve_chart_zone(OWNER, "SCENARIO_NAV_COMPARE", SHEET, f"{xl.col_name(0, len(plan_ids) + 3)}24",
                           "Official NAV, base/bear/bull fair NAV and scenario NAV comparison (reads tbl_NAVSummary)")
    ws.set_column(0, 0, 70)
    ws.set_column(1, 8, 20)
