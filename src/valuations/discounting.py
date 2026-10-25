"""Contract §2."""


def cost_of_equity_capm(risk_free: float, beta: float, equity_risk_premium: float) -> float:
    raise NotImplementedError("02-valuation: contract §2")


def discount_factor(rate: float, tau_years: float) -> float:
    """(1 + rate) ** -tau, annual effective rate, end-of-period."""
    raise NotImplementedError("02-valuation: contract §2")
