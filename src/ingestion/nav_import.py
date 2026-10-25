"""Official NAV import (AMFI NAVAll.txt / NAV history)."""
from __future__ import annotations

from typing import Iterable


def parse_amfi_nav(lines: Iterable[str], scheme_codes: dict[str, str], source_id: str) -> list[dict]:
    """scheme_codes: {AMFI_Scheme_Code: Plan_ID}. Returns official_nav rows for those codes only."""
    raise NotImplementedError("01-data")
