"""Contract §7.0 coverage status of a holdings line."""
from src.common.enums import CoverageStatus
from src.fund_nav.model import HoldingLine


def coverage_status(line: HoldingLine, case: str = "Base") -> CoverageStatus:
    raise NotImplementedError("03-nav: contract §7.0")
