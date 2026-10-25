"""Sheets owned by 00-main: START_HERE, GLOBAL_ASSUMPTIONS, METRIC_DICTIONARY,
MODEL_GOVERNANCE, VALIDATION_CHECKS (first) and EXECUTIVE_DASHBOARD (after modules)."""
from __future__ import annotations

import csv
from pathlib import Path

from src.common import schema as S
from src.common.enums import CheckResult, OutputLabel
from src.common.rows import typed_rows, typed_value
from src.common.styles import FONT_BY_ROLE
from src.common.workbook import TableColumn, WorkbookContext

OWNER = "00-main"
ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DEFINITIONS = [
    (OutputLabel.OFFICIAL_NAV, "Published NAV for the exact scheme, plan, option and date (AMFI/AMC). Imported, never modelled."),
    (OutputLabel.FAIR_NAV, "Official NAV adjusted by the fair values of the disclosed holdings. Static-portfolio estimate; see coverage caption."),
    (OutputLabel.SCENARIO_MARKET_NAV, "The disclosed portfolio marked at the selected scenario market prices. Not a forecast."),
    (OutputLabel.HYPOTHETICAL_PORTFOLIO, "A separate user-built basket on PORTFOLIO_REBALANCING. Never an existing fund."),
    (OutputLabel.TARGET_PURCHASE_PRICE, "Per security: selected scenario fair value x (1 - required margin of safety). One definition (D-023)."),
]


def _table_from_schema(ctx, sheet, top, table: S.Table, rows, roles: dict[str, str] | None = None, numbers=None):
    cols = []
    for c in table.stored_columns:
        role = (roles or {}).get(c.name, "imported")
        number = (numbers or {}).get(c.name) or ("date" if c.dtype == "date" else "general")
        cols.append(TableColumn(c.name, role=role, number=number))
    ctx.add_table(OWNER, sheet, top, 0, table.excel_name, cols, typed_rows(table, rows))


def build_sheets(ctx: WorkbookContext, data) -> None:
    _start_here(ctx, data)
    _global_assumptions(ctx, data)
    ctx.sheet(OWNER, "METRIC_DICTIONARY")
    _table_from_schema(ctx, "METRIC_DICTIONARY", 2, S.METRIC_DICTIONARY, data.rows("metric_dictionary"))
    ctx.sheet(OWNER, "MODEL_GOVERNANCE")
    _table_from_schema(ctx, "MODEL_GOVERNANCE", 2, S.GOVERNANCE_LOG, data.rows("governance_log"))
    _validation_checks(ctx)


def _start_here(ctx, data):
    ws = ctx.sheet(OWNER, "START_HERE")
    bold = ctx.wb.add_format({"bold": True, "font_size": 14})
    h2 = ctx.wb.add_format({"bold": True, "font_size": 11})
    wrap = ctx.wb.add_format({"text_wrap": True, "valign": "top", "font_size": 10})
    ws.set_column(0, 0, 58)
    ws.set_column(1, 1, 100)
    ws.write(1, 0, "Indian Equity Intrinsic Valuation and Mutual Fund Fair NAV Engine", bold)
    ws.write(2, 0, "Formula-driven research model. Estimates are not official NAVs, forecasts or advice.", wrap)
    r = 4
    ws.write(r, 0, "Five distinct outputs (never interchangeable)", h2); r += 1
    for label, definition in OUTPUT_DEFINITIONS:
        ws.write(r, 0, label.value, wrap); ws.write(r, 1, definition, wrap); r += 1
    r += 1
    ws.write(r, 0, "Cell colour legend", h2); r += 1
    for role, meaning in [("input", "User input / assumption / scenario control"),
                          ("calc", "Formula within this sheet"), ("link", "Formula linking another sheet"),
                          ("imported", "Imported source observation (do not edit)"),
                          ("override", "Scenario override / hypothetical input")]:
        ws.write(r, 0, f"{role} ({FONT_BY_ROLE[role]})", ctx.fmt(role)); ws.write(r, 1, meaning, wrap); r += 1
    r += 1
    ws.write(r, 0, "Reset scenario controls", h2); r += 1
    ws.write(r, 0, "Copy each Reset_* column over its input column on SCENARIO_ANALYSIS, or regenerate the "
                   "workbook (python build/generate_workbook.py). VALIDATION_CHECKS shows Controls_At_Default.", wrap)
    r += 2
    ws.write(r, 0, "Navigation", h2); r += 1
    for name in ctx.sheets:
        if name == "START_HERE":
            continue
        ws.write_url(r, 0, f"internal:'{name}'!A1", string=name)
        ws.write(r, 1, f"owner: {ctx.sheet_owner[name]}", wrap)
        r += 1


