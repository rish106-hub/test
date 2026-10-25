"""Python reference for one bank VAL_* sheet (contract §2, §3, §8, §10; D-020).

`run_bank_model` computes, from the same inputs the sheet reads, every value the sheet's
formulas compute: the driver projection per case (§3.6), RI (§3.2), DDM (§3.3), justified
P/B (§3.4), peer-relative P/B (§3.5), the roll-forward to the valuation date (§3.1), the
equity bridge and freshness (§3.1a/b), the blend (§3.8), terminal controls and sensitivity
grids (§10) and the expected five-year return (§8). It uses only the contract reference
functions. tests/valuations/test_sheet_matches_reference.py checks the recalculated
workbook against it.

Missing inputs never become 0. A value that cannot be computed is None, and the status
that explains why travels with it.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Sequence

from src.common.enums import CheckResult as CR, CoverageStatus
from src.common.units import INR_PER_CRORE, year_fraction
from src.valuations.bank_drivers import BankBaseYear, BankDriverYear, BankProjectionYear, project_bank
from src.valuations.bank_ri import RIResult, residual_income_value
from src.valuations.blend import blend_fair_value, validate_weights
from src.valuations.ddm import DDMResult, dividend_discount_value
from src.valuations.discounting import cost_of_equity_capm
from src.valuations.errors import ProbabilityError, TerminalGrowthError, ValuationError
from src.valuations.expected_return import (bank_exit_value, probability_weighted, reinvested_total_return,
                                            xirr)
from src.valuations.justified_pb import justified_pb
from src.valuations.parameters import CASES
from src.valuations.peer_relative import PeerRelativeResult, peer_relative_value
from src.valuations.rollforward import (EquityBridge, InterimResult, dividends_in_window, equity_bridge,
                                        freshness_status, roll_forward_value)
from src.valuations.terminal import sensitivity_grid, sensitivity_grid_2d, terminal_flag

METHODS = ("RI", "DDM", "JPB", "PEER_PB")
NOT_REINVESTED = "Dividends not reinvested (XIRR)"          # contract §8 Reinvestment_Mode values
REINVESTED = "Dividends reinvested at r_reinv"
REINVESTMENT_MODES = (NOT_REINVESTED, REINVESTED)
EXIT_HORIZON_MONTHS = 60                                     # contract §8: exit at V + 5 years
RATE_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)               # contract §10 TV-4: r_e +/-100 bp
GROWTH_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)             # g +/-100 bp
ROE_STEPS = (-0.02, -0.01, 0.0, 0.01, 0.02)                  # ROE_T +/-200 bp
PROBABILITIES_NOT_ENTERED = "NOT ENTERED"                    # blank by default; never invented (§8)
BRIDGE_HORIZON_FAIL = "FAIL: valuation date after the last forecast year end"
ER_HORIZON_FAIL = "FAIL: exit date beyond the forecast horizon"
ER_NO_EXIT_PB = "MISSING: Exit P/B not entered"
ER_NO_PRICE = "MISSING: market price"


def add_months(d: date, months: int) -> date:
    """Excel EDATE: same day of month, clamped to the month's last day."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class CaseInputs:
    drivers: tuple[BankDriverYear, ...] | None     # None when any required driver is missing
    terminal_roe: float | None
    terminal_growth: float | None
    terminal_payout: float | None
    exit_pb: float | None


@dataclass(frozen=True)
class BankModelInputs:
    anchor_date: date | None
    valuation_date: date | None
    fy_ends: tuple[date, ...]                       # FYE_1 .. FYE_N
    base: BankBaseYear | None
    risk_free: float | None
    beta: float | None
    equity_risk_premium: float | None
    cases: Mapping[str, CaseInputs]
    weights: Mapping[str, float | None]             # keys METHODS
    interims: tuple[InterimResult, ...] = ()        # reported discrete quarters after A
    dividends: tuple[tuple[date, float], ...] = ()  # (ex-date, DPS) after A
    share_actions_after_anchor: tuple[date, ...] = ()
    price: float | None = None
    eps_anchor_fy: float | None = None
    peer_pb_median: float | None = None
    peer_n_valid: int = 0
    tv_share_warn: float = 0.75
    interim_dev_warn: float = 0.15
    financials_stale_days: int = 135
    anchor_max_age_days: int = 425
    peer_min_n: int = 3
    clean_surplus_tol: float = 0.005
    reinvestment_mode: str = NOT_REINVESTED
    reinvestment_rate: float | None = None
    probabilities: Mapping[str, float | None] = field(default_factory=lambda: {c: None for c in CASES})


