"""Fixtures for the W and E layers (05-qa).

Which workbook is validated:
  QA_WORKBOOK=<path to .xlsx>   validate that build (its build_report.json / manifest.json are read
                                from the same folder); this is how qa/run_validation.py checks the
                                integration or production build 00-main produced.
  otherwise                     generate a fresh test build (synthetic, watermarked) into a temporary
                                folder; QA_BUILD_ONLY=<worker> makes it an isolated `--only` build.
Every value is read from a LibreOffice recalculation, never from XlsxWriter's cached zeros.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.workbook.wbmodel import Workbook

ROOT = Path(__file__).resolve().parents[2]


def pytest_configure(config):
    config.addinivalue_line("markers", "workbook: requires a generated workbook and LibreOffice recalculation")


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> Workbook:
    if shutil.which("soffice") is None:
        pytest.skip("NOT RUN: LibreOffice (soffice) is not installed; values cannot be recalculated")
    from build.recalc import recalc
    work = tmp_path_factory.mktemp("qa_build")
    given = os.environ.get("QA_WORKBOOK")
    if given:
        src = Path(given).resolve()
        if not src.exists():
            pytest.skip(f"NOT RUN: QA_WORKBOOK={given} does not exist")
        build_dir = src.parent
    else:
        from build.generate_workbook import build
        only = os.environ.get("QA_BUILD_ONLY") or None
        report = build(test_build=True, only=only, out_dir=work / "out")
        src, build_dir = Path(report["workbook"]), work / "out"
    return Workbook(src, recalc(src, work / "recalc"), build_dir)


def require_real(wb: Workbook, *tables: str):
    """Skip (NOT RUN) unless each table was built by its producing module in this build."""
    missing = [t for t in tables if not wb.is_real(t)]
    if missing:
        how = {t: ("stub" if t in wb.tables else "absent") for t in missing}
        pytest.skip(f"NOT RUN: {how} in this build; the producing module is not merged/built yet")


def require_production(wb: Workbook):
    if wb.is_test_build:
        pytest.skip("NOT RUN: this check applies to a production build (data/canonical); "
                    "the validated build is a synthetic test build")
