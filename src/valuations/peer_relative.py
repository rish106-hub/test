"""Contract §3.5. The peer median comes from tbl_PeerSummary (04-charts); no code dependency."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeerRelativeResult:
    value: float | None   # None => UNVALUED by this method, never 0
    flag: str             # PASS | WARNING | MISSING


def peer_relative_value(peer_median_multiple: float | None, company_metric: float | None,
                        n_valid: int, min_peers: int = 3) -> PeerRelativeResult:
    raise NotImplementedError("02-valuation: contract §3.5")
