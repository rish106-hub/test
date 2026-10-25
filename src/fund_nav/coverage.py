"""Contract §7.5: the three data-quality measures, kept separate (D-026)."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from src.common.enums import CoverageStatus, HoldingsMatchStatus, LineRole
from src.fund_nav.classify import coverage_status, is_equity, match_status
from src.fund_nav.methods import reconcile_net_assets
from src.fund_nav.model import CoverageResult, FreshnessResult, HoldingLine, HoldingsCoverageResult

__all__ = ["match_status", "holdings_coverage", "coverage_summary", "freshness_summary", "pct_text"]


def pct_text(fraction: float) -> str:
    """One-decimal percentage text, rounded half-up like Excel TEXT(x*100,"0.0")."""
    d = Decimal(repr(round(fraction * 100, 9))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{d}"


def holdings_coverage(lines: Sequence[HoldingLine], reported_net_assets_inr_cr: float,
                      recon_tolerance: float) -> HoldingsCoverageResult:
    """(1) Holdings coverage, §7.5a."""
    recon = reconcile_net_assets(lines, reported_net_assets_inr_cr, recon_tolerance)
    positions = [l for l in lines if l.line_role == LineRole.POSITION]
    unmatched = tuple(l.line_id for l in positions if match_status(l) != HoldingsMatchStatus.MATCHED)
    total_w = sum(l.weight for l in positions)
    matched_w = sum(l.weight for l in positions if match_status(l) == HoldingsMatchStatus.MATCHED)
    match_pct = 1.0 if total_w == 0 else matched_w / total_w          # no positions: nothing is unmatched
    # PASS needs no unmatched line at all (stricter than match_pct == 1 only for zero-weight lines).
    status = "PASS" if recon.status == "PASS" and not unmatched else "FAIL"
    return HoldingsCoverageResult(value_coverage_pct=recon.computed_inr_cr / reported_net_assets_inr_cr,
                                  match_pct=match_pct, unmatched_line_ids=unmatched,
                                  recon_status=recon.status, status=status)


def coverage_summary(lines: Sequence[HoldingLine], warn: float, fail: float, case: str = "Base") -> CoverageResult:
    """(2) Valuation coverage, §7.5b."""
    st = {l.line_id: coverage_status(l, case) for l in lines}
    total = sum(l.weight for l in lines if st[l.line_id] != CoverageStatus.UNVALUED)
    equity_w = sum(l.weight for l in lines if is_equity(l))
    valued_w = sum(l.weight for l in lines if st[l.line_id] == CoverageStatus.MODEL_VALUED)
    equity = None if equity_w == 0 else valued_w / equity_w
    unvalued = [l for l in lines if st[l.line_id] == CoverageStatus.UNVALUED]
    unvalued_w = sum(l.weight for l in unvalued)
    if equity is None:
        status = "PASS" if not unvalued else "FAIL"
    elif equity < fail:
        status = "FAIL"
    elif equity < warn:
        status = "WARNING"
    else:
        status = "PASS"
    equity_txt = "n/a" if equity is None else pct_text(equity) + "%"
    caption = f"Covers {equity_txt} of equity; {pct_text(unvalued_w)}% of net assets unvalued (adjustment 0)"
    return CoverageResult(coverage_total_pct=total, coverage_equity_pct=equity, unvalued_weight_pct=unvalued_w,
                          unvalued_count=len(unvalued),
                          unvalued_value_inr_cr=sum(l.market_value_inr_cr for l in unvalued),
                          status=status, caption=caption)


def freshness_summary(lines: Sequence[HoldingLine], portfolio_date: date, nav_date: date, valuation_date: date,
                      holdings_stale_days: int, financials_stale_days: int, nav_stale_days: int,
                      case: str = "Base") -> FreshnessResult:
    """(3) Data freshness, §7.5c. A MODEL_VALUED line with no Financials_As_Of is stale, never fresh."""
    holdings_age = (valuation_date - portfolio_date).days
    nav_gap = (valuation_date - nav_date).days
    valued = [l for l in lines if coverage_status(l, case) == CoverageStatus.MODEL_VALUED]
    ages = [(valuation_date - l.financials_as_of).days for l in valued if l.financials_as_of is not None]
    stale_w = sum(l.weight for l in valued
                  if l.financials_as_of is None or (valuation_date - l.financials_as_of).days > financials_stale_days)
    stale = holdings_age > holdings_stale_days or nav_gap > nav_stale_days or round(stale_w, 12) > 0
    return FreshnessResult(holdings_age_days=holdings_age, nav_date_gap_days=nav_gap,
                           max_financials_age_days=max(ages) if ages else None,
                           stale_valued_weight_pct=stale_w, status="STALE" if stale else "PASS")
