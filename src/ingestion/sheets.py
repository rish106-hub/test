"""Builds 01-data sheets (registry, raw data, prices, sources, missing data, feasibility)."""
from src.common.workbook import WorkbookContext


def build_sheets(ctx: WorkbookContext, data) -> None:
    raise NotImplementedError("01-data: see spec/worker_briefs/01-data.md")
