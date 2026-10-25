"""Contract §3.6 bank driver model: drivers -> NII, PPOP, PAT, EPS, DPS, BV, ROE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BankBaseYear:
    """Anchor-year actuals, INR crore except shares (absolute count)."""
    advances: float
    iea_to_advances: float       # interest-earning assets / advances at the anchor
    non_interest_income: float
    operating_expenses: float
    equity: float                # common shareholders' equity
    diluted_shares: float


@dataclass(frozen=True)
class BankDriverYear:
    advance_growth: float
    iea_to_advances: float
    nim: float                   # on average interest-earning assets
    non_interest_income_growth: float
    opex_growth: float
    credit_cost: float           # provisions / average advances
    tax_rate: float
    payout_ratio: float
    diluted_shares: float | None = None   # None = unchanged


@dataclass(frozen=True)
class BankProjectionYear:
    advances: float
    nii: float
    non_interest_income: float
    opex: float
    ppop: float
    provisions: float
    pat: float
    eps: float     # INR
    dps: float     # INR
    equity: float
    bvps: float    # INR
    roe: float     # PAT / average equity


def project_bank(base: BankBaseYear, drivers: Sequence[BankDriverYear]) -> list[BankProjectionYear]:
    raise NotImplementedError("02-valuation: contract §3.6")
