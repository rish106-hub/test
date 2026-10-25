"""Contract §4 Max Financial Services SOTP."""
from __future__ import annotations

from dataclasses import dataclass

from src.common.units import INR_PER_CRORE
from src.valuations.errors import DoubleCountingError, ValuationError


@dataclass(frozen=True)
class SOTPInputs:
    """INR crore except shares (absolute count) and decimals."""
    embedded_value: float
    stake_pct: float
    parent_cash: float
    parent_debt: float
    other_parent_net_assets: float
    diluted_parent_shares: float
    holdco_discount_pct: float = 0.0
    vnb: float | None = None             # Method A
    vnb_multiple: float | None = None    # Method A
    target_p_ev: float | None = None     # Method B


def appraisal_value(inp: SOTPInputs) -> float:
    """Raises DoubleCountingError if both methods (or neither) are specified."""
    method_a = inp.vnb is not None or inp.vnb_multiple is not None
    method_b = inp.target_p_ev is not None
    if method_a and method_b:
        raise DoubleCountingError("both Method A (EV + VNB x multiple) and Method B (EV x P/EV) given: "
                                  "a P/EV multiple already prices future new business (contract §4)")
    if not method_a and not method_b:
        raise DoubleCountingError("neither Method A nor Method B specified (contract §4: exactly one per case)")
    if method_b:
        return inp.embedded_value * inp.target_p_ev
    if inp.vnb is None or inp.vnb_multiple is None:
        raise ValuationError("Method A needs both VNB and the VNB multiple")
    return inp.embedded_value + inp.vnb * inp.vnb_multiple


def sotp_value_per_share(inp: SOTPInputs) -> float:
    """INR per share at the anchor date (roll forward separately, contract §3.1)."""
    if not 0.0 <= inp.stake_pct <= 1.0:
        raise ValuationError(f"stake must be a decimal in [0, 1], got {inp.stake_pct}")
    if not 0.0 <= inp.holdco_discount_pct < 1.0:
        raise ValuationError(f"holdco discount must be in [0, 1), got {inp.holdco_discount_pct}")
    if inp.diluted_parent_shares <= 0:
        raise ValuationError("diluted parent shares must be positive")
    stake_value = inp.stake_pct * appraisal_value(inp) * (1.0 - inp.holdco_discount_pct)
    equity = stake_value + inp.parent_cash - inp.parent_debt + inp.other_parent_net_assets
    return equity * INR_PER_CRORE / inp.diluted_parent_shares
