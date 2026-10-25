"""Contract §7.2-§7.4 NAV methods. `case` is "Base" | "Bear" | "Bull" | "Selected"."""
from __future__ import annotations

from typing import Sequence

from src.fund_nav.model import HoldingLine, NavResult, ReconResult


def weighted_adjustment_nav(official_nav: float, lines: Sequence[HoldingLine], case: str = "Base") -> NavResult:
    """Method 1."""
    raise NotImplementedError("03-nav: contract §7.2")


def quantity_based_nav(official_nav: float, lines: Sequence[HoldingLine], case: str = "Base") -> NavResult:
    """Method 2, ratio form (D-004)."""
    raise NotImplementedError("03-nav: contract §7.3")


def units_based_nav(lines: Sequence[HoldingLine], units_outstanding: float, case: str = "Base") -> float:
    """Secondary form of Method 2 when plan-level units are disclosed: NA_fair * 1e7 / units."""
    raise NotImplementedError("03-nav: contract §7.3")


def scenario_market_nav(official_nav: float, lines: Sequence[HoldingLine]) -> NavResult:
    """Method 3."""
    raise NotImplementedError("03-nav: contract §7.4")


def reconcile_net_assets(lines: Sequence[HoldingLine], reported_inr_cr: float, tolerance_pct: float) -> ReconResult:
    """Sum of disclosed Market_Value_INR_Cr (positions + ONA) vs reported scheme net assets."""
    raise NotImplementedError("03-nav: contract §7.3 reconciliation")
