"""Builds PEER_GROUPS (tbl_PeerMembership, tbl_PeerMetrics, tbl_PeerSummary). Owner: 04-charts."""
from src.common.workbook import WorkbookContext


def build_sheets(ctx: WorkbookContext, data) -> None:
    raise NotImplementedError("04-charts: see spec/worker_briefs/04-charts.md")
