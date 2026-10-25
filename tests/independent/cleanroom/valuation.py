"""Clean-room contract §2, §3.1-3.8, §4 and §10 (bank and insurer valuation).

Units: per-share values in INR, aggregates in INR crore, rates as decimals.
Year fraction for discounting and roll-forward: days / 365.25 (contract §0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Callable, Mapping, Sequence

from src.common.units import DAYS_PER_YEAR_DISCOUNT, INR_PER_CRORE


class QAValuationError(ValueError):
    """The inputs cannot produce a valid valuation."""


class QATerminalGrowthError(QAValuationError):
    """g >= r in a Gordon terminal value (contract §10 TV-1)."""


class QADoubleCountingError(QAValuationError):
    """Insurance SOTP with both methods, or neither (contract §4)."""


class QAMethodNotAllowedError(QAValuationError):
    """FCFF DCF as a bank's primary method (R004)."""


# --------------------------------------------------------------------------- §2
def capm(risk_free: float, beta: float, erp: float) -> float:
    return risk_free + beta * erp


def discount_factor(rate: float, tau: float) -> float:
    return (1.0 + rate) ** (-tau)


def tau(start: date, end: date) -> float:
    return (end - start).days / DAYS_PER_YEAR_DISCOUNT


# --------------------------------------------------------------------------- §10
def gordon(next_flow: float, r: float, g: float) -> float:
    if not g < r:
        raise QATerminalGrowthError(f"g={g} >= r={r}")
    return next_flow / (r - g)


def terminal_flag(tv_share: float, warn: float) -> str:
    return "WARNING" if tv_share > warn else "PASS"


def sensitivity_grid(fn: Callable[[float, float], float], rates: Sequence[float],
                     growths: Sequence[float]) -> list[list[float | None]]:
    return [[(fn(r, g) if g < r else None) for g in growths] for r in rates]


# --------------------------------------------------------------------------- §3.2
@dataclass(frozen=True)
class RI:
    value_at_anchor: float
    pv_residual_income: float
    terminal_value: float
    pv_terminal_value: float
    terminal_value_share: float
    book_values: tuple[float, ...]
    residual_incomes: tuple[float, ...]


def clean_surplus_path(bv0: float, eps: Sequence[float], dps: Sequence[float]) -> list[float]:
    if len(eps) != len(dps):
        raise QAValuationError("eps and dps must cover the same years")
    bv = [bv0]
    for e, d in zip(eps, dps):
        bv.append(bv[-1] + e - d)
    return bv


def residual_income(bv0: float, eps: Sequence[float], dps: Sequence[float], r: float,
                    roe_t: float, g: float) -> RI:
    if not g < r:
        raise QATerminalGrowthError(f"g={g} >= r={r}")
    bv = clean_surplus_path(bv0, eps, dps)
    n = len(eps)
    ri = [eps[t] - r * bv[t] for t in range(n)]                      # beginning-of-year BV
    pv_ri = sum(ri[t] * (1 + r) ** -(t + 1) for t in range(n))
    tv = (roe_t - r) * bv[n] / (r - g)
    pv_tv = tv * (1 + r) ** -n
    v = bv0 + pv_ri + pv_tv
    return RI(v, pv_ri, tv, pv_tv, pv_tv / v, tuple(bv), tuple(ri))


# --------------------------------------------------------------------------- §3.3
@dataclass(frozen=True)
class DDM:
    value_at_anchor: float
    pv_dividends: float
    terminal_value: float
    pv_terminal_value: float
    terminal_value_share: float


def dividend_discount(bv0: float, eps: Sequence[float], dps: Sequence[float], r: float,
                      roe_t: float, payout_t: float, g: float) -> DDM:
    if not g < r:
        raise QATerminalGrowthError(f"g={g} >= r={r}")
    bv = clean_surplus_path(bv0, eps, dps)
    n = len(dps)
    pv_d = sum(dps[t] * (1 + r) ** -(t + 1) for t in range(n))
    tv = roe_t * bv[n] * payout_t / (r - g)
    pv_tv = tv * (1 + r) ** -n
    v = pv_d + pv_tv
    return DDM(v, pv_d, tv, pv_tv, pv_tv / v)


# --------------------------------------------------------------------------- §3.4
def justified_pb(roe_t: float, r: float, g: float) -> float:
    if not g < r:
        raise QATerminalGrowthError(f"g={g} >= r={r}")
    return (roe_t - g) / (r - g)


# --------------------------------------------------------------------------- §3.5
@dataclass(frozen=True)
class PeerRel:
    value: float | None
    flag: str


