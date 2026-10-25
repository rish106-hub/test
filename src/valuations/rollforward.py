"""Contract §3.1 anchor-date to valuation-date roll-forward (D-007)."""
from __future__ import annotations

from datetime import date
from typing import Sequence


def roll_forward_value(value_at_anchor: float, anchor_date: date, valuation_date: date, cost_of_equity: float,
                       dividends: Sequence[tuple[date, float]] = ()) -> float:
    """dividends: (ex_date, DPS). Only ex-dates in (anchor_date, valuation_date] are deducted,
    each compounded from its ex-date to the valuation date. tau = days / 365.25."""
    raise NotImplementedError("02-valuation: contract §3.1")
