"""Convert canonical CSV strings to typed cell values (schema dtype -> Python/Excel value)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Mapping, Sequence

from src.common.schema import Column, Table


def typed_value(col: Column, raw: str | None):
    if raw is None or raw == "":
        return None
    if col.dtype == "float":
        return float(raw)
    if col.dtype == "int":
        return int(float(raw))
    if col.dtype == "bool":
        return raw == "TRUE"
    if col.dtype == "date":
        d = date.fromisoformat(raw)
        return datetime(d.year, d.month, d.day)
    return raw


def typed_rows(table: Table, rows: Sequence[Mapping[str, str]], columns: Sequence[str] | None = None) -> list[list]:
    cols = [table.column(c) for c in columns] if columns else list(table.stored_columns)
    return [[typed_value(c, r.get(c.name)) for c in cols] for r in rows]
