"""Loads canonical CSVs (production) or synthetic fixtures (test build) into ModelData."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from src.common.schema import ALL_TABLES, TABLES
from src.common.validate import validate_rows

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


@dataclass
class ModelData:
    tables: dict[str, list[dict]]
    sources: dict[str, str]                 # table key -> file it came from ("" if absent)
    test_build: bool
    problems: list[str] = field(default_factory=list)

    def rows(self, key: str) -> list[dict]:
        if key not in TABLES:
            raise KeyError(f"unknown table {key!r}")
        return self.tables.get(key, [])


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_model_data(test_build: bool) -> ModelData:
    tables, sources, problems = {}, {}, []
    for t in ALL_TABLES:
        candidates = []
        if test_build:
            candidates.append(FIXTURES / f"{t.key}.csv")
        if t.csv_path:
            candidates.append(ROOT / t.csv_path)
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            tables[t.key], sources[t.key] = [], ""
            continue
        rows = _read(path)
        if t.csv_path:   # workbook-only tables appear only as fixtures for stubs
            problems += validate_rows(t, rows, allow_synthetic=test_build)
        tables[t.key], sources[t.key] = rows, str(path.relative_to(ROOT))
    return ModelData(tables, sources, test_build, problems)
