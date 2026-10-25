"""Selects the inputs one bank VAL_* sheet uses, from ModelData (canonical CSVs or fixtures).

The sheet builder and the Python reference share this selection: which observation is the
anchor equity, which assumption row supplies Base NIM for FY2028, which dividends went ex after
the anchor. The builder turns each selected key (Observation_ID, Assumption_ID, Action_ID) into
a workbook formula; the reference reads the same row's value. The arithmetic on both sides is
independent (src/valuations/bank_model.py vs the sheet formulas).

Selection rules
* One entity, one accounting basis (contract §0). Default Standalone for banks.
* Revisions are append-only (D-016): an observation named in another row's
  Supersedes_Observation_ID is ignored. Point in time: Known_As_Of must be <= the valuation date.
* Anchor A: the latest fiscal-year-end COMMON_EQUITY observation on or before the valuation date.
* Balance-sheet (stock) metrics may be stored as Period_Type FY/Q or POINT at the period end.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from src.common.enums import BANK_MODELS, ValuationMethod
from src.common.units import fiscal_label, fiscal_year_end
from src.valuations import parameters as P
from src.valuations.bank_drivers import BankBaseYear, BankDriverYear
from src.valuations.bank_model import BankModelInputs, CaseInputs, add_months
from src.valuations.errors import MethodNotAllowedError
from src.valuations.method_selection import validate_method_for_business_model
from src.valuations.rollforward import InterimResult

ROOT = Path(__file__).resolve().parents[2]
INITIAL_SCOPE = ROOT / "data" / "reference" / "initial_scope.csv"

DEFAULT_BASIS = "Standalone"
PRIMARY_METHOD = ValuationMethod.RESIDUAL_INCOME.value
SECONDARY_METHODS = (ValuationMethod.DDM.value, ValuationMethod.JUSTIFIED_PB.value, ValuationMethod.PEER_PB.value)
N_HISTORY_FY = 10
N_HISTORY_Q = 20
DIVIDEND = "dividend"
SHARE_COUNT_ACTIONS = ("split", "bonus", "rights", "merger", "demerger", "buyback", "consolidation")

STOCK_METRICS = frozenset({
    "BANK_GROSS_ADVANCES", "BANK_NET_ADVANCES", "BANK_DEPOSITS", "BANK_CASA", "BANK_TERM_DEPOSITS",
    "BANK_INVESTMENTS", "TOTAL_ASSETS", "BANK_BORROWINGS", "COMMON_EQUITY", "DILUTED_SHARES", "BANK_NET_NPA",
    "BANK_GNPA_RATIO", "BANK_NNPA_RATIO", "BANK_PCR", "BANK_CAR", "BANK_CET1", "BANK_LEVERAGE_RATIO",
    "BANK_RESTRUCTURED", "BANK_CASA_RATIO", "BANK_LCR", "BANK_NSFR",
})
# Anchor-year inputs of the driver model (contract §3.6) plus FY EPS for the trailing P/E
ANCHOR_METRICS = ("COMMON_EQUITY", "DILUTED_SHARES", "BANK_NET_ADVANCES", "BANK_NON_II", "BANK_OPEX", "EPS_DILUTED")
# History block (spec <historical_data_requirements>): reported metrics looked up by Observation_ID
HISTORY_FY_METRICS = (
    "BANK_INT_INCOME", "BANK_INT_EXPENSE", "BANK_NON_II", "BANK_OPEX", "BANK_PROVISIONS", "NET_PROFIT_COMMON",
    "EPS_DILUTED", "DPS", "BANK_NET_ADVANCES", "BANK_INVESTMENTS", "BANK_DEPOSITS", "BANK_CASA", "TOTAL_ASSETS",
    "COMMON_EQUITY", "DILUTED_SHARES", "BANK_GNPA_RATIO", "BANK_NNPA_RATIO", "BANK_NIM", "BANK_CAR", "BANK_CET1",
)
HISTORY_Q_METRICS = (
    "BANK_INT_INCOME", "BANK_INT_EXPENSE", "BANK_NON_II", "BANK_OPEX", "BANK_PROVISIONS", "NET_PROFIT_COMMON",
    "EPS_DILUTED", "BANK_NET_ADVANCES", "BANK_DEPOSITS", "BANK_GNPA_RATIO", "BANK_NNPA_RATIO", "BANK_NIM",
)


def parse_date(raw) -> date | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, date):
        return raw if type(raw) is date else raw.date()
    return date.fromisoformat(str(raw)[:10])


def parse_float(raw) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def global_inputs(rows: Iterable[Mapping[str, str]]) -> dict[str, object]:
    """in_* name -> typed value (None when blank), from the global_inputs table."""
    out: dict[str, object] = {}
    for r in rows:
        raw, vt = (r.get("Value") or "").strip(), r.get("Value_Type", "")
        if raw == "":
            out[r["Name"]] = None
        elif vt == "date":
            out[r["Name"]] = date.fromisoformat(raw)
        elif vt == "int":
            out[r["Name"]] = int(float(raw))
        elif vt == "decimal":
            out[r["Name"]] = float(raw)
        else:
            out[r["Name"]] = raw
    return out


@dataclass(frozen=True)
class Observation:
    observation_id: str
    metric_id: str
    period_type: str
    period_end: date
    fiscal_label: str
    basis: str
    value: float
    unit: str
    source_id: str
    known_as_of: date | None


class ObservationIndex:
    """Current (non-superseded, known by `as_of`) observations of one entity on one basis."""

    def __init__(self, rows: Iterable[Mapping[str, str]], entity_id: str, basis: str, as_of: date | None):
        rows = [r for r in rows if r.get("Entity_ID") == entity_id]
        superseded = {r.get("Supersedes_Observation_ID") for r in rows if r.get("Supersedes_Observation_ID")}
        self.problems: list[str] = []
        self.by_key: dict[tuple[str, str, date], Observation] = {}
        for r in rows:
            if r.get("Accounting_Basis") != basis or r["Observation_ID"] in superseded:
                continue
            known = parse_date(r.get("Known_As_Of"))
            if as_of is not None and known is not None and known > as_of:
                continue
            value = parse_float(r.get("Value"))
            if value is None:
                self.problems.append(f"{r['Observation_ID']}: Value {r.get('Value')!r} is not a number")
                continue
            ob = Observation(r["Observation_ID"], r["Metric_ID"], r["Period_Type"], parse_date(r["Period_End"]),
                             r.get("Fiscal_Label", ""), basis, value, r.get("Unit", ""), r.get("Source_ID", ""), known)
            key = (ob.metric_id, ob.period_type, ob.period_end)
            prev = self.by_key.get(key)
            if prev is not None:
                keep = max(prev, ob, key=lambda o: (o.known_as_of or date.min, o.observation_id))
                self.problems.append(f"two current observations for {key}: {prev.observation_id}, "
                                     f"{ob.observation_id}; using {keep.observation_id}")
                ob = keep
            self.by_key[key] = ob

    def get(self, metric: str, period_end: date, annual: bool) -> Observation | None:
        types = ("FY",) if annual else ("Q",)
        if metric in STOCK_METRICS:
            types += ("POINT",)
        for t in types:
            ob = self.by_key.get((metric, t, period_end))
            if ob is not None:
                return ob
        return None

    def anchor_date(self, valuation_date: date | None) -> date | None:
        ends = [k[2] for k in self.by_key if k[0] == "COMMON_EQUITY" and k[1] in ("FY", "POINT")
                and fiscal_year_end(k[2]) == k[2] and (valuation_date is None or k[2] <= valuation_date)]
        return max(ends, default=None)

    def quarter_ends(self) -> list[date]:
        return sorted({k[2] for k in self.by_key if k[1] == "Q"})


@dataclass(frozen=True)
class DividendRow:
    action_id: str
    ex_date: date
    dps: float | None           # None when Ratio_or_Amount is not a number (shown as FAIL)
    raw: str
    source_id: str


@dataclass
class BankSpec:
    security_id: str
    entity_id: str
    company_name: str
    sheet: str
    business_model: str
    registry_method: str
    basis: str
    globals: dict[str, object]
    valuation_date: date | None
    price_date: date | None
    anchor_date: date | None
    fy_ends: tuple[date, ...]
    fy_labels: tuple[str, ...]
    anchor_obs: dict[str, Observation | None]
    interims: list[Observation]
    dividends: list[DividendRow]
    share_actions: list[tuple[str, str, date]]
    price: float | None
    peer_group_id: str | None
    peer_pb_median: float | None
    peer_n_valid: int
    security_inputs: dict[str, P.AssumptionRow | None]
    drivers: dict[tuple[str, str, int], P.AssumptionRow | None]     # (case, code, t) t = 1..N
    terminal: dict[tuple[str, str], P.AssumptionRow | None]         # (case, code)
    weights: dict[str, P.AssumptionRow | None]
    history_fy: list[tuple[str, date]]
    history_q: list[tuple[str, date]]
    history: dict[tuple[str, str], Observation | None]              # (metric, label)
    method_check: str
    problems: list[str] = field(default_factory=list)


def _shift(year: int, month: int, months: int) -> tuple[int, int]:
    y, m = divmod(month - 1 + months, 12)
    return year + y, m + 1


def _month_end(year: int, month: int) -> date:
    ny, nm = _shift(year, month, 1)
    return date(ny, nm, 1) - timedelta(days=1)


def _quarter_end_before(d: date) -> date:
    """Latest calendar quarter end (Mar, Jun, Sep, Dec) on or before d."""
    q_month = ((d.month - 1) // 3) * 3 + 3
    end = _month_end(d.year, q_month)
    return end if end <= d else _month_end(*_shift(d.year, q_month, -3))


def _peer_group(entity_id: str, security_id: str, peer_rows: list[Mapping[str, str]]) -> str | None:
    if INITIAL_SCOPE.exists():
        with INITIAL_SCOPE.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("Entity_ID") == entity_id and r.get("Peer_Group_ID"):
                    return r["Peer_Group_ID"]
    groups = [r["Peer_Group_ID"] for r in peer_rows
              if r.get("Exclude_Security_ID") == security_id and r.get("Metric_ID") == "PB"]
    return groups[0] if groups else None


def gather_bank_spec(data, registry_row: Mapping[str, str], basis: str = DEFAULT_BASIS) -> BankSpec:
    sid, eid = registry_row["Security_ID"], registry_row["Entity_ID"]
    g = global_inputs(data.rows("global_inputs"))
    v, price_date = g.get("in_Valuation_Date"), g.get("in_Price_Date")
    problems: list[str] = []
    bm, reg_method = registry_row.get("Business_Model", ""), registry_row.get("Primary_Valuation_Method") or ""
    validate_method_for_business_model(bm, PRIMARY_METHOD)          # R004: the template's primary method
    method_check = "PASS"
    if reg_method and reg_method != PRIMARY_METHOD:
        try:
            validate_method_for_business_model(bm, reg_method)
            method_check = f"PASS (registry lists {reg_method}; this template values by {PRIMARY_METHOD})"
        except MethodNotAllowedError as exc:
            method_check = f"FAIL: registry primary method not allowed ({exc}); model uses {PRIMARY_METHOD}"
            problems.append(method_check)
    idx = ObservationIndex(data.rows("raw_financials"), eid, basis, v)
    problems += idx.problems
    a = idx.anchor_date(v)
    fy_ends = tuple(add_months(a, 12 * t) for t in range(1, P.FORECAST_YEARS + 1)) if a else ()
    fy_labels = tuple(fiscal_label(d) for d in fy_ends)
    anchor_obs = {m: (idx.get(m, a, annual=True) if a else None) for m in ANCHOR_METRICS}
    last_fye = fy_ends[-1] if fy_ends else None
    interims = sorted((o for (m, t, pe), o in idx.by_key.items()
                       if m == "EPS_DILUTED" and t == "Q" and a and a < pe <= last_fye), key=lambda o: o.period_end)
    dividends, share_actions = [], []
    for r in data.rows("corporate_actions"):
        if r.get("Security_ID") != sid:
            continue
        ex = parse_date(r.get("Ex_Date"))
        kind = (r.get("Action_Type") or "").strip().lower()
        if not a or ex is None or ex <= a:
            continue
        if kind == DIVIDEND and ex <= last_fye:
            raw = (r.get("Ratio_or_Amount") or "").strip()
            dps = parse_float(raw)
            if dps is None:
                problems.append(f"{r['Action_ID']}: dividend amount {raw!r} is not a number")
            dividends.append(DividendRow(r["Action_ID"], ex, dps, raw, r.get("Source_ID", "")))
        elif kind in SHARE_COUNT_ACTIONS:
            share_actions.append((r["Action_ID"], r.get("Action_Type", ""), ex))
    dividends.sort(key=lambda d: (d.ex_date, d.action_id))
    price = None
    for r in data.rows("market_prices"):
        if r.get("Security_ID") == sid and price_date is not None and parse_date(r.get("Price_Date")) == price_date:
            price = parse_float(r.get("Close_INR"))
    peer_rows = data.rows("peer_summary")
    group = _peer_group(eid, sid, peer_rows)
    matches = [r for r in peer_rows if r.get("Peer_Group_ID") == group and r.get("Metric_ID") == "PB"
               and r.get("Exclude_Security_ID") == sid]
    median = parse_float(matches[0].get("Median")) if len(matches) == 1 else None
    n_valid = int(parse_float(matches[0].get("N_Valid")) or 0) if len(matches) == 1 else 0
    res = P.AssumptionResolver(P.parse_rows(data.rows("assumptions")))
    problems += [d for d in res.duplicates if f"'{sid}'" in d or "'GLOBAL'" in d]
    sec = {p.code: res.resolve(sid, P.ALL_CASES, p.code) for p in P.SECURITY_PARAMETERS}
    drivers = {(c, p.code, t + 1): res.resolve(sid, c, p.code, fy_labels[t] if fy_labels else P.ALL_PERIODS)
               for c in P.CASES for p in P.DRIVER_PARAMETERS for t in range(P.FORECAST_YEARS)}
    terminal = {(c, p.code): res.resolve(sid, c, p.code) for c in P.CASES for p in P.TERMINAL_PARAMETERS}
    weights = {p.code: res.resolve(sid, P.ALL_CASES, p.code) for p in P.WEIGHT_PARAMETERS}
    hist_fy = [(fiscal_label(d), d) for d in (add_months(a, -12 * k) for k in range(N_HISTORY_FY - 1, -1, -1))] if a else []
    q_last = (_quarter_end_before(v) if v else max(idx.quarter_ends(), default=None))
    hist_q = []
    if q_last:
        q = q_last
        for _ in range(N_HISTORY_Q):
            hist_q.append((fiscal_label(q, quarterly=True), q))
            q = _month_end(*_shift(q.year, q.month, -3))
        hist_q.reverse()
    history = {}
    for m in HISTORY_FY_METRICS:
        for label, d in hist_fy:
            history[(m, label)] = idx.get(m, d, annual=True)
    for m in HISTORY_Q_METRICS:
        for label, d in hist_q:
            history[(m, label)] = idx.get(m, d, annual=False)
    return BankSpec(
        security_id=sid, entity_id=eid, company_name=registry_row.get("Company_Name", ""),
        sheet=registry_row.get("Dedicated_Sheet", ""), business_model=bm, registry_method=reg_method, basis=basis,
        globals=g, valuation_date=v, price_date=price_date, anchor_date=a, fy_ends=fy_ends, fy_labels=fy_labels,
        anchor_obs=anchor_obs, interims=interims, dividends=dividends, share_actions=share_actions, price=price,
        peer_group_id=group, peer_pb_median=median, peer_n_valid=n_valid, security_inputs=sec, drivers=drivers,
        terminal=terminal, weights=weights, history_fy=hist_fy, history_q=hist_q, history=history,
        method_check=method_check, problems=problems)


def is_bank(registry_row: Mapping[str, str]) -> bool:
    return registry_row.get("Business_Model") in {b.value for b in BANK_MODELS}


def _val(row) -> float | None:
    return None if row is None else row.value


def model_inputs(spec: BankSpec, *, reinvestment_mode: str | None = None, reinvestment_rate: float | None = None,
                 probabilities: Mapping[str, float | None] | None = None) -> BankModelInputs:
    """The BankModelInputs a VAL_* sheet computes from (the reference side of D-020)."""
    g = spec.globals
    ao = {m: (o.value if o else None) for m, o in spec.anchor_obs.items()}
    iea0 = _val(spec.security_inputs.get("IEA_TO_ADV_ANCHOR"))
    base_vals = (ao["BANK_NET_ADVANCES"], iea0, ao["BANK_NON_II"], ao["BANK_OPEX"], ao["COMMON_EQUITY"],
                 ao["DILUTED_SHARES"])
    base = BankBaseYear(*base_vals) if all(x is not None for x in base_vals) else None
    cases = {}
    n = len(spec.fy_ends)
    for c in P.CASES:
        years = []
        for t in range(1, n + 1):
            vals = {p.code: _val(spec.drivers[(c, p.code, t)]) for p in P.DRIVER_PARAMETERS}
            required = [vals[p.code] for p in P.DRIVER_PARAMETERS if p.required]
            if any(x is None for x in required):
                years = None
                break
            years.append(BankDriverYear(vals["ADV_GROWTH"], vals["IEA_TO_ADV"], vals["NIM"], vals["NONII_GROWTH"],
                                        vals["OPEX_GROWTH"], vals["CREDIT_COST"], vals["TAX_RATE"], vals["PAYOUT"],
                                        vals["DILUTED_SHARES"]))
        term = {p.code: _val(spec.terminal[(c, p.code)]) for p in P.TERMINAL_PARAMETERS}
        cases[c] = CaseInputs(tuple(years) if years else None, term["TERMINAL_ROE"], term["TERMINAL_GROWTH"],
                              term["TERMINAL_PAYOUT"], term["EXIT_PB"])
    weights = {P.METHOD_OF_WEIGHT[code]: _val(row) for code, row in spec.weights.items()}
    return BankModelInputs(
        anchor_date=spec.anchor_date, valuation_date=spec.valuation_date, fy_ends=spec.fy_ends, base=base,
        risk_free=g.get("in_Risk_Free_Rate"), beta=_val(spec.security_inputs.get("BETA")),
        equity_risk_premium=g.get("in_Equity_Risk_Premium"), cases=cases, weights=weights,
        interims=tuple(InterimResult(o.period_end, o.value, o.source_id) for o in spec.interims),
        dividends=tuple((d.ex_date, d.dps) for d in spec.dividends if d.dps is not None),
        share_actions_after_anchor=tuple(d for _, _, d in spec.share_actions),
        price=spec.price, eps_anchor_fy=ao["EPS_DILUTED"], peer_pb_median=spec.peer_pb_median,
        peer_n_valid=spec.peer_n_valid,
        tv_share_warn=_num(g, "in_TV_Share_Warn", 0.75), interim_dev_warn=_num(g, "in_Interim_EPS_Dev_Warn", 0.15),
        financials_stale_days=int(_num(g, "in_Financials_Stale_Days", 135)),
        anchor_max_age_days=int(_num(g, "in_Anchor_Max_Age_Days", 425)), peer_min_n=int(_num(g, "in_Peer_Min_N", 3)),
        clean_surplus_tol=_num(g, "in_Clean_Surplus_Tol", 0.005),
        **({"reinvestment_mode": reinvestment_mode} if reinvestment_mode else {}),
        reinvestment_rate=reinvestment_rate,
        **({"probabilities": dict(probabilities)} if probabilities is not None else {}))


def _num(g: Mapping[str, object], name: str, default: float) -> float:
    """Governance thresholds (in_*). The defaults are the contract defaults (§3.1b, §10), used only
    if the global input is blank."""
    v = g.get(name)
    return default if v is None else float(v)
