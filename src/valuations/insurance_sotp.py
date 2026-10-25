"""Contract §4 Max Financial Services SOTP."""
from __future__ import annotations

from dataclasses import dataclass


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
    raise NotImplementedError("02-valuation: contract §4")


def sotp_value_per_share(inp: SOTPInputs) -> float:
    """INR per share at the anchor date (roll forward separately, contract §3.1)."""
    raise NotImplementedError("02-valuation: contract §4")
