"""Builds all 03-nav sheets (spec/workbook_interface.md §3). Owner: 03-nav."""
from src.common.workbook import WorkbookContext
from src.fund_nav import holdings, nav_sheet, xl
from src.scenarios.sheets import build_scenario_sheet


def build_sheets(ctx: WorkbookContext, data) -> None:
    build_scenario_sheet(ctx, data)
    layouts = {fid: holdings.build_holdings_sheet(ctx, data, fid) for fid in xl.FUND_SHEETS}
    nav_sheet.build_nav_sheet(ctx, data, {fid: lay.table for fid, lay in layouts.items()})
