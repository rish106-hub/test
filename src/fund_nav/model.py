"""In-memory holdings line used by every NAV reference function."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.common.enums import AssetClass, CoverageStatus, LineRole, Sector


@dataclass(frozen=True)
class HoldingLine:
    line_id: str
    line_role: LineRole
    asset_class: AssetClass
    sector: Sector
    weight: float                          # decimal of total scheme net assets (disclosed)
    market_value_inr_cr: float             # disclosed, at Portfolio_Date; ONA_LIABILITY negative
    security_id: str | None = None
    quantity: float | None = None          # POSITION lines
    price_inr: float | None = None         # Original_Market_Price at in_Price_Date, INR
    fv_inr: dict[str, float | None] = field(default_factory=dict)   # {"Base"|"Bear"|"Bull": FV INR}
    scenario_price_inr: float | None = None   # Selected_Scenario_Market_Price
    selected_fv_inr: float | None = None      # Selected_Scenario_Fair_Value


@dataclass(frozen=True)
class NavResult:
    nav: float
    sum_adjustment: float                    # Method 1 only; else NA ratio - 1
    adjustment_by_line: dict[str, float]
    adjustment_by_sector: dict[str, float]
    na_market_inr_cr: float | None = None    # Methods 2/3
    na_numerator_inr_cr: float | None = None # NA_fair or NA_scen


@dataclass(frozen=True)
class ReconResult:
    computed_inr_cr: float
    reported_inr_cr: float
    gap_inr_cr: float
    gap_pct: float
    status: str   # PASS | FAIL


@dataclass(frozen=True)
class CoverageResult:
    coverage_total_pct: float
    coverage_equity_pct: float | None
    unvalued_weight_pct: float
    unvalued_count: int
    unvalued_value_inr_cr: float
    status: str     # PASS | WARNING | FAIL
    caption: str    # "Covers X% of equity; Y% of net assets unvalued (adjustment 0)"
