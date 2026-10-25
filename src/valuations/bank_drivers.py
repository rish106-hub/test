"""Contract §3.6 bank driver model: drivers -> NII, PPOP, PAT, EPS, DPS, BV, ROE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.common.units import INR_PER_CRORE
from src.valuations.errors import ValuationError


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
    iea: float = 0.0             # interest-earning assets, INR crore (period end)
    diluted_shares: float = 0.0  # absolute count used for EPS/DPS/BVPS of the year


def project_bank(base: BankBaseYear, drivers: Sequence[BankDriverYear]) -> list[BankProjectionYear]:
    """Project years t = 1..N from the anchor-year actuals (contract §3.6). Amounts in INR crore;
    EPS, DPS and BVPS in INR (crore x 1e7 / shares)."""
    if base.diluted_shares <= 0:
        raise ValuationError("diluted shares at the anchor must be positive")
    adv, iea = base.advances, base.advances * base.iea_to_advances
    nonii, opex, equity, shares = base.non_interest_income, base.operating_expenses, base.equity, base.diluted_shares
    out: list[BankProjectionYear] = []
    for d in drivers:
        adv_t = adv * (1.0 + d.advance_growth)
        iea_t = adv_t * d.iea_to_advances
        nii = d.nim * (iea + iea_t) / 2.0
        nonii_t = nonii * (1.0 + d.non_interest_income_growth)
        opex_t = opex * (1.0 + d.opex_growth)
        ppop = nii + nonii_t - opex_t
        prov = d.credit_cost * (adv + adv_t) / 2.0
        pat = (ppop - prov) * (1.0 - d.tax_rate)
        shares_t = shares if d.diluted_shares is None else d.diluted_shares
        if shares_t <= 0:
            raise ValuationError("diluted shares must be positive")
        eps = pat * INR_PER_CRORE / shares_t
        dps = eps * d.payout_ratio
        equity_t = equity + pat - dps * shares_t / INR_PER_CRORE   # dividend of year t deducted in year t
        bvps = equity_t * INR_PER_CRORE / shares_t
        roe = pat / ((equity + equity_t) / 2.0)
        out.append(BankProjectionYear(adv_t, nii, nonii_t, opex_t, ppop, prov, pat, eps, dps, equity_t, bvps, roe,
                                      iea_t, shares_t))
        adv, iea, nonii, opex, equity, shares = adv_t, iea_t, nonii_t, opex_t, equity_t, shares_t
    return out
