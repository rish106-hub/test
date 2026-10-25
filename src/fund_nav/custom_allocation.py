"""Contract §7.6 custom allocation inputs (hypothetical only, R011)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AllocationLine:
    line_id: str
    sector: str
    security_id: str | None          # None => explicit cash / unallocated line
    sector_weight: float
    constituent_weight: float


def effective_weights(lines: Sequence[AllocationLine]) -> dict[str, float]:
    """{security_id or 'CASH': sector_weight * constituent_weight}."""
    raise NotImplementedError("03-nav: contract §7.6")


def validate_allocation(lines: Sequence[AllocationLine], tol: float = 1e-6) -> list[str]:
    """Empty list = valid. Checks sector sum + explicit cash = 1, constituent sums = 1 per sector,
    no duplicate Security_ID, no negative weights."""
    raise NotImplementedError("03-nav: contract §7.6")
