"""PPFAS_FLEXICAP_HOLDINGS and HDFC_MIDCAP_HOLDINGS: one holdings table per fund, built by one function.

The CSV columns (fund_holdings.csv, filtered by Fund_ID) are imported and grey. The link and calculation
columns of schema.FUND_HOLDINGS use src/common/link_patterns.py (H_*) and the variants in patterns.py.
The two funds never share rows (D-010: Holding_Line_ID carries the Fund_ID).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.common import link_patterns as L
from src.common import schema as S
from src.common.workbook import WorkbookContext
from src.fund_nav import xl

OWNER = xl.OWNER
TOP = 5            # 0-based header row of the holdings table


@dataclass(frozen=True)
class HoldingsLayout:
    fund_id: str
    sheet: str
    table: str
    top: int
    n_rows: int
    line_ids: tuple[str, ...]


def holdings_formulas() -> dict[str, str]:
    return {
        "Current_Market_Price": L.H_CURRENT_PRICE,
        "Selected_Scenario_Price": L.H_SELECTED_PRICE,
        "Base_Fair_Value": L.H_BASE_FV,
        "Scenario_Fair_Value": L.H_SCENARIO_FV,
        "Holdings_Match_Status": L.H_MATCH_STATUS,
        "Financials_As_Of": L.H_FINANCIALS_AS_OF,
        "Valuation_Coverage_Status": L.H_COVERAGE_STATUS,
        "Adj_Base": L.H_ADJ["Base"], "Adj_Bear": L.H_ADJ["Bear"], "Adj_Bull": L.H_ADJ["Bull"],
        "Adj_Selected": L.H_ADJ["Selected"],
        "MV_Mkt_INR_Cr": L.H_MV_MKT, "MV_Fair_Base_INR_Cr": L.H_MV_FAIR_BASE, "MV_Scenario_INR_Cr": L.H_MV_SCENARIO,
    }


def fund_rows(data, fund_id: str) -> list[dict]:
    return [r for r in data.rows("fund_holdings") if r["Fund_ID"] == fund_id]


def build_holdings_sheet(ctx: WorkbookContext, data, fund_id: str) -> HoldingsLayout:
    sheet, table = xl.FUND_SHEETS[fund_id], xl.holdings_table(fund_id)
    ws = ctx.sheet(OWNER, sheet)
    rows = fund_rows(data, fund_id)
    plans = [r["Plan_ID"] for r in data.rows("fund_plans") if r["Fund_ID"] == fund_id]
    xl.ws_note(ctx, sheet, "A2", f"Disclosed portfolio snapshot of scheme {fund_id} (plans: {', '.join(plans) or 'none imported'}). "
               "Holdings belong to the scheme, so every plan shares these lines.", bold=True)
    xl.ws_note(ctx, sheet, "A3", "Grey = imported from the AMC disclosure (never edited). Green = linked from SCENARIO_ANALYSIS / "
               "VALUATION_OUTPUTS. Black = calculated. An unvalued line is shown as UNVALUED with adjustment 0 and is "
               "never treated as zero value (R009).")
    xl.ws_note(ctx, sheet, "A4", "Market prices and fair values are linked, not copied: change controls only on SCENARIO_ANALYSIS.")
    cols = xl.schema_table_columns(S.FUND_HOLDINGS, holdings_formulas(), sheet=sheet)
    ctx.add_table(OWNER, sheet, TOP, 0, table, cols, xl.stored_rows(S.FUND_HOLDINGS, rows))
    ws.set_column(0, 0, 24)
    ws.set_column(1, len(cols) - 1, 16)
    ws.freeze_panes(TOP + 1, 1)
    return HoldingsLayout(fund_id, sheet, table, TOP, max(len(rows), 1), tuple(r["Holding_Line_ID"] for r in rows))
