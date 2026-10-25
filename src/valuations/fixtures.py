"""Test-build fallback for the 02-valuation synthetic fixtures (pending CR-02-valuation-001).

tests/fixtures/synthetic/ has no raw financials, corporate actions or valuation assumptions,
so the isolated build would value S90001 from empty tables. In a TEST build only, the
02-valuation builder appends the rows in tests/valuations/fixtures/synthetic/ to ModelData
before it builds; tbl_RawFinancials and tbl_CorporateActions are stubbed from ModelData after
the module builders run, so the stubs carry the rows too. Rows whose primary key is already
present are skipped, so this becomes a no-op once 00-main promotes the files. A production
build never calls it, and would reject the rows anyway (D-013).
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.common import schema as S
from src.common.validate import validate_rows

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "valuations" / "fixtures" / "synthetic"
FIXTURE_TABLES = ("raw_financials", "corporate_actions", "assumptions")


def augment_test_fixtures(data) -> list[str]:
    """Append the module's synthetic fixtures to `data` in a test build. Returns the table keys extended."""
    if not data.test_build:
        return []
    extended = []
    for key in FIXTURE_TABLES:
        path = FIXTURE_DIR / f"{key}.csv"
        if not path.exists():
            continue
        table = S.TABLES[key]
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        present = {tuple(r.get(k) for k in table.primary_key) for r in data.rows(key)}
        new = [r for r in rows if tuple(r.get(k) for k in table.primary_key) not in present]
        if not new:
            continue
        problems = validate_rows(table, new, allow_synthetic=True)
        if problems:
            raise ValueError(f"{path}: invalid fixture rows:\n  " + "\n  ".join(problems))
        data.tables[key] = list(data.rows(key)) + new
        rel = str(path.relative_to(ROOT))
        data.sources[key] = f"{data.sources[key]} + {rel}" if data.sources.get(key) else rel
        extended.append(key)
    return extended
