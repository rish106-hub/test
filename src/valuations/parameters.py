"""Valuation assumption parameters (tbl_Assumptions[Parameter]) and how a sheet resolves them.

Every driver the bank template needs is declared here once, with its unit and the evidence
expected behind it (spec <persona>: separate facts, guidance, third-party forecasts and user
assumptions). A row in data/canonical/assumptions.csv supplies a value for
(Scope, Case, Parameter, Period). Resolution, most specific first:

    (Security_ID, case, period) -> (Security_ID, case, ALL) -> (Security_ID, All, period)
    -> (Security_ID, All, ALL) -> the same four with Scope = GLOBAL

An input with no matching row stays blank and is shown as MISSING; nothing is defaulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

CASES = ("Bear", "Base", "Bull")
ALL_CASES = "All"
ALL_PERIODS = "ALL"
GLOBAL_SCOPE = "GLOBAL"

# Explicit forecast years after the anchor. Six covers the five-year exit of contract §8 for a
# valuation date up to one year after the anchor (exit = V + 5y must fall inside the forecast).
FORECAST_YEARS = 6


@dataclass(frozen=True)
class Parameter:
    code: str
    label: str
    unit: str           # tbl_Assumptions[Unit]
    number: str         # styles.NUMBER_FORMATS key
    per_case: bool      # resolved separately for Bear / Base / Bull (D-008)
    per_year: bool      # resolved per forecast fiscal year (Period = FY label or ALL)
    required: bool
    evidence: str       # what a Rationale must cite


P = Parameter
# Security-level inputs (one value for all cases)
BETA = P("BETA", "Equity beta vs Nifty (CAPM)", "x", "multiple", False, False, True,
         "Regression on a stated index, window and frequency, or a cited source; else User assumption with reasoning")
IEA_TO_ADV_ANCHOR = P("IEA_TO_ADV_ANCHOR", "Interest-earning assets / advances at the anchor", "x", "multiple", False,
                      False, True, "Calculated from the anchor balance sheet (advances + investments + interest-earning "
                      "balances), with Source_IDs")
# Driver set per case and forecast year (contract §3.6)
ADV_GROWTH = P("ADV_GROWTH", "Advance growth", "decimal", "pct", True, True, True,
               "Reported history (HISTORICAL block) and cited management guidance")
IEA_TO_ADV = P("IEA_TO_ADV", "Interest-earning assets / advances", "x", "multiple", True, True, True,
               "Anchor ratio and the balance-sheet mix the case assumes")
NIM = P("NIM", "NIM on average interest-earning assets", "decimal", "pct", True, True, True,
        "Reported NIM history and guidance; must reconcile with NII / average IEA")
NONII_GROWTH = P("NONII_GROWTH", "Non-interest income growth", "decimal", "pct", True, True, True,
                 "Reported fee and other income history")
OPEX_GROWTH = P("OPEX_GROWTH", "Operating expense growth", "decimal", "pct", True, True, True,
                "Reported opex history and cost-to-income guidance")
CREDIT_COST = P("CREDIT_COST", "Credit cost (provisions / average advances)", "decimal", "pct", True, True, True,
                "Reported provisions history through a cycle; asset-quality trend")
TAX_RATE = P("TAX_RATE", "Effective tax rate", "decimal", "pct", True, True, True,
             "Reported effective tax rate and the statutory rate regime")
PAYOUT = P("PAYOUT", "Dividend payout ratio", "decimal", "pct", True, True, True,
           "Reported payout history and dividend policy")
DILUTED_SHARES = P("DILUTED_SHARES", "Diluted shares (blank = unchanged)", "count", "count", True, True, False,
                   "Only for a known issuance or buyback, with Source_ID")
# Terminal and exit per case
TERMINAL_ROE = P("TERMINAL_ROE", "Sustainable terminal RoE (ROE_T)", "decimal", "pct", True, False, True,
                 "Through-cycle RoE evidence; sector structure")
TERMINAL_GROWTH = P("TERMINAL_GROWTH", "Terminal growth g (must be < r_e)", "decimal", "pct", True, False, True,
                    "Long-run nominal growth evidence; g = ROE_T x (1 - payout_T) consistency")
TERMINAL_PAYOUT = P("TERMINAL_PAYOUT", "Terminal payout (DDM)", "decimal", "pct", True, False, True,
                    "Consistency with g = ROE_T x (1 - payout_T)")
EXIT_PB = P("EXIT_PB", "Exit P/B at V + 5y (expected return, contract §8)", "x", "multiple", True, False, False,
            "Explicit user assumption with reasoning; no automatic convergence to fair value")
# Blend weights (D-009). Usually Scope = GLOBAL.
W_RI = P("W_RI", "Blend weight: Residual Income", "decimal", "pct", False, False, True, "D-009 default 1 (primary)")
W_DDM = P("W_DDM", "Blend weight: Dividend Discount", "decimal", "pct", False, False, True, "D-009 default 0 (cross-check)")
W_JPB = P("W_JPB", "Blend weight: Justified P/B", "decimal", "pct", False, False, True, "D-009 default 0 (cross-check)")
W_PEER_PB = P("W_PEER_PB", "Blend weight: Peer-relative P/B", "decimal", "pct", False, False, True,
              "D-009 default 0 (cross-check until 04-charts delivers peers)")

SECURITY_PARAMETERS = (BETA, IEA_TO_ADV_ANCHOR)
DRIVER_PARAMETERS = (ADV_GROWTH, IEA_TO_ADV, NIM, NONII_GROWTH, OPEX_GROWTH, CREDIT_COST, TAX_RATE, PAYOUT,
                     DILUTED_SHARES)
TERMINAL_PARAMETERS = (TERMINAL_ROE, TERMINAL_GROWTH, TERMINAL_PAYOUT, EXIT_PB)
WEIGHT_PARAMETERS = (W_RI, W_DDM, W_JPB, W_PEER_PB)
ALL_PARAMETERS = SECURITY_PARAMETERS + DRIVER_PARAMETERS + TERMINAL_PARAMETERS + WEIGHT_PARAMETERS
BY_CODE = {p.code: p for p in ALL_PARAMETERS}
METHOD_OF_WEIGHT = {"W_RI": "RI", "W_DDM": "DDM", "W_JPB": "JPB", "W_PEER_PB": "PEER_PB"}


@dataclass(frozen=True)
class AssumptionRow:
    assumption_id: str
    scope: str
    case: str
    parameter: str
    period: str
    value: float
    unit: str
    source_type: str
    source_id: str
    rationale: str


def parse_rows(rows: Iterable[Mapping[str, str]]) -> list[AssumptionRow]:
    out = []
    for r in rows:
        raw = (r.get("Value") or "").strip()
        if raw == "":
            continue   # a blank value is "not yet set" and resolves to MISSING
        out.append(AssumptionRow(r["Assumption_ID"], r["Scope"], r["Case"], r["Parameter"], r["Period"],
                                 float(raw), r.get("Unit", ""), r.get("Assumption_Source_Type", ""),
                                 r.get("Source_ID", ""), r.get("Rationale", "")))
    return out


class AssumptionResolver:
    """Resolves (security, case, parameter, period) to one AssumptionRow, most specific first."""

    def __init__(self, rows: Iterable[AssumptionRow]):
        self.index: dict[tuple[str, str, str, str], AssumptionRow] = {}
        self.duplicates: list[str] = []
        for row in rows:
            key = (row.scope, row.case, row.parameter, row.period)
            if key in self.index:
                self.duplicates.append(f"duplicate assumption {key}: {self.index[key].assumption_id} "
                                       f"and {row.assumption_id} (first one used)")
                continue
            self.index[key] = row

    def resolve(self, security_id: str, case: str, parameter: str, period: str = ALL_PERIODS) -> AssumptionRow | None:
        cases = (case, ALL_CASES) if case != ALL_CASES else (ALL_CASES,)
        periods = (period, ALL_PERIODS) if period != ALL_PERIODS else (ALL_PERIODS,)
        for scope in (security_id, GLOBAL_SCOPE):
            for c in cases:
                for p in periods:
                    row = self.index.get((scope, c, parameter, p))
                    if row is not None:
                        return row
        return None