def peer_relative(median_multiple: float | None, metric: float | None, n_valid: int,
                  min_peers: int = 3) -> PeerRel:
    if n_valid == 0 or median_multiple is None or metric is None:
        return PeerRel(None, "MISSING")                            # blank and UNVALUED, never 0
    return PeerRel(median_multiple * metric, "WARNING" if n_valid < min_peers else "PASS")


@dataclass(frozen=True)
class PeerStat:
    median: float | None
    n_valid: int
    n_excluded: int
    min: float | None
    max: float | None


def peer_statistic(members: Sequence[Mapping], metric: Mapping[str, Mapping],
                   exclude_security_id: str | None = None) -> PeerStat:
    """§9: Included AND Is_Meaningful AND numeric value; the subject is excluded."""
    vals, excluded = [], 0
    for m in members:
        sid = m["Security_ID"]
        row = metric.get(sid, {})
        v = row.get("Value")
        ok = (bool(m["Included"]) and bool(row.get("Is_Meaningful")) and isinstance(v, (int, float))
              and sid != exclude_security_id)
        if ok:
            vals.append(float(v))
        else:
            excluded += 1
    if not vals:
        return PeerStat(None, 0, excluded, None, None)
    return PeerStat(median(vals), len(vals), excluded, min(vals), max(vals))


# --------------------------------------------------------------------------- §3.1
def roll_forward(value_at_anchor: float, anchor: date, valuation: date, r: float,
                 dividends: Sequence[tuple[date, float]] = ()) -> float:
    v = value_at_anchor * (1 + r) ** tau(anchor, valuation)
    for ex, dps in dividends:
        if anchor < ex <= valuation:
            v -= dps * (1 + r) ** tau(ex, valuation)
    return v


def _overlap_days(a0: date, a1: date, b0: date, b1: date) -> int:
    """Days in the intersection of half-open intervals (a0, a1] and (b0, b1]."""
    lo, hi = max(a0, b0), min(a1, b1)
    return max(0, (hi - lo).days)


def accrued_forecast_eps(anchor: date, eps_forecast: Sequence[tuple[date, float]],
                         start: date, end: date) -> float:
    """Σ_t EPS_t × days((start, end] ∩ FY_t) / days(FY_t); FY_t = (FYE_{t-1}, FYE_t], FYE_0 = A."""
    total, prev = 0.0, anchor
    for fye, eps in eps_forecast:
        fy_days = (fye - prev).days
        total += eps * _overlap_days(start, end, prev, fye) / fy_days
        prev = fye
    return total


@dataclass(frozen=True)
class Bridge:
    bv_reported_at_anchor: float
    latest_results_period_end: date
    eps_reported_after_anchor: float
    eps_forecast_stub: float
    dividends_paid: float
    bv_estimated_at_valuation: float
    interim_eps_deviation_pct: float | None
    forecast_update_flag: str
    financials_age_days: int
    anchor_age_days: int
    freshness_status: str


def freshness(anchor: date, results_end: date, valuation: date, stale_days: int = 135,
              anchor_max_days: int = 425) -> tuple[int, int, str]:
    fin_age = (valuation - results_end).days
    anc_age = (valuation - anchor).days
    status = "FAIL" if anc_age > anchor_max_days else ("STALE" if fin_age > stale_days else "PASS")
    return fin_age, anc_age, status


def equity_bridge(bv_a: float, anchor: date, eps_forecast: Sequence[tuple[date, float]], valuation: date,
                  interim: Sequence[tuple[date, float]] = (), dividends: Sequence[tuple[date, float]] = (),
                  *, dev_warn: float = 0.15, stale_days: int = 135, anchor_max_days: int = 425) -> Bridge:
    """Contract §3.1a/b. `interim` is (period_end, EPS) of discrete reported periods."""
    if not eps_forecast or valuation > eps_forecast[-1][0]:
        raise QAValuationError("valuation date is beyond the last forecast fiscal year end")
    reported = [(d, e) for d, e in interim if anchor < d <= valuation]
    r_end = max((d for d, _ in reported), default=anchor)
    eps_rep = sum(e for _, e in reported)
    stub = accrued_forecast_eps(anchor, eps_forecast, r_end, valuation)
    divs = sum(dps for ex, dps in dividends if anchor < ex <= valuation)
    bv_v = bv_a + eps_rep + stub - divs
    if r_end > anchor:
        fc_ar = accrued_forecast_eps(anchor, eps_forecast, anchor, r_end)
        dev = eps_rep / fc_ar - 1
        flag = "WARNING" if abs(dev) > dev_warn else "PASS"
    else:
        # QA-READING (F-007): no interim results means the check cannot run. The contract
        # gives no flag value; "PASS" is used here and only the deviation (None) is compared.
        dev, flag = None, "PASS"
    fin_age, anc_age, status = freshness(anchor, r_end, valuation, stale_days, anchor_max_days)
    return Bridge(bv_a, r_end, eps_rep, stub, divs, bv_v, dev, flag, fin_age, anc_age, status)


