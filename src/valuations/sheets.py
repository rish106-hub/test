"""Builds VAL_* sheets, VALUATION_OUTPUTS and HISTORICAL_METRICS. Owner: 02-valuation.

Must expose, per valued security, out_<Security_ID>_FV_Base / _FV_Bear / _FV_Bull /
_TV_Share and populate tbl_ValuationOutputs (spec/workbook_interface.md §2).
"""
from src.common.workbook import WorkbookContext


def build_sheets(ctx: WorkbookContext, data) -> None:
    raise NotImplementedError("02-valuation: see spec/worker_briefs/02-valuation.md")
