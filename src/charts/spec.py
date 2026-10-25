"""Declarative chart specifications (spec <chart_interpretation_and_quality>, D-017).

Every chart is a ChartSpec. render.py turns specs into native XlsxWriter charts placed
in chart zones reserved by the sheet owner. A spec missing any metadata field fails
validate_chart_spec, so an unlabelled chart cannot be built.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.common.enums import MetricKind


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    categories_ref: str            # structured reference or absolute range
    values_ref: str
    is_forecast: bool = False      # forecasts drawn dashed / separated (spec <chart_principles>)


@dataclass(frozen=True)
class ChartSpec:
    chart_id: str                  # G001.., V001.., B001.., or P/S/N ids from the catalogue
    zone_id: str                   # reserved by the sheet owner
    chart_type: str                # line | column | bar | scatter | doughnut
    title: str
    metric_definition: str
    period: str
    denominator: str
    units: str
    source_note: str
    observation_date_ref: str      # cell/name holding the observation date
    kind: MetricKind
    series: tuple[SeriesSpec, ...]
    n_observations_ref: str        # cell holding the count of non-blank points
    min_observations: int = 2
    missing_data_message: str = "Data unavailable - see MISSING_DATA"
    not_meaningful_reason: str | None = None   # e.g. bank EV/EBITDA: renders an NM notice instead


def validate_chart_spec(spec: ChartSpec) -> list[str]:
    raise NotImplementedError("04-charts: every metadata field non-empty; NM specs have no series")
