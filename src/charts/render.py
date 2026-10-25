"""Renders ChartSpecs into chart zones. Owner: 04-charts. Runs last in the build."""
from src.common.workbook import WorkbookContext


def render_charts(ctx: WorkbookContext, data) -> None:
    raise NotImplementedError("04-charts: see spec/worker_briefs/04-charts.md")
