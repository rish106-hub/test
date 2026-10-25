"""Contract §7.0 coverage status of a holdings line, and §7.5a match status.

`match_status` lives here (and is re-exported by coverage.py) because the status of a line depends on it;
keeping both in one module avoids an import cycle.
"""
from __future__ import annotations

from src.common.enums import EQUITY_ASSET_CLASSES, AssetClass, CoverageStatus, HoldingsMatchStatus, LineRole
from src.fund_nav.model import HoldingLine


def is_equity(line: HoldingLine) -> bool:
    """A POSITION line in an equity asset class (Indian or foreign listed equity)."""
    return line.line_role == LineRole.POSITION and AssetClass(line.asset_class) in EQUITY_ASSET_CLASSES


def match_status(line: HoldingLine) -> HoldingsMatchStatus | None:
    """§7.5a. None for ONA lines. UNMATCHED: no registry Security_ID. NO_PRICE: known, no price at in_Price_Date."""
    if line.line_role != LineRole.POSITION:
        return None
    if line.security_id is None:
        return HoldingsMatchStatus.UNMATCHED
    if line.price_inr is None:
        return HoldingsMatchStatus.NO_PRICE
    return HoldingsMatchStatus.MATCHED


def fair_value_for_case(line: HoldingLine, case: str = "Base") -> float | None:
    """The line's fair value (INR/share) for Base | Bear | Bull | Selected; None when there is no valid output."""
    if case == "Selected":
        return line.selected_fv_inr
    return line.fv_inr.get(case)


def coverage_status(line: HoldingLine, case: str = "Base") -> CoverageStatus:
    """§7.0. A POSITION line that is not MATCHED is UNVALUED, even if a fair value exists (D-026)."""
    if line.line_role != LineRole.POSITION:
        return CoverageStatus.CARRYING_VALUE
    if match_status(line) != HoldingsMatchStatus.MATCHED:
        return CoverageStatus.UNVALUED
    if is_equity(line):
        return (CoverageStatus.MODEL_VALUED if fair_value_for_case(line, case) is not None
                else CoverageStatus.UNVALUED)
    return CoverageStatus.MARKET_PASS_THROUGH
