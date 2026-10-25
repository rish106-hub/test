"""Contract §10 terminal-value controls."""
from __future__ import annotations

from typing import Callable, Sequence


def gordon_terminal_value(next_period_flow: float, rate: float, growth: float) -> float:
    """next_period_flow / (rate - growth). Raises TerminalGrowthError if growth >= rate."""
    raise NotImplementedError("02-valuation: contract §10 TV-1")


def terminal_flag(terminal_value_share: float, warn_threshold: float) -> str:
    """'PASS' or 'WARNING' (TV-3)."""
    raise NotImplementedError("02-valuation: contract §10 TV-3")


def sensitivity_grid(value_fn: Callable[[float, float], float], rates: Sequence[float],
                     growths: Sequence[float]) -> list[list[float | None]]:
    """rows = rates, cols = growths; a cell with g >= r is None, never a number (TV-5)."""
    raise NotImplementedError("02-valuation: contract §10 TV-4/TV-5")