@dataclass(frozen=True)
class ExpectedReturnResult:
    exit_date: date
    bvps_at_exit: float | None
    exit_value: float | None
    dividends_received: tuple[float, ...]          # per forecast year t = 1..N (0 outside (V, T])
    cashflow_dates: tuple[date, ...]               # V, max(FYE_t, V) for t = 1..N, T
    cashflows: tuple[float, ...]
    xirr: float | None
    reinvested: float | None
    selected: float | None
    status: str


@dataclass(frozen=True)
class CaseResult:
    case: str
    projection: tuple[BankProjectionYear, ...]
    bv_path: tuple[float, ...]                     # clean-surplus BV_0 .. BV_N (per share)
    capital_retention_gap: float                   # max_t |BV_t / BVPS_t - 1|
    capital_retention_status: str
    terminal_status: str                           # PASS, or FAIL when g >= r (TV-1)
    ri: RIResult | None
    ddm: DDMResult | None
    jpb_multiple: float | None
    jpb_value_at_anchor: float | None
    value_at_valuation: dict[str, float | None]    # RI, DDM, JPB rolled to V; PEER_PB at the price date
    fair_value: float | None
    terminal_flag: str
    expected_return: ExpectedReturnResult | None


@dataclass(frozen=True)
class BankModelResult:
    cost_of_equity: float | None
    bv0: float | None
    latest_results_period_end: date | None
    financials_age_days: int | None
    anchor_age_days: int | None
    freshness_status: str
    roll_factor: float | None                      # (1 + r)^tau(A, V)
    dividends_compounded: float | None             # Σ DPS_d (1 + r)^tau(d, V), d in (A, V]
    dividends_paid: float | None                   # Σ DPS_d, d in (A, V]
    bridge: EquityBridge | None
    bridge_status: str
    interim_count: int
    interim_expected: int | None
    interim_coverage_status: str
    share_action_status: str
    peer: PeerRelativeResult
    weights_status: str
    cases: dict[str, CaseResult | None]
    fair_values: dict[str, float | None]
    tv_share_base: float | None
    terminal_flag_base: str
    coverage_status: str
    grid_rates: tuple[float, ...] = ()
    grid_growths: tuple[float, ...] = ()
    grid_roes: tuple[float, ...] = ()
    grid_rate_growth: tuple[tuple[float | None, ...], ...] = ()
    grid_rate_roe: tuple[tuple[float | None, ...], ...] = ()
    probability_weighted_return: float | None = None
    probability_status: str = ""
    market: dict[str, float | None] = field(default_factory=dict)


def _ready(*xs) -> bool:
    return all(x is not None for x in xs)


def _latest_results(a: date, v: date, interims: Sequence[InterimResult]) -> date:
    return max((i.period_end for i in interims if a < i.period_end <= v), default=a)


def _expected_return(case: CaseInputs, proj: Sequence[BankProjectionYear], bv_path: Sequence[float],
                     inp: BankModelInputs) -> ExpectedReturnResult:
    a, v, fyes = inp.anchor_date, inp.valuation_date, inp.fy_ends
    t_exit = add_months(v, EXIT_HORIZON_MONTHS)
    bounds = [a, *fyes]
    eps = [p.eps for p in proj]
    dps = [p.dps for p in proj]
    # Year t's dividend is paid at FYE_t (contract §2, §3.6). For the fiscal year containing V the
    # dividends that already went ex in (FYE_{t-1}, V] are netted off, so nothing is received twice.
    received = []
    for t, fye in enumerate(fyes):
        if v < fye <= t_exit:
            already = sum(x for _, x in dividends_in_window(inp.dividends, bounds[t], v))
            received.append(max(0.0, dps[t] - already))
        else:
            received.append(0.0)
    dates = (v, *[max(f, v) for f in fyes], t_exit)
    bvps_t = exit_value = None
    status = CR.PASS.value
    for k in range(len(fyes)):
        if bounds[k] <= t_exit < bounds[k + 1]:
            frac = (t_exit - bounds[k]).days / (bounds[k + 1] - bounds[k]).days
            bvps_t = bv_path[k] + eps[k] * frac
    if bvps_t is None:
        status = ER_HORIZON_FAIL
    elif case.exit_pb is None:
        status = ER_NO_EXIT_PB
    elif inp.price is None:
        status = ER_NO_PRICE
    else:
        exit_value = bank_exit_value(case.exit_pb, bvps_t)
    flows: tuple[float, ...] = ()
    irr = reinv = None
    if exit_value is not None:
        flows = (-inp.price, *received, exit_value)
        irr = xirr(list(flows), list(dates))
        if inp.reinvestment_rate is not None:
            divs = [(f, x) for f, x in zip(fyes, received) if x]
            reinv = reinvested_total_return(inp.price, v, t_exit, divs, exit_value, inp.reinvestment_rate)
    selected = reinv if inp.reinvestment_mode == REINVESTED else irr
    return ExpectedReturnResult(t_exit, bvps_t, exit_value, tuple(received), dates, flows, irr, reinv, selected,
                                status)


