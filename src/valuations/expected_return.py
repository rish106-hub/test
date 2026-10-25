"""Contract §8 expected five-year return."""
from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence


def xirr(cashflows: Sequence[float], dates: Sequence[date]) -> float:
    """Excel XIRR convention: sum CF_i / (1 + r) ** ((d_i - d_0).days / 365) = 0."""
    raise NotImplementedError("02-valuation: contract §8")


def bank_exit_value(exit_pb: float, bvps_at_exit: float) -> float:
    raise NotImplementedError("02-valuation: contract §8")


def probability_weighted(values: Mapping[str, float | None], probabilities: Mapping[str, float | None]) -> float | None:
    """None if any probability is blank; ProbabilityError if entered and sum != 1 (1e-9)."""
    raise NotImplementedError("02-valuation: contract §8")
