"""Contract §9 peer statistics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PeerStat:
    median: float | None    # None when n_valid == 0, never 0
    n_valid: int
    n_excluded: int         # members not counted: Included=FALSE, NM, missing, or the subject
    min: float | None
    max: float | None


def peer_statistic(members: Sequence[Mapping], metrics: Mapping[str, Mapping], exclude_security_id: str | None = None) -> PeerStat:
    """members: rows of tbl_PeerMembership for one Peer_Group_ID.
    metrics: {Security_ID: {"Value": float|None, "Is_Meaningful": bool}} for one Metric_ID."""
    raise NotImplementedError("04-charts: contract §9")