def _global_assumptions(ctx, data):
    sheet = "GLOBAL_ASSUMPTIONS"
    ws = ctx.sheet(OWNER, sheet)
    ws.write(1, 0, "Global inputs. Blue cells are editable; each Value cell is a named input (in_*).")
    t = S.GLOBAL_INPUTS
    rows = data.rows("global_inputs")
    cols = [TableColumn(c.name, role="input" if c.name == "Value" else "imported") for c in t.stored_columns]
    top = 3
    ctx.add_table(OWNER, sheet, top, 0, t.excel_name, cols, [[None] * len(cols) for _ in rows])
    value_col = [c.name for c in t.stored_columns].index("Value")
    for i, r in enumerate(rows):
        row = top + 1 + i
        for j, c in enumerate(t.stored_columns):
            raw = r.get(c.name, "")
            if c.name == "Value":
                vt = r["Value_Type"]
                v = typed_value(S.Column("Value", {"decimal": "float", "int": "int"}.get(vt, vt)), raw) if raw else None
                number = {"date": "date", "decimal": "pct" if r["Unit"] == "decimal" else "general"}.get(vt, "general")
                if v is None:
                    ws.write_blank(row, j, None, ctx.fmt("input", number))
                else:
                    ws.write(row, j, v, ctx.fmt("input", number))
                if r.get("Allowed_Values"):
                    ws.data_validation(row, j, row, j, {"validate": "list", "source": r["Allowed_Values"].split(";")})
            else:
                ws.write(row, j, raw, ctx.fmt("imported"))
        cell = f"{chr(ord('A') + value_col)}{row + 1}"
        ctx.define_name(OWNER, r["Name"], sheet, cell)
    ws.set_column(0, 0, 28); ws.set_column(1, 1, 14); ws.set_column(4, 4, 60); ws.set_column(8, 8, 70)


def _validation_checks(ctx):
    sheet = "VALIDATION_CHECKS"
    ctx.sheet(OWNER, sheet)
    path = ROOT / S.VALIDATION_RESULTS.csv_path
    if path.exists():
        with path.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        rows = [{"Check_ID": "NONE", "Category": "All", "Description": "No validation run has been recorded for this build",
                 "Executed": "FALSE", "Executed_At": "", "Result": CheckResult.NOT_RUN.value,
                 "Evidence": "Run 05-qa (spec/worker_briefs/05-qa.md)", "Tool": "-"}]
    ctx.write_value(OWNER, sheet, "A1", "Executed checks only. NOT RUN is never shown as PASS.", role="calc")
    _table_from_schema(ctx, sheet, 2, S.VALIDATION_RESULTS, rows)


def build_dashboard(ctx: WorkbookContext, data) -> None:
    """Runs after the module builders, so it can link to tbl_NAVSummary when 03-nav has built it."""
    sheet = "EXECUTIVE_DASHBOARD"
    ws = ctx.sheet(OWNER, sheet)
    h = ctx.wb.add_format({"bold": True, "font_size": 12})
    ws.write(1, 0, "Executive dashboard", h)
    if "tbl_NAVSummary" not in ctx.tables:
        ctx.write_value(OWNER, sheet, "A4", "NAV engine not built yet (owner 03-nav). No fund outputs to show.", role="calc")
        return
    fields = [("Official_NAV", OutputLabel.OFFICIAL_NAV.value, "inr"),
              ("Fair_NAV_Base", OutputLabel.FAIR_NAV.value + " - Base", "inr"),
              ("Fair_NAV_Bear", OutputLabel.FAIR_NAV.value + " - Bear", "inr"),
              ("Fair_NAV_Bull", OutputLabel.FAIR_NAV.value + " - Bull", "inr"),
              ("Scenario_Market_NAV", OutputLabel.SCENARIO_MARKET_NAV.value, "inr"),
              ("Diff_vs_Official_Pct", "Fair NAV (Base) vs Official NAV", "pct"),
              # Three separate data-quality measures (contract §7.5). Never combined into one score.
              ("Holdings_Value_Coverage_Pct", "1 Holdings coverage: imported value / reported net assets", "pct"),
              ("Holdings_Match_Pct", "1 Holdings coverage: positions matched and priced", "pct"),
              ("Holdings_Coverage_Status", "1 Holdings coverage status", "general"),
              ("Coverage_Caption", "2 Valuation coverage", "general"),
              ("Valuation_Coverage_Status", "2 Valuation coverage status", "general"),
              ("Portfolio_Date", "3 Freshness: portfolio disclosure date", "date"),
              ("NAV_Date", "3 Freshness: official NAV date", "date"),
              ("Price_Date", "3 Freshness: market price date", "date"),
              ("Valuation_Date", "3 Freshness: valuation date", "date"),
              ("Holdings_Age_Days", "3 Freshness: holdings age (days)", "count"),
              ("Max_Financials_Age_Days", "3 Freshness: oldest valued financials (days)", "count"),
              ("Stale_Valued_Weight_Pct", "3 Freshness: weight valued on stale financials", "pct"),
              ("Freshness_Status", "3 Freshness status", "general")]
    plans = [r["Plan_ID"] for r in data.rows("fund_plans")]
    ws.write(3, 0, "Plan_ID", h)
    for j, p in enumerate(plans):
        ctx.write_value(OWNER, sheet, f"{chr(ord('B') + j)}4", p, role="imported")
    for i, (field, label, number) in enumerate(fields):
        row = 5 + i
        ws.write(row - 1, 0, label)
        for j, _ in enumerate(plans):
            col = chr(ord("B") + j)
            ctx.write_formula(OWNER, sheet, f"{col}{row}",
                              f'=IFERROR(INDEX(tbl_NAVSummary[{field}],MATCH({col}$4,tbl_NAVSummary[Plan_ID],0)),"MISSING")',
                              role="link", number=number)
    ctx.reserve_chart_zone(OWNER, "DASH_NAV_COMPARE", sheet, "H3", "Official vs fair (bear/base/bull) vs scenario NAV per plan")
    ctx.reserve_chart_zone(OWNER, "DASH_COVERAGE", sheet, "H22", "Valuation coverage and source freshness")
    ctx.reserve_chart_zone(OWNER, "DASH_SECTOR", sheet, "H41", "Sector contribution to fair NAV difference")
