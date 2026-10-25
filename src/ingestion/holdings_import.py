"""Monthly portfolio-disclosure import (spec <monthly_update_workflow>)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ImportDiff:
    added: tuple[str, ...]        # Security_IDs new this month
    removed: tuple[str, ...]      # Security_IDs no longer held
    unmatched_isins: tuple[str, ...]  # not in registry: need a registry row and a valuation status
    weight_sum: float
    weight_sum_status: str        # PASS | WARNING (outside 1 +/- in_Weight_Sum_Tol)


def parse_disclosure(fund_id: str, path: Path, source_id: str, import_batch_id: str) -> list[dict]:
    """AMC monthly portfolio file -> fund_holdings rows (schema.FUND_HOLDINGS stored columns).
    Converts lakh to crore, keeps Raw_Market_Value/Raw_Market_Value_Unit, assigns Line_Role."""
    raise NotImplementedError("01-data")


def diff_portfolios(previous: Sequence[Mapping], current: Sequence[Mapping], tolerance: float) -> ImportDiff:
    raise NotImplementedError("01-data")
