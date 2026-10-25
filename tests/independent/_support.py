"""Helpers for the I layer: call a worker's reference function, compare results field by field."""
from __future__ import annotations

import dataclasses
import math
from enum import Enum

import pytest

REL = 1e-9     # spec/test_plan.md W-03 tolerance, also used for the I layer; never loosened
ABS = 1e-12


def call_worker(fn, *args, **kwargs):
    """Run a worker reference function; NOT RUN (skip) while it is still a stub."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError as exc:
        pytest.skip(f"NOT RUN: worker reference {fn.__module__}.{fn.__qualname__} raises "
                    f"NotImplementedError ({exc}); runs once 00-main merges the worker")


def norm(v):
    if isinstance(v, Enum):
        return v.value
    return v


def same(a, b, rel: float = REL, abs_: float = ABS) -> bool:
    a, b = norm(a), norm(b)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) or math.isnan(b):
            return False
        return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)
    if isinstance(a, dict) and isinstance(b, dict):
        return set(map(str, a)) == set(map(str, b)) and all(
            same(a[k], b[next(kk for kk in b if str(kk) == str(k))], rel, abs_) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(same(x, y, rel, abs_) for x, y in zip(a, b))
    return str(a) == str(b)


def diff_fields(worker, mine, fields=None, rel: float = REL, skip=()) -> dict:
    """{field: (worker, clean-room)} for every field that disagrees."""
    names = fields or [f.name for f in dataclasses.fields(mine)]
    out = {}
    for f in names:
        if f in skip:
            continue
        w, m = getattr(worker, f), getattr(mine, f)
        if not same(w, m, rel):
            out[f] = (w, m)
    return out
