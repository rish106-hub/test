"""Contract §7.6 custom allocation inputs (hypothetical only, R011)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

CASH_KEY = "CASH"


@dataclass(frozen=True)
class AllocationLine:
    line_id: str
    sector: str
    security_id: str | None          # None => explicit cash / unallocated line
    sector_weight: float
    constituent_weight: float


def effective_weights(lines: Sequence[AllocationLine]) -> dict[str, float]:
    """{security_id or 'CASH': sector_weight * constituent_weight}."""
    out: dict[str, float] = {}
    for l in lines:
        key = l.security_id if l.security_id is not None else CASH_KEY
        out[key] = out.get(key, 0.0) + l.sector_weight * l.constituent_weight
    return out


def validate_allocation(lines: Sequence[AllocationLine], tol: float = 1e-6) -> list[str]:
    """Empty list = valid. Checks sector sum + explicit cash = 1, constituent sums = 1 per sector,
    no duplicate Security_ID, no negative weights.

    A sector's weight is stated on each of its lines, so the lines of one sector must agree. The explicit
    cash / unallocated weight is the effective weight of the lines with no Security_ID.
    """
    problems: list[str] = []
    for l in lines:
        if l.sector_weight < 0 or l.constituent_weight < 0:
            problems.append(f"{l.line_id}: weights must be >= 0")
    seen: dict[str, str] = {}
    for l in lines:
        if l.security_id is not None:
            if l.security_id in seen:
                problems.append(f"{l.line_id}: duplicate Security_ID {l.security_id} (also on {seen[l.security_id]})")
            seen.setdefault(l.security_id, l.line_id)

    sectors: dict[str, list[AllocationLine]] = {}
    for l in lines:
        sectors.setdefault(l.sector, []).append(l)
    sector_weight_sum = 0.0
    for sector, group in sectors.items():
        weights = {g.sector_weight for g in group}
        if len(weights) > 1:
            problems.append(f"sector {sector}: lines state different sector weights {sorted(weights)}")
        sw = group[0].sector_weight
        if sw != 0 and abs(sum(g.constituent_weight for g in group) - 1) > tol:
            problems.append(f"sector {sector}: constituent weights sum to "
                            f"{sum(g.constituent_weight for g in group):.6g}, not 1")
        if any(g.security_id is not None for g in group):
            sector_weight_sum += sw
    cash = sum(l.sector_weight * l.constituent_weight for l in lines if l.security_id is None)
    if abs(sector_weight_sum + cash - 1) > tol:
        problems.append(f"sector weights ({sector_weight_sum:.6g}) + explicit cash ({cash:.6g}) must equal 1")
    return problems
