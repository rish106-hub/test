"""Sheet-building helpers shared by the 03-nav sheet builders (src/scenarios and src/fund_nav).

Everything here goes through WorkbookContext. Formula font colours are derived from what a formula
references (same-sheet = black, cross-sheet = green, spec <formatting_and_colour_coding>), so a column
can never be coloured wrongly by hand (W-07).
"""
from __future__ import annotations

from typing import Any, Sequence

from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell

from src.common import excel_contract as X
from src.common import schema as S
from src.common.rows import typed_rows
from src.common.workbook import TableColumn, WorkbookContext, qualify_this_row

OWNER = "03-nav"

# Funds and the sheet that holds each fund's holdings table. Both funds are built by the same function.
FUND_SHEETS = {"MF001": "PPFAS_FLEXICAP_HOLDINGS", "MF002": "HDFC_MIDCAP_HOLDINGS"}

# Sheet of every table 03-nav reads or builds; used to colour formulas (cross-sheet = green).
_PRIVATE_TABLE_SHEETS = {
    "tbl_Nav_ControlsStatus": "SCENARIO_ANALYSIS", "tbl_Nav_PriceDefaults": "SCENARIO_ANALYSIS",
    "tbl_Nav_PlanCalc": "MF_NAV_CALCULATOR",
}


def holdings_table(fund_id: str) -> str:
    return f"tbl_Holdings_{fund_id}"


def table_sheet(name: str) -> str | None:
    if name in _PRIVATE_TABLE_SHEETS:
        return _PRIVATE_TABLE_SHEETS[name]
    for fid, sheet in FUND_SHEETS.items():
        if name == holdings_table(fid):
            return sheet
    for t in S.ALL_TABLES:
        if t.excel_name == name:
            return t.sheet
    return None


def register_private_table(name: str, sheet: str) -> None:
    """Declare a private table's sheet before any formula that references it is generated."""
    _PRIVATE_TABLE_SHEETS[name] = sheet


def role_of(formula: str, sheet: str) -> str:
    """'link' when the formula reads another sheet (a table there, or an in_/out_ name), else 'calc'."""
    if X.names_referenced(formula):
        return "link"
    for t in X.tables_referenced(formula):
        if table_sheet(t) not in (None, sheet):
            return "link"
    return "calc"


def number_for(col: S.Column) -> str:
    if col.dtype == "date":
        return "date"
    if col.unit == "INR":
        return "inr"
    if col.unit == "INR_Cr":
        return "inr_cr"
    if col.unit == "decimal" or col.name.endswith("_Pct"):
        return "pct"
    if col.dtype == "int" or col.unit in ("count", "days"):
        return "count"
    return "general"


def schema_table_columns(table: S.Table, formulas: dict[str, str] | None = None, roles: dict[str, str] | None = None,
                         sheet: str = "") -> list[TableColumn]:
    """TableColumns for every schema column in schema order. Stored columns are imported (grey) unless `roles`
    says otherwise; columns in `formulas` become calculated columns coloured by what they reference."""
    formulas, roles = formulas or {}, roles or {}
    out = []
    for c in table.columns:
        f = formulas.get(c.name)
        if f is not None:
            out.append(TableColumn(c.name, formula=f, role=roles.get(c.name) or role_of(f, sheet), number=number_for(c)))
        else:
            if c.origin != "stored" and c.name not in roles:
                raise KeyError(f"{table.key}.{c.name} is a {c.origin} column and needs a formula")
            out.append(TableColumn(c.name, role=roles.get(c.name, "imported"), number=number_for(c)))
    return out


def stored_rows(table: S.Table, rows: Sequence[dict]) -> list[list[Any]]:
    """Typed values for the non-formula (stored) columns only, in schema order."""
    return typed_rows(table, rows)


def cell_of(top: int, left: int, row_i: int, col_j: int) -> str:
    """A1 address of data row `row_i`, column `col_j` of a table whose header row is `top` (0-based)."""
    return xl_rowcol_to_cell(top + 1 + row_i, left + col_j)


def write_row_formula(ctx: WorkbookContext, sheet: str, table: str, top: int, left: int, row_i: int,
                      col_j: int, formula: str, number: str = "general", role: str | None = None) -> None:
    """A formula in one cell of a table whose rows differ (e.g. each plan reads its own fund's holdings table)."""
    formula = qualify_this_row(formula, table)
    ctx.write_formula(OWNER, sheet, cell_of(top, left, row_i, col_j), formula,
                      role=role or role_of(formula, sheet), number=number)


def col_name(left: int, j: int) -> str:
    return xl_col_to_name(left + j)


def ws_note(ctx: WorkbookContext, sheet: str, cell: str, text: str, *, bold: bool = False) -> None:
    ws = ctx.sheets[sheet]
    ws.write(cell, text, ctx.wb.add_format({"bold": bold, "font_size": 11 if bold else 10,
                                            "font_name": "Calibri", "text_wrap": False}))


def lookup(table: str, col: str, key_expr: str, key_col: str) -> str:
    """INDEX/MATCH without the leading '='. A missing key is #N/A (WI-6)."""
    return f"INDEX({table}[{col}],MATCH({key_expr},{table}[{key_col}],0))"


def ids(text: str) -> str:
    """A plan or fund identifier inside a formula string."""
    return '"' + text.replace('"', '""') + '"'


def safe_name(plan_id: str) -> str:
    return plan_id.replace("-", "_")
