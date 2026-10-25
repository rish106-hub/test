"""Contract §7.5: the three data-quality measures, kept separate (D-026)."""
from datetime import date
from typing import Sequence

from src.common.enums import HoldingsMatchStatus
from src.fund_nav.model import CoverageResult, FreshnessResult, HoldingLine, HoldingsCoverageResult


def match_status(line: HoldingLine) -> HoldingsMatchStatus | None:
    """§7.5a. None for ONA lines."""
    raise NotImplementedError("03-nav: contract §7.5a")


def holdings_coverage(lines: Sequence[HoldingLine], reported_net_assets_inr_cr: float,
                      recon_tolerance: float) -> HoldingsCoverageResult:
    """(1) Holdings coverage, §7.5a."""
    raise NotImplementedError("03-nav: contract §7.5a")


def coverage_summary(lines: Sequence[HoldingLine], warn: float, fail: float, case: str = "Base") -> CoverageResult:
    """(2) Valuation coverage, §7.5b."""
    raise NotImplementedError("03-nav: contract §7.5b")


def freshness_summary(lines: Sequence[HoldingLine], portfolio_date: date, nav_date: date, valuation_date: date,
                      holdings_stale_days: int, financials_stale_days: int, nav_stale_days: int) -> FreshnessResult:
    """(3) Data freshness, §7.5c."""
    raise NotImplementedError("03-nav: contract §7.5c")
