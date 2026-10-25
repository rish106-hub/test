"""Contract §2: cost of equity and discounting."""
from __future__ import annotations

import math

from src.valuations.errors import ValuationError


def _finite(name: str, x: float) -> float:
    if x is None or not math.isfinite(x):
        raise ValuationError(f"{name} must be a finite number, got {x!r}")
    return float(x)


def cost_of_equity_capm(risk_free: float, beta: float, equity_risk_premium: float) -> float:
    """r_e = Rf + beta x ERP (annual effective, decimal)."""
    return _finite("risk_free", risk_free) + _finite("beta", beta) * _finite("equity_risk_premium", equity_risk_premium)


def discount_factor(rate: float, tau_years: float) -> float:
    """(1 + rate) ** -tau, annual effective rate, end-of-period."""
    rate = _finite("rate", rate)
    if rate <= -1.0:
        raise ValuationError(f"rate must be > -100%, got {rate}")
    return (1.0 + rate) ** -_finite("tau_years", tau_years)