# --------------------------------------------------------------------------- §3.6
@dataclass(frozen=True)
class ProjYear:
    advances: float
    nii: float
    non_interest_income: float
    opex: float
    ppop: float
    provisions: float
    pat: float
    eps: float
    dps: float
    equity: float
    bvps: float
    roe: float


def project_bank(base, drivers) -> list[ProjYear]:
    """base/drivers: any objects with the attributes of the §3.6 driver list (duck-typed)."""
    adv, iea = base.advances, base.advances * base.iea_to_advances
    nonii, opex, eq, shares = base.non_interest_income, base.operating_expenses, base.equity, base.diluted_shares
    out = []
    for d in drivers:
        shares = getattr(d, "diluted_shares", None) or shares
        adv_t = adv * (1 + d.advance_growth)
        iea_t = adv_t * d.iea_to_advances
        nii = d.nim * (iea + iea_t) / 2
        nonii_t = nonii * (1 + d.non_interest_income_growth)
        opex_t = opex * (1 + d.opex_growth)
        ppop = nii + nonii_t - opex_t
        prov = d.credit_cost * (adv + adv_t) / 2
        pat = (ppop - prov) * (1 - d.tax_rate)
        eps = pat * INR_PER_CRORE / shares
        dps = eps * d.payout_ratio
        eq_t = eq + pat - dps * shares / INR_PER_CRORE
        out.append(ProjYear(adv_t, nii, nonii_t, opex_t, ppop, prov, pat, eps, dps, eq_t,
                            eq_t * INR_PER_CRORE / shares, pat / ((eq + eq_t) / 2)))
        adv, iea, nonii, opex, eq = adv_t, iea_t, nonii_t, opex_t, eq_t
    return out


def capital_retention_check(bv_clean_surplus: Sequence[float], bvps_driver: Sequence[float],
                            tol: float = 0.005) -> str:
    worst = max((abs(a / b - 1) for a, b in zip(bv_clean_surplus, bvps_driver)), default=0.0)
    return "PASS" if worst <= tol else "FAIL"


# --------------------------------------------------------------------------- §3.8
BLEND_WEIGHT_TOL = 1e-9   # QA-READING (F-008): the contract says "validated" without a tolerance


def blend(values: Mapping[str, float | None], weights: Mapping[str, float]) -> float | None:
    if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1) > BLEND_WEIGHT_TOL:
        raise QAValuationError("blend weights must be >= 0 and sum to 1")
    total = 0.0
    for m, w in weights.items():
        if w == 0:
            continue
        v = values.get(m)
        if v is None:
            return None
        total += w * v
    return total


# --------------------------------------------------------------------------- R004
FORBIDDEN_BANK_PRIMARY = {"FCFF DCF (WACC)"}
BANK_MODELS = {"Deposit-taking bank", "Small finance bank"}


def validate_method(business_model: str, method: str) -> None:
    if business_model in BANK_MODELS and method in FORBIDDEN_BANK_PRIMARY:
        raise QAMethodNotAllowedError(f"{method} is not a valid primary method for a {business_model}")


# --------------------------------------------------------------------------- §4
def appraisal_value(ev: float, vnb: float | None = None, vnb_multiple: float | None = None,
                    target_p_ev: float | None = None) -> float:
    a = vnb is not None and vnb_multiple is not None
    b = target_p_ev is not None
    if a == b:
        raise QADoubleCountingError("exactly one of Method A (VNB multiple) and Method B (P/EV) per case")
    return ev + vnb * vnb_multiple if a else ev * target_p_ev


def sotp_per_share(ev: float, stake: float, cash: float, debt: float, other: float, shares: float,
                   holdco_discount: float = 0.0, vnb=None, vnb_multiple=None, target_p_ev=None) -> float:
    appraisal = appraisal_value(ev, vnb, vnb_multiple, target_p_ev)
    equity = stake * appraisal * (1 - holdco_discount) + cash - debt + other
    return equity * INR_PER_CRORE / shares
