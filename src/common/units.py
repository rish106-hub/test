"""Unit, date and fiscal-period conventions (contract §0)."""
from __future__ import annotations

from datetime import date

INR_PER_CRORE = 10_000_000
LAKH_PER_CRORE = 100
DAYS_PER_YEAR_DISCOUNT = 365.25  # discounting and roll-forward
DAYS_PER_YEAR_XIRR = 365         # Excel XIRR convention


def lakh_to_crore(value_lakh: float) -> float:
    return value_lakh / LAKH_PER_CRORE


def market_value_inr_cr(quantity: float, price_inr: float) -> float:
    """Quantity (absolute count) x per-share INR price -> INR crore."""
    return quantity * price_inr / INR_PER_CRORE


def per_share_from_crore(amount_inr_cr: float, shares: float) -> float:
    """INR crore aggregate / absolute share count -> INR per share."""
    return amount_inr_cr * INR_PER_CRORE / shares


def year_fraction(start: date, end: date) -> float:
    """tau for discounting: days / 365.25."""
    return (end - start).days / DAYS_PER_YEAR_DISCOUNT


def fiscal_year_end(d: date) -> date:
    """Indian fiscal year end (31 March) of the fiscal year containing d."""
    return date(d.year if d.month <= 3 else d.year + 1, 3, 31)


def fiscal_label(period_end: date, quarterly: bool = False) -> str:
    """FY2026 = Apr-2025..Mar-2026; Q1FY2027 ends 2026-06-30."""
    fy = fiscal_year_end(period_end).year
    if not quarterly:
        return f"FY{fy}"
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(period_end.month)
    if q is None:
        raise ValueError(f"{period_end} is not a fiscal quarter end")
    return f"Q{q}FY{fy}"