def _run_case(name: str, case: CaseInputs, inp: BankModelInputs, r: float | None, bv0: float | None,
              peer_value: float | None) -> CaseResult | None:
    if not _ready(case.drivers, inp.base, r, bv0, inp.anchor_date, inp.valuation_date):
        return None
    if inp.valuation_date < inp.anchor_date:
        return None
    if len(case.drivers) != len(inp.fy_ends):
        raise ValuationError(f"{name}: {len(case.drivers)} driver years for {len(inp.fy_ends)} forecast years")
    proj = tuple(project_bank(inp.base, case.drivers))
    eps, dps = [p.eps for p in proj], [p.dps for p in proj]
    bv_path = [bv0]
    for e, d in zip(eps, dps):
        bv_path.append(bv_path[-1] + e - d)
    gap = max(abs(bv / p.bvps - 1.0) for bv, p in zip(bv_path[1:], proj))
    retention = CR.PASS.value if gap <= inp.clean_surplus_tol else CR.FAIL.value
    a, v = inp.anchor_date, inp.valuation_date
    ri = ddm = None
    jpb_mult = jpb_value = None
    terminal_status = CR.PASS.value
    if _ready(case.terminal_roe, case.terminal_growth):
        try:
            ri = residual_income_value(bv0, eps, dps, r, case.terminal_roe, case.terminal_growth)
            jpb_mult = justified_pb(case.terminal_roe, r, case.terminal_growth)
            jpb_value = jpb_mult * bv0
            if case.terminal_payout is not None:
                ddm = dividend_discount_value(bv0, eps, dps, r, case.terminal_roe, case.terminal_payout,
                                              case.terminal_growth)
        except TerminalGrowthError:
            terminal_status = CR.FAIL.value
    else:
        terminal_status = CR.MISSING.value
    roll = (lambda x: None if x is None else roll_forward_value(x, a, v, r, inp.dividends))
    values = {"RI": roll(ri.value_at_anchor if ri else None), "DDM": roll(ddm.value_at_anchor if ddm else None),
              "JPB": roll(jpb_value), "PEER_PB": peer_value}
    try:
        fv = blend_fair_value(values, inp.weights)
    except ValuationError:
        fv = None
    if terminal_status == CR.FAIL.value:
        tflag = CR.FAIL.value
    elif ri is None:
        tflag = CR.MISSING.value
    else:
        tflag = terminal_flag(ri.terminal_value_share, inp.tv_share_warn)
    er = _expected_return(case, proj, bv_path, inp)
    return CaseResult(name, proj, tuple(bv_path), gap, retention, terminal_status, ri, ddm, jpb_mult, jpb_value,
                      values, fv, tflag, er)


