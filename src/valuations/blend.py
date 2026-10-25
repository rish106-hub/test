"""Contract §3.8."""
from __future__ import annotations

from typing import Mapping

from src.valuations.errors import ValuationError

WEIGHT_SUM_TOL = 1e-9


def validate_weights(weights: Mapping[str, float | None]) -> None:
    if not weights or any(w is None or w < 0 for w in weights.values()):
        raise ValuationError(f"blend weights must be entered and >= 0: {dict(weights)}")
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOL:
        raise ValuationError(f"blend weights must sum to 1, got {total}")


def blend_fair_value(values: Mapping[str, float | None], weights: Mapping[str, float]) -> float | None:
    """Sum w_m * V_m. Weights must be >= 0 and sum to 1 (else ValuationError). A method with
    positive weight and value None makes the blend None (unvalued), never a silent re-weighting."""
    validate_weights(weights)
    total = 0.0
    for method, w in weights.items():
        if w == 0:
            continue
        v = values.get(method)
        if v is None:
            return None
        total += w * v
    return total
