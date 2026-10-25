"""Contract §7.2-§7.4 NAV methods. `case` is "Base" | "Bear" | "Bull" | "Selected"."""
from __future__ import annotations

from typing import Sequence

from src.common.enums import CoverageStatus, LineRole
from src.common.units import INR_PER_CRORE
from src.fund_nav.classify import coverage_status, fair_value_for_case
from src.fund_nav.model import HoldingLine, NavResult, ReconResult


class UnmarkableHoldingError(ValueError):
    """A position that cannot be marked (no quantity or price). Excel shows #N/A (WI-6); never silently 0."""


def _sector(line: HoldingLine) -> str:
    return str(line.sector)


def _by_sector(lines: Sequence[HoldingLine], per_line: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for l in lines:
        out[_sector(l)] = out.get(_sector(l), 0.0) + per_line[l.line_id]
    return out


def _mv(quantity: float | None, price: float | None, line: HoldingLine) -> float:
    if quantity is None or price is None:
        raise UnmarkableHoldingError(f"{line.line_id}: no quantity or price, the position cannot be marked")
    return quantity * price / INR_PER_CRORE


def is_marked(line: HoldingLine) -> bool:
    """True when the line is carried as quantity x price (everything except ONA and pass-through lines)."""
    return line.line_role == LineRole.POSITION and coverage_status(line) != CoverageStatus.MARKET_PASS_THROUGH


def weighted_adjustment_nav(official_nav: float, lines: Sequence[HoldingLine], case: str = "Base") -> NavResult:
    """Method 1. Adj_i = w_i (FV_i / P_i - 1) for MODEL_VALUED lines, else 0 (the line stays flagged, D-015)."""
    adj: dict[str, float] = {}
    for l in lines:
        if coverage_status(l, case) == CoverageStatus.MODEL_VALUED:
            adj[l.line_id] = l.weight * (fair_value_for_case(l, case) / l.price_inr - 1)
        else:
            adj[l.line_id] = 0.0
    total = sum(adj.values())
    return NavResult(nav=official_nav * (1 + total), sum_adjustment=total, adjustment_by_line=adj,
                     adjustment_by_sector=_by_sector(lines, adj))


def _net_assets(lines: Sequence[HoldingLine], fair_case: str | None, scenario: bool):
    """(NA_mkt, NA_target, per-line mkt value, per-line target value). Target = fair (case) or scenario market."""
    mkt, tgt = {}, {}
    for l in lines:
        if not is_marked(l):
            mkt[l.line_id] = tgt[l.line_id] = l.market_value_inr_cr           # ONA and pass-through: disclosed value
            continue
        mkt[l.line_id] = _mv(l.quantity, l.price_inr, l)
        if scenario:
            tgt[l.line_id] = _mv(l.quantity, l.scenario_price_inr, l)
        elif coverage_status(l, fair_case) == CoverageStatus.MODEL_VALUED:
            tgt[l.line_id] = _mv(l.quantity, fair_value_for_case(l, fair_case), l)
        else:
            tgt[l.line_id] = mkt[l.line_id]                                   # FV := P for non-MODEL_VALUED lines
    return sum(mkt.values()), sum(tgt.values()), mkt, tgt


def _ratio_result(official_nav, lines, na_mkt, na_tgt, mkt, tgt) -> NavResult:
    per_line = {k: (tgt[k] - mkt[k]) / na_mkt for k in mkt}
    return NavResult(nav=official_nav * na_tgt / na_mkt, sum_adjustment=na_tgt / na_mkt - 1,
                     adjustment_by_line=per_line, adjustment_by_sector=_by_sector(lines, per_line),
                     na_market_inr_cr=na_mkt, na_numerator_inr_cr=na_tgt)


def quantity_based_nav(official_nav: float, lines: Sequence[HoldingLine], case: str = "Base") -> NavResult:
    """Method 2, ratio form (D-004): Official_NAV x NA_fair / NA_mkt."""
    na_mkt, na_fair, mkt, fair = _net_assets(lines, case, scenario=False)
    return _ratio_result(official_nav, lines, na_mkt, na_fair, mkt, fair)


def units_based_nav(lines: Sequence[HoldingLine], units_outstanding: float, case: str = "Base") -> float:
    """Secondary form of Method 2 when plan-level units are disclosed: NA_fair * 1e7 / units."""
    _, na_fair, _, _ = _net_assets(lines, case, scenario=False)
    return na_fair * INR_PER_CRORE / units_outstanding


def scenario_market_nav(official_nav: float, lines: Sequence[HoldingLine]) -> NavResult:
    """Method 3: Official_NAV x NA_scen / NA_mkt, marking every priced position at its scenario price."""
    na_mkt, na_scen, mkt, scen = _net_assets(lines, None, scenario=True)
    return _ratio_result(official_nav, lines, na_mkt, na_scen, mkt, scen)


def reconcile_net_assets(lines: Sequence[HoldingLine], reported_inr_cr: float, tolerance_pct: float) -> ReconResult:
    """Sum of disclosed Market_Value_INR_Cr (positions + ONA, each line once) vs reported scheme net assets."""
    if not reported_inr_cr or reported_inr_cr <= 0:
        raise ValueError("reported scheme net assets must be a positive number")
    computed = sum(l.market_value_inr_cr for l in lines)
    gap_pct = computed / reported_inr_cr - 1
    return ReconResult(computed_inr_cr=computed, reported_inr_cr=reported_inr_cr, gap_inr_cr=computed - reported_inr_cr,
                       gap_pct=gap_pct, status="FAIL" if abs(gap_pct) > tolerance_pct else "PASS")
