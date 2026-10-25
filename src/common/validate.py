"""Row-level validation of canonical tables against src/common/schema.py.

Used by 01-data before writing a CSV, by 00-main before building, and by 05-qa.
Returns a list of human-readable problems; an empty list means valid.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from src.common.enums import DataStatus
from src.common.schema import Table

SYNTHETIC = DataStatus.SYNTHETIC_TEST_FIXTURE.value
SYNTHETIC_SOURCE_PREFIX = "SRC-SYNTH"   # fixture Source_IDs; a second quarantine for tables without a status


def _check_type(value: str, dtype: str) -> bool:
    if value == "":
        return True
    try:
        if dtype == "float":
            float(value)
        elif dtype == "int":
            int(value)
        elif dtype == "date":
            date.fromisoformat(value)
        elif dtype == "bool":
            return value in ("TRUE", "FALSE")
    except ValueError:
        return False
    return True


def validate_rows(table: Table, rows: Iterable[Mapping[str, str]], *, allow_synthetic: bool = False) -> list[str]:
    problems: list[str] = []
    stored = table.stored_columns
    expected = [c.name for c in stored]
    seen_keys: set[tuple] = set()
    for n, row in enumerate(rows, start=2):  # row 1 is the CSV header
        missing_cols = [c for c in expected if c not in row]
        if missing_cols:
            problems.append(f"{table.key} row {n}: missing columns {missing_cols}")
            continue
        for col in stored:
            v = (row[col.name] or "").strip()
            if col.required and v == "":
                problems.append(f"{table.key} row {n}: {col.name} is required")
            if not _check_type(v, col.dtype):
                problems.append(f"{table.key} row {n}: {col.name}={v!r} is not {col.dtype}")
            if col.enum and v and v not in col.enum:
                problems.append(f"{table.key} row {n}: {col.name}={v!r} not in {col.enum}")
            if not allow_synthetic and (v == SYNTHETIC or
                                        (col.name.endswith("Source_ID") and v.startswith(SYNTHETIC_SOURCE_PREFIX))):
                problems.append(f"{table.key} row {n}: synthetic fixture data in a production build (D-013)")
        key = tuple(row[k] for k in table.primary_key)
        if key in seen_keys:
            problems.append(f"{table.key} row {n}: duplicate primary key {key}")
        seen_keys.add(key)
    return problems


def validate_csv(table: Table, path: Path | str, *, allow_synthetic: bool = False) -> list[str]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        expected = [c.name for c in table.stored_columns]
        problems = []
        if header != expected:
            problems.append(f"{path}: header {header} != schema {expected}")
        return problems + validate_rows(table, list(reader), allow_synthetic=allow_synthetic)


def write_header(table: Table, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([c.name for c in table.stored_columns])
