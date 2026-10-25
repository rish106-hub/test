"""Small layout helper for 02-valuation sheets.

Every value and formula goes through WorkbookContext (ownership, whitelist and reference
checks). Grid adds a registry of logical cell keys, so formulas are composed from named cells
(`g.ref("re")`) rather than hand-typed addresses, and the builder can publish a cell map that
the sheet-vs-reference test and 05-qa read. Labels and notes are plain text written directly
to the worksheet the module owns; they carry no numbers.
"""
from __future__ import annotations

from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell

from src.common.styles import STATUS_FILL
from src.common.workbook import WorkbookContext

OWNER = "02-valuation"

_TEXT_STYLES = {
    "title": {"bold": True, "font_size": 13},
    "h1": {"bold": True, "font_size": 11, "bg_color": "#DDEBF7", "bottom": 1},
    "h2": {"bold": True, "font_size": 10},
    "label": {"font_size": 10},
    "label_b": {"font_size": 10, "bold": True},
    "note": {"font_size": 9, "italic": True, "font_color": "#595959", "text_wrap": False},
    "tag": {"font_size": 9, "font_color": "#595959"},
    "colhead": {"font_size": 9, "bold": True, "bg_color": "#F2F2F2", "align": "center"},
}
_FORMATS: dict[tuple[int, str], object] = {}


def text_format(ctx: WorkbookContext, style: str):
    key = (id(ctx.wb), style)
    if key not in _FORMATS:
        _FORMATS[key] = ctx.wb.add_format(dict(font_name="Calibri", **_TEXT_STYLES[style]))
    return _FORMATS[key]


def add_status_highlighting(ctx: WorkbookContext, ws, first_row: int, first_col: int, last_row: int, last_col: int):
    """Fill status cells by their text. The status word is always written too (colour safety, §11)."""
    for word, colour in STATUS_FILL.items():
        key = (id(ctx.wb), "status_" + word)
        if key not in _FORMATS:
            _FORMATS[key] = ctx.wb.add_format({"bg_color": colour})
        ws.conditional_format(first_row, first_col, last_row, last_col,
                              {"type": "text", "criteria": "begins with", "value": word, "format": _FORMATS[key]})


class Grid:
    def __init__(self, ctx: WorkbookContext, sheet: str, prefix: str = ""):
        self.ctx, self.sheet, self.prefix = ctx, sheet, prefix
        self.ws = ctx.sheets[sheet]
        self.cells: dict[str, str] = {}

    # ---------------------------------------------------------------- addresses
    @staticmethod
    def addr(row: int, col: int) -> str:
        return xl_rowcol_to_cell(row, col)

    @staticmethod
    def col(col: int) -> str:
        return xl_col_to_name(col)

    def rng(self, row1: int, col1: int, row2: int, col2: int) -> str:
        return f"{self.addr(row1, col1)}:{self.addr(row2, col2)}"

    def _remember(self, key: str | None, row: int, col: int) -> str:
        a = self.addr(row, col)
        if key is not None:
            if key in self.cells:
                raise KeyError(f"{self.sheet}: cell key {key!r} used twice")
            self.cells[key] = a
        return a

    def ref(self, key: str) -> str:
        return self.cells[key]

    def ext(self, key: str) -> str:
        """Absolute reference from another sheet the module owns."""
        a = self.cells[key]
        letters = "".join(ch for ch in a if ch.isalpha())
        return f"'{self.sheet}'!${letters}${a[len(letters):]}"

    # ---------------------------------------------------------------- writers
    def label(self, row: int, col: int, text: str, style: str = "label"):
        self.ws.write_string(row, col, text, text_format(self.ctx, style))

    def formula(self, row: int, col: int, formula: str, *, role: str = "calc", number: str = "general",
                key: str | None = None) -> str:
        f = formula if formula.startswith("=") else "=" + formula
        a = self._remember(key, row, col)
        self.ctx.write_formula(OWNER, self.sheet, a, f, role=role, number=number)
        return a

    def value(self, row: int, col: int, value, *, role: str = "imported", number: str = "general",
              key: str | None = None) -> str:
        a = self._remember(key, row, col)
        self.ctx.write_value(OWNER, self.sheet, a, value, role=role, number=number)
        return a
