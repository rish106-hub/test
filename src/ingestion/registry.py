"""Security registry maintenance (spec <unique_identifier_rule>)."""
from __future__ import annotations

import re
from typing import Mapping, Sequence

_ID_RE = re.compile(r"^S(\d{5})$")


def _norm(v) -> str:
    return (v or "").strip().upper()


def match_security(isin: str | None, ticker: str | None, registry: Sequence[Mapping]) -> str | None:
    """Security_ID by ISIN, then by exchange ticker. Never by company name. None if unmatched."""
    i = _norm(isin)
    if i:
        for row in registry:
            if _norm(row.get("ISIN")) == i:
                return row["Security_ID"]
    t = _norm(ticker)
    if t:
        for row in registry:
            if _norm(row.get("Exchange_Ticker")) == t:
                return row["Security_ID"]
    return None


def next_security_id(registry: Sequence[Mapping]) -> str:
    """S00001-style id one above the current maximum; ids are never reused."""
    top = 0
    for row in registry:
        m = _ID_RE.match((row.get("Security_ID") or "").strip())
        if m:
            top = max(top, int(m.group(1)))
    return f"S{top + 1:05d}"
