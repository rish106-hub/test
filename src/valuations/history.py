"""History block of a bank VAL_* sheet: reported rows and calculated rows (spec
<historical_data_requirements>, <bank_risk_and_capital>).

Each calculated row is defined once, with its Excel formula and its Python reference, so the
sheet-vs-reference test covers history as well as valuation. Calculated rows with a Metric_ID
from the metric dictionary feed tbl_HistoricalMetrics; rows marked display-only are consistency
displays on the VAL sheet (contract §3.6: deposit growth, yields and funding costs are shown, not
driven) and use labels, not Metric_IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from src.common.units import INR_PER_CRORE
from src.valuations.inputs import HISTORY_FY_METRICS, HISTORY_Q_METRICS, BankSpec

UNITS = {
    "BANK_INT_INCOME": ("INR_Cr", "inr_cr"), "BANK_INT_EXPENSE": ("INR_Cr", "inr_cr"),
    "BANK_NON_II": ("INR_Cr", "inr_cr"), "BANK_OPEX": ("INR_Cr", "inr_cr"), "BANK_PROVISIONS": ("INR_Cr", "inr_cr"),
    "NET_PROFIT_COMMON": ("INR_Cr", "inr_cr"), "EPS_DILUTED": ("INR", "inr"), "DPS": ("INR", "inr"),
    "BANK_NET_ADVANCES": ("INR_Cr", "inr_cr"), "BANK_INVESTMENTS": ("INR_Cr", "inr_cr"),
    "BANK_DEPOSITS": ("INR_Cr", "inr_cr"), "BANK_CASA": ("INR_Cr", "inr_cr"), "TOTAL_ASSETS": ("INR_Cr", "inr_cr"),
    "COMMON_EQUITY": ("INR_Cr", "inr_cr"), "DILUTED_SHARES": ("count", "count"),
    "BANK_GNPA_RATIO": ("decimal", "pct"), "BANK_NNPA_RATIO": ("decimal", "pct"), "BANK_NIM": ("decimal", "pct"),
    "BANK_CAR": ("decimal", "pct"), "BANK_CET1": ("decimal", "pct"),
}
LABELS = {
    "BANK_INT_INCOME": "Interest income", "BANK_INT_EXPENSE": "Interest expense",
    "BANK_NON_II": "Non-interest income", "BANK_OPEX": "Operating expenses",
    "BANK_PROVISIONS": "Provisions and contingencies (ex tax)", "NET_PROFIT_COMMON": "Net profit to common",
    "EPS_DILUTED": "Diluted EPS", "DPS": "Dividend per share", "BANK_NET_ADVANCES": "Net advances",
    "BANK_INVESTMENTS": "Investments", "BANK_DEPOSITS": "Deposits", "BANK_CASA": "CASA balances",
    "TOTAL_ASSETS": "Total assets", "COMMON_EQUITY": "Common equity", "DILUTED_SHARES": "Diluted shares",
    "BANK_GNPA_RATIO": "Gross NPA ratio", "BANK_NNPA_RATIO": "Net NPA ratio", "BANK_NIM": "NIM (as reported)",
    "BANK_CAR": "Capital adequacy ratio", "BANK_CET1": "CET1 ratio",
}


@dataclass(frozen=True)
class Calc:
    key: str                         # Metric_ID (exported) or a display key
    label: str
    unit: str
    number: str
    inputs: tuple[tuple[str, int], ...]   # (metric or calc key, lag in periods)
    py: Callable[..., float]
    xl: Callable[..., str]
    den: Callable[..., float] | None = None       # denominator that must be non-zero
    xl_den: Callable[..., str] | None = None
    export: bool = True              # feeds tbl_HistoricalMetrics (Metric_ID from the dictionary)


_C = INR_PER_CRORE   # crore -> rupees, written into formulas by the generator (WI-5)
FY_CALCS = (
    Calc("BANK_NII", "Net interest income (calc.)", "INR_Cr", "inr_cr",
         (("BANK_INT_INCOME", 0), ("BANK_INT_EXPENSE", 0)), lambda a, b: a - b, lambda a, b: f"{a}-{b}"),
    Calc("BANK_PPOP", "Pre-provision operating profit (calc.)", "INR_Cr", "inr_cr",
         (("BANK_NII", 0), ("BANK_NON_II", 0), ("BANK_OPEX", 0)), lambda a, b, c: a + b - c,
         lambda a, b, c: f"{a}+{b}-{c}"),
    Calc("BVPS", "Book value per share (calc.)", "INR", "inr", (("COMMON_EQUITY", 0), ("DILUTED_SHARES", 0)),
         lambda a, b: a * _C / b, lambda a, b: f"{a}*{_C}/{b}", lambda a, b: b, lambda a, b: b),
    Calc("ROE", "RoE: profit / average equity (calc.)", "decimal", "pct",
         (("NET_PROFIT_COMMON", 0), ("COMMON_EQUITY", 1), ("COMMON_EQUITY", 0)),
         lambda a, b, c: a / ((b + c) / 2), lambda a, b, c: f"{a}/(({b}+{c})/2)", lambda a, b, c: b + c,
         lambda a, b, c: f"({b}+{c})"),
    Calc("ROA", "RoA: profit / average total assets (calc.)", "decimal", "pct",
         (("NET_PROFIT_COMMON", 0), ("TOTAL_ASSETS", 1), ("TOTAL_ASSETS", 0)),
         lambda a, b, c: a / ((b + c) / 2), lambda a, b, c: f"{a}/(({b}+{c})/2)", lambda a, b, c: b + c,
         lambda a, b, c: f"({b}+{c})"),
    Calc("BANK_COST_INCOME", "Cost-to-income (calc.)", "decimal", "pct",
         (("BANK_OPEX", 0), ("BANK_NII", 0), ("BANK_NON_II", 0)), lambda a, b, c: a / (b + c),
         lambda a, b, c: f"{a}/({b}+{c})", lambda a, b, c: b + c, lambda a, b, c: f"({b}+{c})"),
    Calc("BANK_CREDIT_COST", "Provisions / average net advances (credit-cost proxy, calc.)", "decimal", "pct",
         (("BANK_PROVISIONS", 0), ("BANK_NET_ADVANCES", 1), ("BANK_NET_ADVANCES", 0)),
         lambda a, b, c: a / ((b + c) / 2), lambda a, b, c: f"{a}/(({b}+{c})/2)", lambda a, b, c: b + c,
         lambda a, b, c: f"({b}+{c})"),
    Calc("BANK_CASA_RATIO", "CASA ratio (calc.)", "decimal", "pct", (("BANK_CASA", 0), ("BANK_DEPOSITS", 0)),
         lambda a, b: a / b, lambda a, b: f"{a}/{b}", lambda a, b: b, lambda a, b: b),
    # Consistency displays (contract §3.6, charts B005/B006): not drivers, not exported.
    Calc("ADV_GROWTH_YOY", "Advance growth YoY (display)", "decimal", "pct",
         (("BANK_NET_ADVANCES", 0), ("BANK_NET_ADVANCES", 1)), lambda a, b: a / b - 1, lambda a, b: f"{a}/{b}-1",
         lambda a, b: b, lambda a, b: b, export=False),
    Calc("DEPOSIT_GROWTH_YOY", "Deposit growth YoY (display)", "decimal", "pct",
         (("BANK_DEPOSITS", 0), ("BANK_DEPOSITS", 1)), lambda a, b: a / b - 1, lambda a, b: f"{a}/{b}-1",
         lambda a, b: b, lambda a, b: b, export=False),
    Calc("IEA_PROXY_TO_ADV", "(Advances + investments) / advances (IEA proxy, display)", "x", "multiple",
         (("BANK_NET_ADVANCES", 0), ("BANK_INVESTMENTS", 0)), lambda a, b: (a + b) / a,
         lambda a, b: f"({a}+{b})/{a}", lambda a, b: a, lambda a, b: a, export=False),
    Calc("NII_ON_IEA_PROXY", "NII / avg (advances + investments) (NIM proxy, display)", "decimal", "pct",
         (("BANK_NII", 0), ("BANK_NET_ADVANCES", 1), ("BANK_INVESTMENTS", 1), ("BANK_NET_ADVANCES", 0),
          ("BANK_INVESTMENTS", 0)), lambda a, b, c, d, e: a / ((b + c + d + e) / 2),
         lambda a, b, c, d, e: f"{a}/(({b}+{c}+{d}+{e})/2)", lambda a, b, c, d, e: b + c + d + e,
         lambda a, b, c, d, e: f"({b}+{c}+{d}+{e})", export=False),
    Calc("YIELD_ON_IEA_PROXY", "Interest income / avg (advances + investments) (yield proxy, display)", "decimal",
         "pct", (("BANK_INT_INCOME", 0), ("BANK_NET_ADVANCES", 1), ("BANK_INVESTMENTS", 1), ("BANK_NET_ADVANCES", 0),
                 ("BANK_INVESTMENTS", 0)), lambda a, b, c, d, e: a / ((b + c + d + e) / 2),
         lambda a, b, c, d, e: f"{a}/(({b}+{c}+{d}+{e})/2)", lambda a, b, c, d, e: b + c + d + e,
         lambda a, b, c, d, e: f"({b}+{c}+{d}+{e})", export=False),
    Calc("COST_OF_FUNDS_PROXY", "Interest expense / avg deposits (cost-of-deposits proxy, display)", "decimal", "pct",
         (("BANK_INT_EXPENSE", 0), ("BANK_DEPOSITS", 1), ("BANK_DEPOSITS", 0)), lambda a, b, c: a / ((b + c) / 2),
         lambda a, b, c: f"{a}/(({b}+{c})/2)", lambda a, b, c: b + c, lambda a, b, c: f"({b}+{c})", export=False),
)
Q_CALCS = FY_CALCS[:2]   # NII and PPOP: discrete-quarter flows. Ratios need annualising and are left to FY.


def _calc_values(calcs: Sequence[Calc], labels: Sequence[str], values: dict[tuple[str, str], float | None]):
    for c in calcs:
        for i, label in enumerate(labels):
            args = []
            for metric, lag in c.inputs:
                j = i - lag
                args.append(values.get((metric, labels[j])) if j >= 0 else None)
            v = None
            if all(a is not None for a in args) and (c.den is None or c.den(*args) != 0):
                v = c.py(*args)
            values[(c.key, label)] = v


def history_values(spec: BankSpec) -> dict[str, dict[tuple[str, str], float | None]]:
    """Python reference for the history block: {'FY': {(metric, label): value}, 'Q': {...}}."""
    out = {}
    for block, metrics, periods, calcs in (("FY", HISTORY_FY_METRICS, spec.history_fy, FY_CALCS),
                                           ("Q", HISTORY_Q_METRICS, spec.history_q, Q_CALCS)):
        labels = [lab for lab, _ in periods]
        vals: dict[tuple[str, str], float | None] = {}
        for m in metrics:
            for lab in labels:
                ob = spec.history.get((m, lab))
                vals[(m, lab)] = ob.value if ob else None
        _calc_values(calcs, labels, vals)
        out[block] = vals
    return out


def excel_calc(c: Calc, refs: Sequence[str]) -> str:
    """=IF(all inputs numeric [and denominator non-zero], formula, "")."""
    n = len(refs)
    cond = f"COUNT({','.join(refs)})={n}"
    body = c.xl(*refs)
    if c.xl_den is not None:
        body = f'IF({c.xl_den(*refs)}=0,"",{body})'
    return f'=IF({cond},{body},"")'


def metric_units(metric: str) -> tuple[str, str]:
    return UNITS[metric]


def metric_label(metric: str) -> str:
    return LABELS[metric]


def calcs_by_key(calcs: Sequence[Calc]) -> Mapping[str, Calc]:
    return {c.key: c for c in calcs}
