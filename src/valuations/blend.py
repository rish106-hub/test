"""Contract §3.8."""
from __future__ import annotations

from typing import Mapping


def blend_fair_value(values: Mapping[str, float | None], weights: Mapping[str, float]) -> float | None:
    """Sum w_m * V_m. Weights must be >= 0 and sum to 1 (else ValuationError). A method with
    positive weight and value None makes the blend None (unvalued), never a silent re-weighting."""
    raise NotImplementedError("02-valuation: contract §3.8")
