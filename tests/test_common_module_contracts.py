"""spec/module_contracts.toml is consistent, and tools/check_module_contract.py rejects what it should (D-027)."""
import fnmatch
import re
from pathlib import Path

import pytest

from build.interface_stubs import INTERFACE_TABLES
from src.common import ownership, schema as S
from tools.check_module_contract import check_doc, check_functions, check_manifest, load_contracts

ROOT = Path(__file__).resolve().parents[1]
MODULES = load_contracts()
BUILT_BY = {t: w for w, c in MODULES.items() for t in c["builds_tables"]}


def test_every_worker_has_a_contract():
    assert set(MODULES) == set(ownership.load()["workers"])


def test_each_interface_table_has_one_builder_and_a_schema():
    seen = [t for c in MODULES.values() for t in c["builds_tables"]]
    assert len(seen) == len(set(seen))
    for t in seen:
        assert any(x.excel_name == t or fnmatch.fnmatchcase(t, re.sub(r"<[^>]+>", "*", x.excel_name))
                   for x in S.ALL_TABLES), t


def test_builders_own_the_sheet_each_table_lives_on():
    for t, w in BUILT_BY.items():
        sch = next((x for x in S.ALL_TABLES if x.excel_name == t), None)
        if sch is not None:
            assert ownership.sheet_owner(sch.sheet) == w, (t, sch.sheet, w)


def test_consumed_interfaces_exist_and_can_be_stubbed_for_isolated_builds():
    stubbable = {name for _, name, _, _ in INTERFACE_TABLES}
    for w, c in MODULES.items():
        for pat in c["consumes"]:
            if pat.startswith("in_"):
                continue
            hits = [t for t in BUILT_BY if fnmatch.fnmatchcase(t, pat)]
            assert hits, f"{w} consumes {pat}, which no module builds"
            for t in hits:
                assert BUILT_BY[t] != w, f"{w} lists its own table {t} as consumed"
                assert BUILT_BY[t] == "00-main" or t in stubbable, f"{t} ({w} consumes) has no interface stub"


def test_interface_stubs_only_stub_declared_interfaces():
    for _, name, sheet, _ in INTERFACE_TABLES:
        assert name in BUILT_BY and BUILT_BY[name] == ownership.sheet_owner(sheet), name


def test_reference_functions_import_and_contract_tests_belong_to_the_module():
    for w, c in MODULES.items():
        assert check_functions(c) == [], w
        for f in c["contract_tests"]:
            text = (ROOT / f).read_text()
            assert f'pytest.mark.owner("{w}")' in text, (w, f)
    listed = {f for c in MODULES.values() for f in c["contract_tests"]}
    assert listed == {f"tests/contract/{p.name}" for p in (ROOT / "tests/contract").glob("test_*.py")}


def test_writes_csv_tables_are_produced_by_that_worker():
    for w, c in MODULES.items():
        for key in c["writes_csv"]:
            t = S.TABLES[key]
            assert t.csv_path and ownership.path_owner(t.csv_path) == w, (w, key, t.csv_path)


# ---- checker behaviour on a synthetic manifest -------------------------------------------

def _manifest(**over):
    cols = [c.name for c in S.NAV_SUMMARY.columns]
    m = {"tables": {"tbl_NAVSummary": {"owner": "03-nav", "columns": cols},
                    "tbl_ValuationOutputs": {"owner": "02-valuation", "columns": []},
                    "tbl_Val_HDFC_RI": {"owner": "02-valuation", "columns": []}},
         "names": {"in_Price_Date": {"owner": "00-main"}},
         "references": {"03-nav": {"tables": ["tbl_ValuationOutputs"], "names": ["in_Price_Date"]}}}
    for k, v in over.items():
        m[k] = v
    return m


def _nav_only():
    return dict(MODULES["03-nav"], builds_tables=["tbl_NAVSummary"])


def test_checker_accepts_a_conforming_module():
    assert check_manifest("03-nav", _nav_only(), _manifest()) == []


@pytest.mark.parametrize("change,expected", [
    ({"tables": {"tbl_NAVSummary": {"owner": "STUB", "columns": []}}}, "missing interface table tbl_NAVSummary (stubbed)"),
    ({"tables": {"tbl_NAVSummary": {"owner": "03-nav", "columns": ["Plan_ID"]}}}, "columns differ from schema"),
    ({"tables": {"tbl_NAVSummary": {"owner": "03-nav", "columns": [c.name for c in S.NAV_SUMMARY.columns]},
                 "tbl_MyScratch": {"owner": "03-nav", "columns": []}}}, "undeclared table tbl_MyScratch"),
    ({"names": {"out_X": {"owner": "03-nav"}}}, "undeclared defined name out_X"),
    ({"references": {"03-nav": {"tables": ["tbl_PeerSummary"], "names": []}}}, "neither built by 03-nav nor in its consumes"),
    ({"references": {"03-nav": {"tables": ["tbl_Val_HDFC_RI", "tbl_ValuationOutputs"], "names": []}}}, "private table of 02-valuation"),
])
def test_checker_rejects(change, expected):
    problems = check_manifest("03-nav", _nav_only(), _manifest(**change))
    assert any(expected in p for p in problems), problems


def test_module_doc_templates_are_rejected_until_filled(tmp_path):
    for w, c in MODULES.items():
        if c["module_doc"]:
            assert check_doc(c), f"{w}: the TODO template must not pass"
    doc = tmp_path / "MODULE.md"
    doc.write_text("# M\n" + "".join(f"## {s}\n\nFilled in.\n\n" for s in
                                    ("Inputs", "Outputs", "Assumptions", "Limitations", "Tests")))
    assert check_doc({"module_doc": str(doc)}) == []
