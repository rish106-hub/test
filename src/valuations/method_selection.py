"""R004 / R005 guard: which valuation methods may be the primary method for a business model."""
from __future__ import annotations

from src.common.enums import BusinessModel as B, ValuationMethod as M
from src.valuations.errors import MethodNotAllowedError

# Primary methods allowed per business model. Banks and lenders: equity-based intrinsic methods
# only (R004). An FCFF/WACC DCF treats deposits as operating liabilities and is never primary.
ALLOWED_PRIMARY: dict[str, frozenset[str]] = {
    B.BANK.value: frozenset({M.RESIDUAL_INCOME.value, M.DDM.value}),
    B.SMALL_FINANCE_BANK.value: frozenset({M.RESIDUAL_INCOME.value, M.DDM.value}),
    B.NBFC.value: frozenset({M.RESIDUAL_INCOME.value, M.DDM.value}),
    B.INSURANCE_HOLDCO.value: frozenset({M.INSURANCE_SOTP.value}),
    B.LIFE_INSURER.value: frozenset({M.INSURANCE_SOTP.value}),
    B.NON_FINANCIAL.value: frozenset({M.FCFF_DCF.value, M.FCFE.value, M.DDM.value, M.EV_MULTIPLE.value}),
    B.OTHER.value: frozenset({M.RESIDUAL_INCOME.value, M.DDM.value, M.FCFF_DCF.value, M.FCFE.value}),
}


def validate_method_for_business_model(business_model: str, primary_method: str) -> None:
    """Raise MethodNotAllowedError for disallowed pairs, e.g. FCFF DCF as a bank's primary method.

    'None' (no model, the security stays UNVALUED) is allowed for every business model (R009)."""
    bm, method = str(business_model), str(primary_method)
    if method not in M.values():
        raise MethodNotAllowedError(f"unknown valuation method {method!r}")
    if bm not in ALLOWED_PRIMARY:
        raise MethodNotAllowedError(f"unknown business model {bm!r}")
    if method == M.NONE.value:
        return
    if method not in ALLOWED_PRIMARY[bm]:
        rule = "R004" if bm in (B.BANK.value, B.SMALL_FINANCE_BANK.value) else "R005"
        raise MethodNotAllowedError(
            f"{method!r} is not an allowed primary method for {bm!r} ({rule}); allowed: {sorted(ALLOWED_PRIMARY[bm])}")
