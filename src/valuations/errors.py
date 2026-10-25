class ValuationError(ValueError):
    """Base class: the inputs cannot produce a valid valuation."""


class TerminalGrowthError(ValuationError):
    """Gordon terminal value requested with g >= r (contract §10 TV-1)."""


class DoubleCountingError(ValuationError):
    """Insurance SOTP given both an EV multiple and a VNB multiple (contract §4)."""


class MethodNotAllowedError(ValuationError):
    """Method inappropriate for the business model, e.g. FCFF DCF as a bank's primary (R004/R005)."""


class ProbabilityError(ValuationError):
    """Scenario probabilities entered but not summing to 1 (contract §8)."""
