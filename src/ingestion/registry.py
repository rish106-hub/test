"""Security registry maintenance (spec <unique_identifier_rule>)."""
from __future__ import annotations

from typing import Mapping, Sequence


def match_security(isin: str | None, ticker: str | None, registry: Sequence[Mapping]) -> str | None:
    """Security_ID by ISIN, then by exchange ticker. Never by company name. None if unmatched."""
    raise NotImplementedError("01-data")


def next_security_id(registry: Sequence[Mapping]) -> str:
    """S00001-style id one above the current maximum; ids are never reused."""
    raise NotImplementedError("01-data")