def run_bank_model(inp: BankModelInputs) -> BankModelResult:
    a, v = inp.anchor_date, inp.valuation_date
    r = (cost_of_equity_capm(inp.risk_free, inp.beta, inp.equity_risk_premium)
         if _ready(inp.risk_free, inp.beta, inp.equity_risk_premium) else None)
    base = inp.base
    bv0 = base.equity * INR_PER_CRORE / base.diluted_shares if base is not None else None
    dates_ok = _ready(a, v) and a <= v
    # Freshness (§3.1b) needs only the dates, not the forecast
    rr = fin_age = anchor_age = None
    fresh = CR.MISSING.value
    if dates_ok:
        rr = _latest_results(a, v, inp.interims)
        fin_age, anchor_age = (v - rr).days, (v - a).days
        fresh = freshness_status(fin_age, anchor_age, inp.financials_stale_days, inp.anchor_max_age_days)
    # Roll-forward factors (§3.1), common to every method and case
    roll_factor = div_fv = paid = None
    if dates_ok and r is not None:
        window = dividends_in_window(inp.dividends, a, v)
        roll_factor = (1.0 + r) ** year_fraction(a, v)
        div_fv = sum(x * (1.0 + r) ** year_fraction(d, v) for d, x in window)
        paid = sum(x for _, x in window)
    # Interim coverage: every quarter in (A, R] should be reported, or the bridge undercounts EPS
    count = sum(1 for i in inp.interims if dates_ok and a < i.period_end <= rr)
    expected = (((rr.year - a.year) * 12 + rr.month - a.month) // 3) if dates_ok else None
    interim_cov = (CR.MISSING.value if expected is None else
                   CR.PASS.value if count == expected else CR.FAIL.value)
    share_actions = [d for d in inp.share_actions_after_anchor if dates_ok and a < d <= v]
    share_status = CR.FAIL.value if share_actions else CR.PASS.value
    peer = peer_relative_value(inp.peer_pb_median, bv0, inp.peer_n_valid, inp.peer_min_n)
    try:
        validate_weights(inp.weights)
        weights_status = CR.PASS.value
    except ValuationError:
        weights_status = CR.FAIL.value
    cases = {c: _run_case(c, inp.cases[c], inp, r, bv0, peer.value) for c in CASES}
    fvs = {c: (cases[c].fair_value if cases[c] else None) for c in CASES}
    base_case = cases.get("Base")
    bridge, bridge_status = None, CR.MISSING.value
    if base_case is not None:
        try:
            bridge = equity_bridge(bv0, a, list(zip(inp.fy_ends, [p.eps for p in base_case.projection])), v,
                                   inp.interims, inp.dividends, interim_dev_warn=inp.interim_dev_warn,
                                   financials_stale_days=inp.financials_stale_days,
                                   anchor_max_age_days=inp.anchor_max_age_days)
            bridge_status = CR.PASS.value
        except ValuationError:
            bridge_status = BRIDGE_HORIZON_FAIL
    tv_share = base_case.ri.terminal_value_share if base_case and base_case.ri else None
    tflag = base_case.terminal_flag if base_case else CR.MISSING.value
    coverage = (CoverageStatus.MODEL_VALUED.value if all(fvs[c] is not None for c in CASES)
                else CoverageStatus.UNVALUED.value)
    # Sensitivity grids on the Base case RI value at V (§10 TV-4/TV-5)
    grids: dict = {}
    if base_case is not None and base_case.ri is not None:
        bc, eps = inp.cases["Base"], [p.eps for p in base_case.projection]
        dps = [p.dps for p in base_case.projection]

        def ri_at_v(rate, roe, g):
            return roll_forward_value(residual_income_value(bv0, eps, dps, rate, roe, g).value_at_anchor,
                                      a, v, rate, inp.dividends)
        rates = tuple(r + s for s in RATE_STEPS)
        growths = tuple(bc.terminal_growth + s for s in GROWTH_STEPS)
        roes = tuple(bc.terminal_roe + s for s in ROE_STEPS)
        grids = dict(
            grid_rates=rates, grid_growths=growths, grid_roes=roes,
            grid_rate_growth=tuple(map(tuple, sensitivity_grid(lambda x, g: ri_at_v(x, bc.terminal_roe, g),
                                                               rates, growths))),
            grid_rate_roe=tuple(map(tuple, sensitivity_grid_2d(lambda x, roe: ri_at_v(x, roe, bc.terminal_growth),
                                                               rates, roes))))
    # Probability-weighted expected return: only when every probability is entered (§8)
    selected = {c: (cases[c].expected_return.selected if cases[c] and cases[c].expected_return else None)
                for c in CASES}
    try:
        pw = probability_weighted(selected, inp.probabilities)
        if any(p is None for p in inp.probabilities.values()):
            p_status = PROBABILITIES_NOT_ENTERED
        else:
            p_status = CR.PASS.value if pw is not None else CR.MISSING.value
    except ProbabilityError:
        pw, p_status = None, CR.FAIL.value
    price = inp.price
    base_fv = fvs["Base"]
    bv_v = bridge.bv_estimated_at_valuation if bridge else None
    market = {
        "market_cap_inr_cr": price * base.diluted_shares / INR_PER_CRORE if _ready(price, base) else None,
        "pb_on_bv_at_anchor": price / bv0 if _ready(price, bv0) else None,
        "pb_on_bv_at_valuation_estimate": price / bv_v if _ready(price, bv_v) else None,
        "implied_pb_at_valuation_estimate": base_fv / bv_v if _ready(base_fv, bv_v) else None,
        "trailing_pe_on_anchor_fy_eps": price / inp.eps_anchor_fy if _ready(price, inp.eps_anchor_fy) else None,
        "forward_pe_model_fy1": (price / base_case.projection[0].eps if _ready(price, base_case) else None),
        "upside_base": base_fv / price - 1.0 if _ready(price, base_fv) else None,
    }
    return BankModelResult(
        cost_of_equity=r, bv0=bv0, latest_results_period_end=rr, financials_age_days=fin_age,
        anchor_age_days=anchor_age, freshness_status=fresh, roll_factor=roll_factor,
        dividends_compounded=div_fv, dividends_paid=paid, bridge=bridge, bridge_status=bridge_status,
        interim_count=count, interim_expected=expected, interim_coverage_status=interim_cov,
        share_action_status=share_status, peer=peer, weights_status=weights_status, cases=cases,
        fair_values=fvs, tv_share_base=tv_share, terminal_flag_base=tflag, coverage_status=coverage,
        probability_weighted_return=pw, probability_status=p_status, market=market, **grids)
