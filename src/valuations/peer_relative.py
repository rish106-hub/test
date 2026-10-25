"""Contract §3.5. The peer median comes from tbl_PeerSummary (04-charts); no code dependency."""
from __future__ import annotations

from dataclasses import dataclass

from src.common.enums import CheckResult


@dataclass(frozen=True)
class PeerRelativeResult:
    value: float | None   # None => UNVALUED by this method, never 0
    flag: str             # PASS | WARNING | MISSING


def peer_relative_value(peer_median_multiple: float | None, company_metric: float | None,
                        n_valid: int, min_peers: int = 3) -> PeerRelativeResult:
    """V = peer median multiple x company metric. N_Valid = 0 (or a missing input) is MISSING
    and blank, never 0; N_Valid below min_peers is WARNING."""
    if not n_valid or peer_median_multiple is None or company_metric is None:
        return PeerRelativeResult(None, CheckResult.MISSING.value)
    flag = CheckResult.WARNING.value if n_valid < min_peers else CheckResult.PASS.value
    return PeerRelativeResult(peer_median_multiple * company_metric, flag)
