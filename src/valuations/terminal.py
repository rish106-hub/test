"""Contract §10 terminal-value controls."""
from __future__ import annotations

from typing import Callable, Sequence

from src.common.enums import CheckResult
from src.valuations.errors import TerminalGrowthError


def require_growth_below_rate(rate: float, growth: float) -> None:
    """TV-1: every Gordon terminal needs g < r."""
    if not growth < rate:
        raise TerminalGrowthError(f"terminal growth {growth} must be below the discount rate {rate} (contract §10 TV-1)")


def gordon_terminal_value(next_period_flow: float, rate: float, growth: float) -> float:
    """next_period_flow / (rate - growth). Raises TerminalGrowthError if growth >= rate."""
    require_growth_below_rate(rate, growth)
    return next_period_flow / (rate - growth)


def terminal_flag(terminal_value_share: float, warn_threshold: float) -> str:
    """'PASS' or 'WARNING' (TV-3)."""
    return CheckResult.WARNING.value if terminal_value_share > warn_threshold else CheckResult.PASS.value


def sensitivity_grid(value_fn: Callable[[float, float], float], rates: Sequence[float],
                     growths: Sequence[float]) -> list[list[float | None]]:
    """rows = rates, cols = growths; a cell with g >= r is None, never a number (TV-5)."""
    return [[None if not g < r else value_fn(r, g) for g in growths] for r in rates]


def sensitivity_grid_2d(value_fn: Callable[[float, float], float], rows: Sequence[float],
                        cols: Sequence[float]) -> list[list[float | None]]:
    """Generic grid, e.g. r_e x ROE_T for RI (TV-4). A cell whose terminal is invalid
    (value_fn raises TerminalGrowthError) is None, never a number (TV-5)."""
    out: list[list[float | None]] = []
    for a in rows:
        line: list[float | None] = []
        for b in cols:
            try:
                line.append(value_fn(a, b))
            except TerminalGrowthError:
                line.append(None)
        out.append(line)
    return out
