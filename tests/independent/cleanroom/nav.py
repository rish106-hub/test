"""Clean-room contract §7.0-7.8: holdings classification, NAV methods 1-4, reconciliation and
the three separate data-quality measures (R006, R009, R011, D-004, D-005, D-015, D-026).

Holdings lines are duck-typed: any object with the attributes line_id, line_role, asset_class,
sector, weight, market_value_inr_cr, security_id, quantity, price_inr, fv_inr (case -> INR),
scenario_price_inr, selected_fv_inr and financials_as_of. Weights are decimals of total
scheme net assets, money is INR crore, prices and fair values are INR per share.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor
from typing import Mapping, Sequence

from src.common.units import INR_PER_CRORE

EQUITY = {"Indian listed equity", "Foreign listed equity"}
MODEL_VALUED, CARRYING_VALUE, MARKET_PASS_THROUGH, UNVALUED = (
    "MODEL_VALUED", "CARRYING_VALUE", "MARKET_PASS_THROUGH", "UNVALUED")


def _s(v) -> str | None:
    return None if v is None else str(v)


def is_position(line) -> bool:
    return _s(line.line_role) == "POSITION"


def is_equity(line) -> bool:
    return is_position(line) and _s(line.asset_class) in EQUITY


# --------------------------------------------------------------------------- §7.5a / §7.0
def match_status(line) -> str | None:
    if not is_position(line):
        return None
    if not line.security_id:
        return "UNMATCHED"
    if line.price_inr is None:
        return "NO_PRICE"
    return "MATCHED"


def fair_value(line, case: str) -> float | None:
    if case == "Selected":
        return line.selected_fv_inr
    return (line.fv_inr or {}).get(case)


def coverage_status(line, case: str = "Base") -> str:
    if not is_position(line):
        return CARRYING_VALUE
    if match_status(line) != "MATCHED":
        return UNVALUED                         # never MODEL_VALUED unless MATCHED (D-026)
    if _s(line.asset_class) in EQUITY:
        return MODEL_VALUED if fair_value(line, case) is not None else UNVALUED
    return MARKET_PASS_THROUGH


# --------------------------------------------------------------------------- §7.2 Method 1
@dataclass(frozen=True)
class Nav:
    nav: float | None
    sum_adjustment: float | None
    adjustment_by_line: dict
    adjustment_by_sector: dict
    na_market_inr_cr: float | None = None
    na_numerator_inr_cr: float | None = None


def weighted_adjustment_nav(official_nav: float, lines: Sequence, case: str = "Base") -> Nav:
    by_line, by_sector = {}, {}
    for l in lines:
        adj = 0.0
        if coverage_status(l, case) == MODEL_VALUED:
            adj = l.weight * (fair_value(l, case) / l.price_inr - 1)
        by_line[l.line_id] = adj
        by_sector[_s(l.sector)] = by_sector.get(_s(l.sector), 0.0) + adj
    total = sum(by_line.values())
    return Nav(official_nav * (1 + total), total, by_line, by_sector)


# --------------------------------------------------------------------------- §7.3 Method 2
def _mv(q, p):
    return None if q is None or p is None else q * p / INR_PER_CRORE


def _net_assets(lines: Sequence, price_of, mpt_basis: str) -> float | None:
    """Σ position values at price_of(line) + ONA.

    QA-READING (F-001): the contract puts MARKET_PASS_THROUGH lines in ONA at their disclosed
    value ("line values"); mpt_basis="disclosed" follows that text, "market" marks them q × P
    like link_patterns.H_MV_MKT does. A POSITION that cannot be marked makes the result None,
    the Python analogue of the workbook's #N/A (§7.5a).
    """
    total = 0.0
    for l in lines:
        st = coverage_status(l)
        if st == CARRYING_VALUE or (st == MARKET_PASS_THROUGH and mpt_basis == "disclosed"):
            total += l.market_value_inr_cr
            continue
        v = _mv(l.quantity, price_of(l))
        if v is None:
            return None
        total += v
    return total


def quantity_based_nav(official_nav: float, lines: Sequence, case: str = "Base",
                       mpt_basis: str = "disclosed") -> Nav:
    def fair_price(l):
        return fair_value(l, case) if coverage_status(l, case) == MODEL_VALUED else l.price_inr
    na_mkt = _net_assets(lines, lambda l: l.price_inr, mpt_basis)
    na_fair = _net_assets(lines, fair_price, mpt_basis)
    nav = None if na_mkt is None or na_fair is None else official_nav * na_fair / na_mkt
    return Nav(nav, None if nav is None else nav / official_nav - 1, {}, {}, na_mkt, na_fair)


def units_based_nav(lines: Sequence, units: float, case: str = "Base", mpt_basis: str = "disclosed"):
    def fair_price(l):
        return fair_value(l, case) if coverage_status(l, case) == MODEL_VALUED else l.price_inr
    na_fair = _net_assets(lines, fair_price, mpt_basis)
    return None if na_fair is None else na_fair * INR_PER_CRORE / units


# --------------------------------------------------------------------------- §7.4 Method 3
def scenario_market_nav(official_nav: float, lines: Sequence, mpt_basis: str = "disclosed") -> Nav:
    na_mkt = _net_assets(lines, lambda l: l.price_inr, mpt_basis)
    na_scen = _net_assets(lines, lambda l: l.scenario_price_inr, mpt_basis)
    nav = None if na_mkt is None or na_scen is None else official_nav * na_scen / na_mkt
    return Nav(nav, None if nav is None else nav / official_nav - 1, {}, {}, na_mkt, na_scen)


# --------------------------------------------------------------------------- reconciliation
@dataclass(frozen=True)
class Recon:
    computed_inr_cr: float
    reported_inr_cr: float
    gap_inr_cr: float
    gap_pct: float
    status: str


def reconcile(lines: Sequence, reported: float, tol: float) -> Recon:
    computed = sum(l.market_value_inr_cr for l in lines)
    gap = computed - reported
    return Recon(computed, reported, gap, gap / reported, "FAIL" if abs(gap) / reported > tol else "PASS")


# --------------------------------------------------------------------------- §7.5a
@dataclass(frozen=True)
class HoldingsCov:
    value_coverage_pct: float
    match_pct: float
    unmatched_line_ids: tuple
    recon_status: str
    status: str


def holdings_coverage(lines: Sequence, reported: float, tol: float) -> HoldingsCov:
    rec = reconcile(lines, reported, tol)
    pos = [l for l in lines if is_position(l)]
    w_pos = sum(l.weight for l in pos)
    w_match = sum(l.weight for l in pos if match_status(l) == "MATCHED")
    match_pct = w_match / w_pos if w_pos else 1.0
    unmatched = tuple(l.line_id for l in pos if match_status(l) != "MATCHED")
    ok = rec.status == "PASS" and not unmatched
    return HoldingsCov(rec.computed_inr_cr / reported, match_pct, unmatched, rec.status, "PASS" if ok else "FAIL")


# --------------------------------------------------------------------------- §7.5b
@dataclass(frozen=True)
class ValuationCov:
    coverage_total_pct: float
    coverage_equity_pct: float | None
    unvalued_weight_pct: float
    unvalued_count: int
    unvalued_value_inr_cr: float
    status: str
    caption: str


def coverage_caption(equity_pct: float | None, unvalued_pct: float) -> str:
    x = "n/a" if equity_pct is None else f"{equity_pct * 100:.1f}%"
    return f"Covers {x} of equity; {unvalued_pct * 100:.1f}% of net assets unvalued (adjustment 0)"


def coverage_summary(lines: Sequence, warn: float, fail: float, case: str = "Base") -> ValuationCov:
    st = {l.line_id: coverage_status(l, case) for l in lines}
    total = sum(l.weight for l in lines if st[l.line_id] != UNVALUED)
    eq = [l for l in lines if is_equity(l)]
    w_eq = sum(l.weight for l in eq)
    eq_pct = sum(l.weight for l in eq if st[l.line_id] == MODEL_VALUED) / w_eq if w_eq else None
    unv = [l for l in lines if st[l.line_id] == UNVALUED]
    uw = sum(l.weight for l in unv)
    if eq_pct is None:
        status = "PASS"     # QA-READING (F-009): a fund with no equity has nothing to value
    else:
        status = "FAIL" if eq_pct < fail else ("WARNING" if eq_pct < warn else "PASS")
    return ValuationCov(total, eq_pct, uw, len(unv), sum(l.market_value_inr_cr for l in unv),
                        status, coverage_caption(eq_pct, uw))


# --------------------------------------------------------------------------- §7.5c
@dataclass(frozen=True)
class Fresh:
    holdings_age_days: int
    nav_date_gap_days: int
    max_financials_age_days: int | None
    stale_valued_weight_pct: float
    status: str


def freshness_summary(lines: Sequence, portfolio_date: date, nav_date: date, valuation_date: date,
                      holdings_stale_days: int, financials_stale_days: int, nav_stale_days: int) -> Fresh:
    h_age = (valuation_date - portfolio_date).days
    n_gap = (valuation_date - nav_date).days
    valued = [l for l in lines if coverage_status(l) == MODEL_VALUED]
    ages = [(valuation_date - l.financials_as_of).days for l in valued if l.financials_as_of is not None]
    max_age = max(ages) if ages else None   # QA-READING (F-009): undated lines are excluded from the max
    stale_w = sum(l.weight for l in valued
                  if l.financials_as_of is None or (valuation_date - l.financials_as_of).days > financials_stale_days)
    stale = h_age > holdings_stale_days or n_gap > nav_stale_days or stale_w > 0
    return Fresh(h_age, n_gap, max_age, stale_w, "STALE" if stale else "PASS")


# --------------------------------------------------------------------------- §7.6
def effective_weights(alloc: Sequence) -> dict:
    out = {}
    for a in alloc:
        key = a.security_id or "CASH"
        out[key] = out.get(key, 0.0) + a.sector_weight * a.constituent_weight
    return out


def validate_allocation(alloc: Sequence, tol: float = 1e-6) -> list[str]:
    problems = []
    sector_w, cash_w, constituents, seen = {}, 0.0, {}, set()
    for a in alloc:
        if a.sector_weight < 0 or a.constituent_weight < 0:
            problems.append(f"{a.line_id}: negative weight")
        if a.security_id is None:
            cash_w += a.sector_weight * a.constituent_weight
            continue
        if a.security_id in seen:
            problems.append(f"{a.line_id}: duplicate Security_ID {a.security_id}")
        seen.add(a.security_id)
        sector_w.setdefault(a.sector, a.sector_weight)
        if abs(sector_w[a.sector] - a.sector_weight) > tol:
            problems.append(f"{a.line_id}: inconsistent sector weight for {a.sector}")
        constituents[a.sector] = constituents.get(a.sector, 0.0) + a.constituent_weight
    if abs(sum(sector_w.values()) + cash_w - 1) > tol:
        problems.append("sector weights + explicit cash do not sum to 1")
    for s, c in constituents.items():
        if sector_w[s] != 0 and abs(c - 1) > tol:
            problems.append(f"constituent weights in {s} sum to {c}, not 1")
    return problems


@dataclass(frozen=True)
class HypoLine:
    security_id: str
    quantity: float
    cost_inr: float
    fee_inr: float
    market_value_inr: float
    fair_value_inr: float | None


@dataclass(frozen=True)
class Hypo:
    lines: tuple
    cash_remaining_inr: float
    value_market_inr: float
    value_fair_inr: float
    status: str


def build_hypothetical_portfolio(capital: float, lines: Sequence, tc: float) -> Hypo:
    out = []
    for l in lines:
        target = capital * l.effective_weight
        buy = l.assumed_buy_price_inr if l.assumed_buy_price_inr is not None else l.scenario_price_inr
        q = l.quantity_override if l.quantity_override is not None else floor(target / (buy * (1 + tc)))
        cost = q * buy
        fv = l.fair_value_inr
        out.append(HypoLine(l.security_id, q, cost, cost * tc, q * l.scenario_price_inr,
                            None if fv is None else q * fv))
    cash = capital - sum(h.cost_inr + h.fee_inr for h in out)
    mkt = sum(h.market_value_inr for h in out) + cash
    fair = sum((h.fair_value_inr if h.fair_value_inr is not None else h.market_value_inr) for h in out) + cash
    return Hypo(tuple(out), cash, mkt, fair, "PASS" if cash >= 0 else "FAIL")


# --------------------------------------------------------------------------- §7.8
def overlap_by_weight(a: Mapping[str, float], b: Mapping[str, float]) -> tuple[float, int]:
    common = [s for s in a if s in b and a[s] > 0 and b[s] > 0]
    return sum(min(a[s], b[s]) for s in common), len(common)
