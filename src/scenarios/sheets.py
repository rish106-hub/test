"""Builds SCENARIO_ANALYSIS (tbl_PriceControls, tbl_SectorShocks). Owner: 03-nav.

Called from src/fund_nav/sheets.py::build_sheets so 03-nav has one entry point.
"""
from src.common.workbook import WorkbookContext


def build_scenario_sheet(ctx: WorkbookContext, data) -> None:
    raise NotImplementedError("03-nav: build SCENARIO_ANALYSIS per spec/workbook_interface.md")
