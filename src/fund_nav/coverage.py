"""Contract §7.5."""
from typing import Sequence

from src.fund_nav.model import CoverageResult, HoldingLine


def coverage_summary(lines: Sequence[HoldingLine], warn: float, fail: float, case: str = "Base") -> CoverageResult:
    raise NotImplementedError("03-nav: contract §7.5")
