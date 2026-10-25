"""Builds VAL_* sheets, VALUATION_OUTPUTS and HISTORICAL_METRICS. Owner: 02-valuation.

Must expose, per valued security, out_<Security_ID>_FV_Base / _FV_Bear / _FV_Bull /
_TV_Share and populate tbl_ValuationOutputs (spec/workbook_interface.md §2).

Wave 1 (D-028): only VAL_HDFC_BANK carries the bank template. Every other registry security
gets an UNVALUED row with blank fair values and the reason (R009), never 0. The other named
VAL_* sheets show a Wave 2 notice.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

from src.common import schema as S
from src.common.enums import BusinessModel, MetricKind
from src.common.rows import typed_value
from src.common.workbook import TableColumn, WorkbookContext
from src.valuations import history as H
from src.valuations import parameters as P
from src.valuations.bank_model import run_bank_model
from src.valuations.bank_sheet import BuiltSheet, build_bank_sheet
from src.valuations.fixtures import augment_test_fixtures
from src.valuations.inputs import (PRIMARY_METHOD, SECONDARY_METHODS, gather_bank_spec, global_inputs, is_bank,
                                   model_inputs)
from src.valuations.layout import OWNER, Grid, add_status_highlighting, text_format
from src.valuations.reference import METHODOLOGY_VERSION, csv_value, unvalued_row, valued_row

WAVE_1_SHEETS = ("VAL_HDFC_BANK",)
NAMED_VAL_SHEETS = ("VAL_HDFC_BANK", "VAL_FEDERAL_BANK", "VAL_AU_SFB", "VAL_INDIAN_BANK", "VAL_ICICI_BANK",
                    "VAL_KOTAK_BANK", "VAL_MAX_FINANCIAL")
# Peer-relative links tbl_PeerSummary, which 04-charts builds after gate G1 (D-028). Until then the
# table exists only as a stub in an isolated test build; linking it in an integrated or production
# build would leave an unresolved reference. Set to True when 04-charts delivers tbl_PeerSummary.
PEERS_DELIVERED = False
REFERENCE_CSV = "reference_valuation_outputs.csv"
CELL_MAP_JSON = "valuation_cell_map.json"


def _isolated_test_build(ctx: WorkbookContext) -> bool:
    """`--test-build --only 02-valuation`: 01-data has not built its tables, so they are stubbed after us."""
    return ctx.test_build and "tbl_Registry" not in ctx.tables


def build_sheets(ctx: WorkbookContext, data) -> None:
    isolated = _isolated_test_build(ctx)
    if isolated:
        augment_test_fixtures(data)          # pending CR-02-valuation-001
    link_peers = PEERS_DELIVERED or isolated
    g = global_inputs(data.rows("global_inputs"))
    registry = data.rows("security_registry")
    built: dict[str, BuiltSheet] = {}
    reference: dict[str, dict] = {}
    reasons: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for row in registry:
        sid, sheet = row["Security_ID"], (row.get("Dedicated_Sheet") or "").strip()
        if sheet in WAVE_1_SHEETS and is_bank(row) and sheet not in claimed:
            spec = gather_bank_spec(data, row)
            if not link_peers:
                spec.peer_pb_median, spec.peer_n_valid = None, 0
            _claim(ctx, sheet)
            claimed[sheet] = sid
            b = build_bank_sheet(ctx, spec, link_peers=link_peers)
            built[sid] = b
            reference[sid] = valued_row(spec, run_bank_model(model_inputs(spec)))
        else:
            reasons[sid] = _unvalued_reason(row, claimed)
            reference[sid] = unvalued_row(row, g, reasons[sid])
    for sheet in NAMED_VAL_SHEETS:
        if sheet not in claimed:
            _placeholder(ctx, sheet, [r for r in registry if (r.get("Dedicated_Sheet") or "").strip() == sheet])
    _assumptions_sheet(ctx, data)
    _valuation_outputs(ctx, registry, built, reasons)
    _historical_metrics(ctx, built)
    _write_side_files(ctx, registry, reference, built)


def _claim(ctx: WorkbookContext, sheet: str):
    return ctx.sheet(OWNER, sheet) if sheet in ctx.sheets else ctx.add_sheet(OWNER, sheet)


def _unvalued_reason(row, claimed: dict[str, str]) -> str:
    sheet = (row.get("Dedicated_Sheet") or "").strip()
    bm = row.get("Business_Model", "")
    if sheet and sheet in claimed:
        return f"{sheet} already values {claimed[sheet]}; one security per dedicated sheet"
    if bm == BusinessModel.INSURANCE_HOLDCO.value:
        return "insurance SOTP (contract §4) is Wave 2, after gate G1 (D-028); carried at market, adjustment 0 (D-015)"
    if is_bank(row) and sheet:
        return f"{sheet} is Wave 2, after gate G1 (D-028); carried at market, adjustment 0 (D-015)"
    if is_bank(row):
        return ("no company model yet; template sheets for further banks come after gate G1 (D-028); carried at "
                "market, adjustment 0 (D-015)")
    return (f"no valuation model for business model '{bm}' yet (contract §5); carried at market, adjustment 0 "
            "(D-015)")


def _placeholder(ctx: WorkbookContext, sheet: str, rows):
    ws = _claim(ctx, sheet)
    ws.write(2, 0, f"{sheet}: not modelled in Wave 1 (D-028). Built after gate G1.", text_format(ctx, "title"))
    if rows:
        ids = ", ".join(f"{r['Security_ID']} {r.get('Company_Name', '')}" for r in rows)
        ws.write(3, 0, f"Registry securities on this sheet: {ids}. Each is UNVALUED in tbl_ValuationOutputs: blank "
                       "fair values, never 0 (R009).", text_format(ctx, "note"))
    else:
        ws.write(3, 0, "No registry security names this sheet as its Dedicated_Sheet yet (01-data registry).",
                 text_format(ctx, "note"))


# ---------------------------------------------------------------------- VALUATION_ASSUMPTIONS
def _assumptions_sheet(ctx: WorkbookContext, data):
    sheet = "VALUATION_ASSUMPTIONS"
    ws = ctx.sheet(OWNER, sheet)
    ws.write(1, 0, "Valuation assumptions (tbl_Assumptions). Edit Value (blue) here: the VAL_* sheets link to it. "
                   "Every row carries a source type and a rationale; a missing row stays blank and shows as MISSING.",
             text_format(ctx, "note"))
    t = S.ASSUMPTIONS
    cols = [TableColumn(c.name, role="input" if c.name == "Value" else "imported") for c in t.stored_columns]
    rows = data.rows("assumptions")
    ctx.add_table(OWNER, sheet, 3, 0, t.excel_name, cols,
                  [[typed_value(c, r.get(c.name)) for c in t.stored_columns] for r in rows])
    widths = {"Assumption_ID": 30, "Scope": 10, "Case": 7, "Parameter": 18, "Period": 9, "Value": 12, "Unit": 9,
              "Assumption_Source_Type": 26, "Source_ID": 20, "Rationale": 90}
    for j, c in enumerate(t.stored_columns):
        ws.set_column(j, j, widths.get(c.name, 14))
    top = 3 + max(len(rows), 1) + 3
    ws.write(top, 0, "Parameter catalogue: what each driver means and the evidence its rationale must cite",
             text_format(ctx, "h2"))
    heads = ("Parameter", "Label", "Unit", "Per case", "Per year", "Required", "Evidence expected")
    for j, h in enumerate(heads):
        ws.write(top + 1, j, h, text_format(ctx, "colhead"))
    for i, p in enumerate(P.ALL_PARAMETERS):
        vals = (p.code, p.label, p.unit, "yes" if p.per_case else "no", "yes" if p.per_year else "no",
                "yes" if p.required else "no", p.evidence)
        for j, v in enumerate(vals):
            ws.write(top + 2 + i, j, v, text_format(ctx, "label"))
    ws.write(top + 3 + len(P.ALL_PARAMETERS), 0,
             "Resolution, most specific first: (Security_ID, case, FY) -> (Security_ID, case, ALL) -> (Security_ID, "
             "All, FY) -> (Security_ID, All, ALL) -> the same with Scope GLOBAL. Add rows in "
             "data/canonical/assumptions.csv and regenerate.", text_format(ctx, "note"))


# ---------------------------------------------------------------------- VALUATION_OUTPUTS
CALC_COLUMNS = {
    "Valuation_Date": ('=IF(in_Valuation_Date="","",in_Valuation_Date)', "link", "date"),
    "Price_Date": ('=IF(in_Price_Date="","",in_Price_Date)', "link", "date"),
    "Valuation_Coverage_Status": ('=IF(AND(ISNUMBER([@FV_Base_INR]),ISNUMBER([@FV_Bear_INR]),ISNUMBER([@FV_Bull_INR])),'
                                  '"MODEL_VALUED","UNVALUED")', "calc", "general"),
}
NUMBER_OF = {"date": "date", "INR": "inr", "decimal": "pct", "days": "count"}
# Columns linked from the VAL_* sheet: column -> cell key on that sheet
LINKED = {
    "Anchor_Date": "A", "Latest_Results_Period_End": "R", "BV_Reported_At_Anchor_INR": "bv0",
    "BV_Estimated_At_Valuation_INR": "bv_v", "Interim_EPS_Deviation_Pct": "dev", "Forecast_Update_Flag": "fflag",
    "Financials_Age_Days": "fin_age", "Anchor_Age_Days": "anchor_age", "Freshness_Status": "fresh",
    "Terminal_Flag": "out.tflag", "Peer_Flag": "peer_flag", "Data_Confidence_Note": "note",
}


def _number(col: S.Column) -> str:
    return "date" if col.dtype == "date" else NUMBER_OF.get(col.unit, "general")


def _valuation_outputs(ctx: WorkbookContext, registry, built: dict[str, BuiltSheet], reasons: dict[str, str]):
    sheet = "VALUATION_OUTPUTS"
    ws = ctx.sheet(OWNER, sheet)
    ws.write(1, 0, "tbl_ValuationOutputs: one row per registry security. The only seam between valuation and NAV. "
                   "FV_* are modelled fair values per share at Valuation_Date (estimates). UNVALUED rows keep blank "
                   "fair values, never 0 (R009).", text_format(ctx, "note"))
    t = S.VALUATION_OUTPUTS
    cols = []
    for c in t.columns:
        if c.name in CALC_COLUMNS:
            f, role, number = CALC_COLUMNS[c.name]
            cols.append(TableColumn(c.name, formula=f, role=role, number=number))
        else:
            cols.append(TableColumn(c.name, role="imported", number=_number(c)))
    value_cols = [c for c in t.columns if c.name not in CALC_COLUMNS]
    rows = []
    for r in registry:
        sid = r["Security_ID"]
        b = built.get(sid)
        vals = {"Security_ID": sid}
        if b is None:
            vals.update(Primary_Method="None", Secondary_Methods="", Model_Sheet="NONE",
                        Methodology_Version=METHODOLOGY_VERSION, Data_Confidence_Note=f"UNVALUED: {reasons[sid]}")
        else:
            vals.update(Primary_Method=PRIMARY_METHOD, Secondary_Methods=";".join(SECONDARY_METHODS),
                        Model_Sheet=b.spec.sheet, Methodology_Version=METHODOLOGY_VERSION)
        rows.append([vals.get(c.name) for c in value_cols])
    top = 3
    ctx.add_table(OWNER, sheet, top, 0, t.excel_name, cols, rows)
    names = [c.name for c in t.columns]
    for i, r in enumerate(registry):
        b = built.get(r["Security_ID"])
        if b is None:
            continue
        row = top + 1 + i
        for col_name, key in LINKED.items():
            j = names.index(col_name)
            ref = b.ext(key)
            ctx.write_formula(OWNER, sheet, Grid.addr(row, j), f'=IF({ref}="","",{ref})', role="link",
                              number=_number(t.column(col_name)))
        for case in ("Base", "Bear", "Bull"):
            name = f"out_{r['Security_ID']}_FV_{case}"
            ctx.write_formula(OWNER, sheet, Grid.addr(row, names.index(f"FV_{case}_INR")),
                              f'=IF({name}="","",{name})', role="link", number="inr")
        name = f"out_{r['Security_ID']}_TV_Share"
        ctx.write_formula(OWNER, sheet, Grid.addr(row, names.index("Terminal_Value_Share_Base")),
                          f'=IF({name}="","",{name})', role="link", number="pct")
    widths = {"Security_ID": 11, "Data_Confidence_Note": 90, "Methodology_Version": 40, "Secondary_Methods": 40}
    for j, n in enumerate(names):
        ws.set_column(j, j, widths.get(n, 15))
    add_status_highlighting(ctx, ws, top + 1, 0, top + max(len(registry), 1), len(names) - 1)


# ---------------------------------------------------------------------- HISTORICAL_METRICS
FORECAST_UNITS = {"BVPS": "INR", "EPS_DILUTED": "INR", "DPS": "INR", "ROE": "decimal", "BANK_NIM": "decimal",
                  "BANK_CREDIT_COST": "decimal", "DILUTED_SHARES": "count"}


def _historical_metrics(ctx: WorkbookContext, built: dict[str, BuiltSheet]):
    sheet = "HISTORICAL_METRICS"
    ws = ctx.sheet(OWNER, sheet)
    ws.write(1, 0, "tbl_HistoricalMetrics: reported and calculated history (Is_Forecast FALSE) and Base-case "
                   "forecasts (Modelled, Is_Forecast TRUE, never consensus). Blank Value = no observation.",
             text_format(ctx, "note"))
    t = S.HISTORICAL_METRICS
    value_cols = list(t.columns)   # Value is written per row below (a link to the VAL sheet cell)
    cols = [TableColumn(c.name, role="link" if c.name == "Value" else "imported",
                        number="date" if c.dtype == "date" else "general") for c in t.columns]
    rows, refs = [], []
    calcs = {**{c.key: c for c in H.FY_CALCS if c.export}}
    for sid, b in built.items():
        s = b.spec
        for (block, metric, label), cell in b.history_cells.items():
            calc = calcs.get(metric)
            if calc is None and metric not in H.UNITS:
                continue          # display-only consistency rows stay on the VAL sheet
            periods = dict(s.history_fy if block == "FY" else s.history_q)
            if calc is not None:
                kind, unit, src = MetricKind.CALCULATED.value, calc.unit, f"{s.sheet}: {calc.label}"
            else:
                ob = s.history.get((metric, label))
                kind, unit = MetricKind.REPORTED.value, H.UNITS[metric][0]
                src = (f"tbl_RawFinancials {ob.observation_id} (Source_ID {ob.source_id})" if ob
                       else "MISSING: no observation")
            vals = dict(Entity_ID=s.entity_id, Metric_ID=metric, Fiscal_Label=label, Period_End=periods[label],
                        Value=None, Unit=unit, Kind=kind, Is_Forecast=False, Source_or_Formula=src)
            rows.append([_typed(vals[c.name]) for c in value_cols])
            refs.append(cell)
        for (metric, tt), cell in sorted(b.forecast_cells.items(), key=lambda x: (x[0][0], x[0][1])):
            if not s.fy_ends:
                continue
            vals = dict(Entity_ID=s.entity_id, Metric_ID=metric, Fiscal_Label=s.fy_labels[tt - 1],
                        Period_End=s.fy_ends[tt - 1], Value=None, Unit=FORECAST_UNITS.get(metric, "INR_Cr"),
                        Kind=MetricKind.MODELLED.value, Is_Forecast=True,
                        Source_or_Formula=f"{s.sheet} Base-case projection (contract §3.6); modelled, not consensus")
            rows.append([_typed(vals[c.name]) for c in value_cols])
            refs.append(cell)
    top = 3
    ctx.add_table(OWNER, sheet, top, 0, t.excel_name, cols, rows)
    j = [c.name for c in t.columns].index("Value")
    for i, ref in enumerate(refs):
        ctx.write_formula(OWNER, sheet, Grid.addr(top + 1 + i, j), f'=IF({ref}="","",{ref})', role="link")
    for jj, w in enumerate((10, 22, 11, 11, 16, 9, 12, 10, 70)):
        ws.set_column(jj, jj, w)


def _typed(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v


# ---------------------------------------------------------------------- side files for QA
def _write_side_files(ctx: WorkbookContext, registry, reference: dict[str, dict], built: dict[str, BuiltSheet]):
    out_dir = Path(ctx.path).parent
    names = [c.name for c in S.VALUATION_OUTPUTS.columns]
    with (out_dir / REFERENCE_CSV).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(names)
        for r in registry:
            w.writerow([csv_value(reference[r["Security_ID"]].get(n)) for n in names])
    cell_map = {sid: {"sheet": b.spec.sheet, "cells": b.grid.cells} for sid, b in built.items()}
    (out_dir / CELL_MAP_JSON).write_text(json.dumps(cell_map, indent=1))
