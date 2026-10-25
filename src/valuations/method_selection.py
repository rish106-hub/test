"""R004 / R005 guard."""


def validate_method_for_business_model(business_model: str, primary_method: str) -> None:
    """Raise MethodNotAllowedError for disallowed pairs, e.g. FCFF DCF as a bank's primary method."""
    raise NotImplementedError("02-valuation: R004/R005")
