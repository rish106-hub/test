"""Builds all 03-nav sheets (spec/workbook_interface.md §3). Owner: 03-nav."""
from src.common.workbook import WorkbookContext
from src.fund_nav import audit, holdings, nav_sheet, performance_sheet, rebalancing, scenario_builder, sector_sheets, xl
from src.scenarios.sheets import build_scenario_sheet


def build_sheets(ctx: WorkbookContext, data) -> None:
    build_scenario_sheet(ctx, data)
    layouts = {fid: holdings.build_holdings_sheet(ctx, data, fid) for fid in xl.FUND_SHEETS}
    nav = nav_sheet.build_nav_sheet(ctx, data, {fid: lay.table for fid, lay in layouts.items()})
    audit.build_audit_sheet(ctx, data, layouts, nav.plan_ids, nav.plan_fund)
    sector_sheets.build_sector_sheet(ctx, data, layouts, nav.plan_fund)
    sector_sheets.build_sensitivity_sheet(ctx, data, layouts, nav.plan_fund)
    scenario_builder.build_scenario_builder(ctx, data, nav.plan_ids)
    rebalancing.build_rebalancing_sheet(ctx, data, layouts)
    performance_sheet.build_performance_sheet(ctx, data, layouts, nav.plan_ids, nav.plan_fund)
