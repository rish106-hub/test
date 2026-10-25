"""WorkbookContext: the only way module code touches the workbook.

Each module exposes `build_sheets(ctx: WorkbookContext, data: ModelData) -> None`
(spec/workbook_interface.md). The context enforces four rules at build time:

1. A module may only create the worksheets assigned to it in spec/ownership.toml.
2. Every formula uses whitelisted functions only (src/common/excel_contract.py).
3. Every referenced table (tbl_*) and defined name (in_*/out_*) exists by close().
   This catches cross-module interface drift before Excel shows #NAME? or #REF!.
4. A test build that contains synthetic fixtures watermarks every sheet (D-013).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell

from src.common import excel_contract as X
from src.common import ownership, styles


_THIS_ROW = re.compile(r"\[@([A-Za-z0-9_]+)\]")


def qualify_this_row(formula: str, table: str) -> str:
    """[@Col] -> tbl_X[[#This Row],[Col]].

    XlsxWriter stores [@Col] as the unqualified "[[#This Row],Col]", which Excel
    accepts but LibreOffice 24.2 evaluates to #N/A (verified 2026-10-25). The
    qualified form works in both, so the QA harness can recalculate the formula.
    """
    return _THIS_ROW.sub(lambda m: f"{table}[[#This Row],[{m.group(1)}]]", formula)


class InterfaceError(RuntimeError):
    """A module broke the workbook interface contract."""


@dataclass
class TableColumn:
    header: str
    formula: str | None = None   # structured-reference formula for calculated columns
    role: str = "imported"       # styles role: input | calc | link | imported | override
    number: str = "general"


@dataclass
class ChartZone:
    zone_id: str
    sheet: str
    anchor: str          # top-left cell, e.g. "R3"
    owner: str           # sheet owner who reserved it
    purpose: str


@dataclass
class _FormulaRecord:
    owner: str
    sheet: str
    cell: str
    formula: str


class WorkbookContext:
    def __init__(self, path: str, *, test_build: bool = False):
        self.path = path
        self.test_build = test_build
        self.wb = xlsxwriter.Workbook(path, {"use_future_functions": True})
        self.sheets: dict[str, Any] = {}
        self.sheet_owner: dict[str, str] = {}
        self.tables: dict[str, dict] = {}       # tbl name -> {owner, sheet, columns}
        self.names: dict[str, dict] = {}        # in_/out_ name -> {owner, sheet, cell}
        self.chart_zones: dict[str, ChartZone] = {}
        self.built: set[str] = set()
        self._formulas: list[_FormulaRecord] = []
        self._formats: dict[tuple, Any] = {}

    # ------------------------------------------------------------------ formats
    def fmt(self, role: str, number: str = "general", **extra):
        key = (role, number, tuple(sorted(extra.items())))
        if key not in self._formats:
            self._formats[key] = self.wb.add_format(styles.format_props(role, number, **extra))
        return self._formats[key]

    # ------------------------------------------------------------------ sheets
    def create_sheets(self, order: Sequence[str]):
        """Called once by build/generate_workbook.py to fix the tab order (SHEET_ORDER)."""
        for name in order:
            self._new_sheet(name, ownership.sheet_owner(name))

    def sheet(self, owner: str, name: str):
        """Claim a pre-created sheet. Raises if `owner` does not own it."""
        if name not in self.sheets:
            raise InterfaceError(f"sheet {name!r} is not in SHEET_ORDER; use add_sheet for template sheets")
        self._require_owner(owner, name)
        self.built.add(name)
        return self.sheets[name]

    def add_sheet(self, owner: str, name: str):
        """Create an additional sheet (e.g. a template-generated VAL_* sheet) at the end."""
        if ownership.sheet_owner(name) != owner:
            raise InterfaceError(f"{owner} may not create sheet {name!r} (owner: {ownership.sheet_owner(name)})")
        ws = self._new_sheet(name, owner)
        self.built.add(name)
        return ws

    def _new_sheet(self, name: str, owner: str | None):
        if owner is None:
            raise InterfaceError(f"sheet {name!r} has no owner in spec/ownership.toml")
        if name in self.sheets:
            raise InterfaceError(f"sheet {name!r} created twice")
        ws = self.wb.add_worksheet(name)
        self.sheets[name] = ws
        self.sheet_owner[name] = owner
        if self.test_build:
            ws.write(0, 0, "TEST BUILD - SYNTHETIC DATA - NOT FOR INVESTMENT USE",
                     self.wb.add_format({"bold": True, "font_color": "#C00000"}))
        return ws

    def unbuilt_sheets(self) -> list[str]:
        return [s for s in self.sheets if s not in self.built]

    def _require_owner(self, owner: str, sheet: str):
        if self.sheet_owner.get(sheet) != owner:
            raise InterfaceError(f"{owner} may not write to sheet {sheet!r} (owner: {self.sheet_owner.get(sheet)})")

    # ------------------------------------------------------------------ cells
    def write_formula(self, owner: str, sheet: str, cell: str, formula: str, role: str = "calc",
                      number: str = "general"):
        self._require_owner(owner, sheet)
        self._check(formula, owner, sheet, cell)
        self.sheets[sheet].write_formula(cell, formula, self.fmt(role, number))

    def write_value(self, owner: str, sheet: str, cell: str, value, role: str = "imported",
                    number: str = "general"):
        self._require_owner(owner, sheet)
        if value is None:
            self.sheets[sheet].write_blank(cell, None, self.fmt(role, number))
        else:
            self.sheets[sheet].write(cell, value, self.fmt(role, number))

    def define_name(self, owner: str, name: str, sheet: str, cell: str):
        self._require_owner(owner, sheet)
        if not X.NAME_RE.match(name):
            raise InterfaceError(f"defined name {name!r} must match {X.NAME_RE.pattern}")
        if name in self.names:
            raise InterfaceError(f"defined name {name!r} already defined by {self.names[name]['owner']}")
        col_row = cell.replace("$", "")
        letters = "".join(ch for ch in col_row if ch.isalpha())
        digits = col_row[len(letters):]
        self.wb.define_name(name, f"='{sheet}'!${letters}${digits}")
        self.names[name] = {"owner": owner, "sheet": sheet, "cell": cell}

    # ------------------------------------------------------------------ tables
    def add_table(self, owner: str, sheet: str, top_row: int, left_col: int, name: str,
                  columns: Sequence[TableColumn], rows: Sequence[Sequence[Any]]):
        """rows contain values for non-formula columns only, in column order."""
        self._require_owner(owner, sheet)
        if not X.TABLE_RE.match(name):
            raise InterfaceError(f"table name {name!r} must match {X.TABLE_RE.pattern}")
        if name in self.tables:
            raise InterfaceError(f"table {name!r} defined twice")
        value_cols = [i for i, c in enumerate(columns) if c.formula is None]
        data = []
        for r in rows:
            if len(r) != len(value_cols):
                raise InterfaceError(f"{name}: row has {len(r)} values, expected {len(value_cols)}")
            full = [None] * len(columns)
            for i, v in zip(value_cols, r):
                full[i] = v
            data.append(full)
        n_rows = max(len(data), 1)
        last_row = top_row + n_rows
        last_col = left_col + len(columns) - 1
        spec_cols = []
        for c in columns:
            col = {"header": c.header, "format": self.fmt(c.role, c.number)}
            if c.formula is not None:
                formula = qualify_this_row(c.formula, name)
                self._check(formula, owner, sheet, f"{name}[{c.header}]")
                col["formula"] = formula
            spec_cols.append(col)
        opts = {"name": name, "columns": spec_cols, "style": "Table Style Light 1"}
        if data:
            opts["data"] = data
        self.sheets[sheet].add_table(top_row, left_col, last_row, last_col, opts)
        self.tables[name] = {"owner": owner, "sheet": sheet, "columns": [c.header for c in columns],
                             "range": (xl_rowcol_to_cell(top_row, left_col), xl_rowcol_to_cell(last_row, last_col))}

    def add_stub_table(self, sheet: str, top_row: int, name: str, headers: Sequence[str],
                       rows: Sequence[Sequence[Any]]):
        """Interface stub for an isolated worker build (build/interface_stubs.py only).

        Creates a value-only copy of another module's interface table from synthetic
        fixtures, so a worker can build and recalculate its own sheets alone. Never
        used in an integration build.
        """
        if not self.test_build:
            raise InterfaceError("interface stubs are allowed only in a test build")
        if name in self.tables:
            raise InterfaceError(f"table {name!r} defined twice")
        ws = self.sheets[sheet]
        ws.write(top_row - 1, 0, f"STUB of {name} (owner {self.sheet_owner[sheet]} not built) - synthetic fixture values",
                 self.wb.add_format({"italic": True, "font_color": "#C00000"}))
        data = [list(r) for r in rows] or [[None] * len(headers)]
        cols = [{"header": h, "format": self.fmt("imported")} for h in headers]
        ws.add_table(top_row, 0, top_row + len(data), len(headers) - 1,
                     {"name": name, "columns": cols, "data": data, "style": "Table Style Light 15"})
        self.tables[name] = {"owner": "STUB", "sheet": sheet, "columns": list(headers)}
        self.built.add(sheet)

    # ------------------------------------------------------------------ charts
    def reserve_chart_zone(self, owner: str, zone_id: str, sheet: str, anchor: str, purpose: str):
        self._require_owner(owner, sheet)
        if zone_id in self.chart_zones:
            raise InterfaceError(f"chart zone {zone_id!r} reserved twice")
        self.chart_zones[zone_id] = ChartZone(zone_id, sheet, anchor, owner, purpose)

    def insert_chart(self, owner: str, zone_id: str, chart):
        if owner != "04-charts":
            raise InterfaceError("only 04-charts inserts charts (D-017)")
        zone = self.chart_zones.get(zone_id)
        if zone is None:
            raise InterfaceError(f"chart zone {zone_id!r} was not reserved by a sheet owner")
        self.sheets[zone.sheet].insert_chart(zone.anchor, chart)

    def add_chart(self, owner: str, options: dict):
        if owner != "04-charts":
            raise InterfaceError("only 04-charts creates charts (D-017)")
        return self.wb.add_chart(options)

    # ------------------------------------------------------------------ checks
    def _check(self, formula: str, owner: str, sheet: str, where: str):
        problems = X.check_formula(formula)
        if problems:
            raise InterfaceError(f"{owner} {sheet}!{where}: {'; '.join(problems)}  formula={formula}")
        self._formulas.append(_FormulaRecord(owner, sheet, where, formula))

    def reference_problems(self) -> list[str]:
        problems = []
        for rec in self._formulas:
            for t in X.tables_referenced(rec.formula):
                if t not in self.tables:
                    problems.append(f"{rec.owner} {rec.sheet}!{rec.cell}: unknown table {t}")
            for n in X.names_referenced(rec.formula):
                if n not in self.names:
                    problems.append(f"{rec.owner} {rec.sheet}!{rec.cell}: unknown name {n}")
        return problems

    def references_by_owner(self) -> dict[str, dict[str, list[str]]]:
        """Tables and names each owner's formulas reference (checked by tools/check_module_contract.py)."""
        refs: dict[str, dict[str, set[str]]] = {}
        for rec in self._formulas:
            r = refs.setdefault(rec.owner, {"tables": set(), "names": set()})
            r["tables"] |= X.tables_referenced(rec.formula)
            r["names"] |= X.names_referenced(rec.formula)
        return {o: {k: sorted(v) for k, v in r.items()} for o, r in sorted(refs.items())}

    def manifest(self) -> dict:
        """Machine-readable interface of the built workbook (written to build/out/manifest.json)."""
        return {
            "sheets": self.sheet_owner,
            "tables": {k: {kk: vv for kk, vv in v.items()} for k, v in self.tables.items()},
            "names": self.names,
            "chart_zones": {k: vars(v) for k, v in self.chart_zones.items()},
            "formula_count": len(self._formulas),
            "references": self.references_by_owner(),
            "test_build": self.test_build,
            "unbuilt_sheets": self.unbuilt_sheets(),
        }

    def close(self):
        problems = self.reference_problems()
        if problems:
            raise InterfaceError("unresolved workbook references:\n  " + "\n  ".join(problems))
        self.wb.close()
