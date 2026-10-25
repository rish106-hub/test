"""Contract §3.4."""
from src.valuations.terminal import require_growth_below_rate


def justified_pb(terminal_roe: float, cost_of_equity: float, terminal_growth: float) -> float:
    """(ROE - g) / (r - g). Raises TerminalGrowthError if g >= r."""
    require_growth_below_rate(cost_of_equity, terminal_growth)
    return (terminal_roe - terminal_growth) / (cost_of_equity - terminal_growth)
