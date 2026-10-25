"""Contract §7.8."""
from typing import Mapping


def overlap_by_weight(weights_a: Mapping[str, float], weights_b: Mapping[str, float]) -> tuple[float, int]:
    """(sum of min weights over common Security_IDs, count of common Security_IDs)."""
    common = [k for k in weights_a if weights_a[k] > 0 and weights_b.get(k, 0) > 0]
    return sum(min(weights_a[k], weights_b[k]) for k in common), len(common)
