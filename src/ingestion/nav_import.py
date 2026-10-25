"""Official NAV import (AMFI NAVAll.txt / NAV history).

Both AMFI layouts end with `...;Net Asset Value;Date` and start with the scheme code, so one parser
reads them:
  NAVAll.txt   Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date
  NAV history  Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from src.common.enums import DataStatus


def parse_amfi_date(text: str) -> str:
    """'23-Oct-2026' -> '2026-10-23'."""
    return datetime.strptime(text.strip(), "%d-%b-%Y").date().isoformat()


def parse_amfi_nav(lines: Iterable[str], scheme_codes: dict[str, str], source_id: str) -> list[dict]:
    """scheme_codes: {AMFI_Scheme_Code: Plan_ID}. Returns official_nav rows for those codes only.

    Header, blank, section and AMC lines are skipped. A line whose NAV is not numeric (AMFI prints
    'N.A.' for suspended schemes) is skipped, never turned into 0 (R009). Duplicate (Plan_ID, date)
    pairs keep the first occurrence.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in lines:
        parts = raw.rstrip("\r\n").split(";")
        if len(parts) < 8:
            continue
        plan_id = scheme_codes.get(parts[0].strip())
        if plan_id is None:
            continue
        try:
            nav = float(parts[-2].strip())
            day = parse_amfi_date(parts[-1])
        except ValueError:
            continue
        if (plan_id, day) in seen:
            continue
        seen.add((plan_id, day))
        out.append({
            "Plan_ID": plan_id,
            "NAV_Date": day,
            "NAV_INR": parts[-2].strip(),     # as printed by AMFI (4 decimals); float-checked above
            "Source_ID": source_id,
            "Data_Status": DataStatus.RETRIEVED_VERIFIED.value,
        })
    return out
