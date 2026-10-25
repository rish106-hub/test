"""Tests of the 00-main shared layer: schema, ownership, Excel rules, units, fixtures, build."""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from build.data_loader import load_model_data
from build.generate_workbook import MODULE_BUILDERS, SHEET_ORDER, build
from src.common import excel_contract as X
from src.common import ownership
from src.common.schema import ALL_TABLES, TABLES
from src.common.units import fiscal_label, market_value_inr_cr, per_share_from_crore, year_fraction
from src.common.validate import validate_csv, validate_rows
from src.common.workbook import InterfaceError, TableColumn, WorkbookContext

ROOT = Path(__file__).resolve().parents[1]

SPEC_SHEETS = [  # v3 spec <workbook_architecture> and <model_governance>
    "VAL_HDFC_BANK", "VAL_FEDERAL_BANK", "VAL_AU_SFB", "VAL_INDIAN_BANK", "VAL_ICICI_BANK", "VAL_KOTAK_BANK",
    "VAL_MAX_FINANCIAL", "START_HERE", "EXECUTIVE_DASHBOARD", "MASTER_SECURITY_REGISTRY", "RAW_FINANCIAL_DATA",
    "MARKET_PRICES", "HISTORICAL_METRICS", "GLOBAL_ASSUMPTIONS", "SECTOR_CLASSIFICATION", "PEER_GROUPS",
    "SOURCE_LOG", "MISSING_DATA", "SCENARIO_ANALYSIS", "METRIC_DICTIONARY", "PPFAS_FLEXICAP_HOLDINGS",
    "HDFC_MIDCAP_HOLDINGS", "MF_NAV_CALCULATOR", "MF_SCENARIO_BUILDER", "MF_SECTOR_ANALYSIS",
    "MF_NAV_SENSITIVITY", "MF_COVERAGE_AUDIT", "PORTFOLIO_REBALANCING", "MODEL_GOVERNANCE",
]


def _tool(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)


# ------------------------------------------------------------------ schema & docs
def test_schema_doc_is_generated_from_code():
    r = _tool("tools/render_schema_doc.py", "--check")
    assert r.returncode == 0, r.stdout


def test_table_names_and_sheets_are_owned():
    for t in ALL_TABLES:
        if "<" in t.excel_name:
            continue
        assert X.TABLE_RE.match(t.excel_name), t.excel_name
        assert ownership.sheet_owner(t.sheet) is not None, (t.key, t.sheet)


@pytest.mark.parametrize("key", ["metric_dictionary", "global_inputs", "governance_log"])
def test_committed_reference_csvs_validate(key):
    t = TABLES[key]
    assert validate_csv(t, ROOT / t.csv_path) == []


def test_required_and_enum_validation():
    t = TABLES["official_nav"]
    ok = {"Plan_ID": "MF001-DIR-GR", "NAV_Date": "2026-10-23", "NAV_INR": "80", "Source_ID": "S",
          "Data_Status": "Retrieved and verified"}
    assert validate_rows(t, [ok]) == []
    assert validate_rows(t, [dict(ok, NAV_INR="")])                       # required
    assert validate_rows(t, [dict(ok, NAV_INR="eighty")])                 # type
    assert validate_rows(t, [dict(ok, Data_Status="Looks fine")])         # enum
    assert validate_rows(t, [ok, ok])                                     # duplicate key
    syn = dict(ok, Data_Status="SYNTHETIC TEST FIXTURE")
    assert validate_rows(t, [syn])                                        # D-013 quarantine
    assert validate_rows(t, [syn], allow_synthetic=True) == []


# ------------------------------------------------------------------ fixtures
def test_fixtures_match_cases():
    r = _tool("tools/make_synthetic_fixtures.py", "--check")
    assert r.returncode == 0, r.stdout


def test_fixtures_validate_only_in_test_build():
    assert load_model_data(test_build=True).problems == []
    for f in (ROOT / "tests/fixtures/synthetic").glob("*.csv"):
        t = TABLES[f.stem]
        if t.csv_path:
            assert validate_csv(t, f), f"{f.name} must be rejected outside a test build"


# ------------------------------------------------------------------ ownership
def test_sheet_order_covers_every_owned_sheet_and_the_spec():
    assert sorted(SHEET_ORDER) == sorted(ownership.all_sheets())
    assert len(SHEET_ORDER) == len(set(SHEET_ORDER))
    assert set(SPEC_SHEETS) <= set(SHEET_ORDER)


def test_every_tracked_file_has_an_owner():
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split()
    orphans = [f for f in files if ownership.path_owner(f) is None]
    assert orphans == [], f"add these paths to spec/ownership.toml: {orphans}"


def test_frozen_paths_win_over_worker_paths():
    assert ownership.path_owner("tests/contract/test_nav_contract.py") == "frozen"
    assert ownership.path_owner("src/fund_nav/methods.py") == "03-nav"
    assert ownership.path_owner("data/canonical/fund_holdings.csv") == "01-data"
    assert ownership.path_owner("data/canonical/assumptions.csv") == "02-valuation"   # most specific wins
    assert ownership.path_owner("data/canonical/peer_membership.csv") == "04-charts"
    assert ownership.path_owner("data/canonical/governance_log.csv") == "00-main"
    assert ownership.sheet_owner("VAL_TATA_STEEL") == "02-valuation"   # template prefix
    assert ownership.path_owner("spec/change_requests/CR-03-nav-001-links.md") == "shared"
    assert ownership.path_owner("spec/change_requests/README.md") == "00-main"


# ------------------------------------------------------------------ Excel rules
def test_formula_scanner():
    assert X.check_formula('=INDEX(tbl_A[x],MATCH(B1,tbl_A[id],0))') == []
    assert any("XLOOKUP" in p for p in X.check_formula("=XLOOKUP(A1,B:B,C:C)"))
    assert any("INDIRECT" in p for p in X.check_formula('=SUM(INDIRECT("A1"))'))
    assert X.check_formula('=IF(A1="XLOOKUP(",1,0)') == []               # text inside strings ignored
    assert X.tables_referenced("=SUM(tbl_PriceControls[Selected_Scenario_Market_Price])") == {"tbl_PriceControls"}
    assert X.names_referenced("=A1*(1+in_Global_Price_Shock_Pct)+out_S00001_FV_Base") == \
        {"in_Global_Price_Shock_Pct", "out_S00001_FV_Base"}
    assert X.functions_used("=_xlfn.STDEV.S(A1:A9)") == {"STDEV.S"}


def test_workbook_context_enforces_ownership_and_references(tmp_path):
    ctx = WorkbookContext(str(tmp_path / "t.xlsx"), test_build=True)
    ctx.create_sheets(["START_HERE", "SCENARIO_ANALYSIS", "VALUATION_OUTPUTS"])
    with pytest.raises(InterfaceError):
        ctx.sheet("03-nav", "VALUATION_OUTPUTS")                       # owned by 02-valuation
    ctx.sheet("03-nav", "SCENARIO_ANALYSIS")
    with pytest.raises(InterfaceError):
        ctx.write_formula("03-nav", "SCENARIO_ANALYSIS", "A5", "=LET(x,1,x)")
    ctx.write_formula("03-nav", "SCENARIO_ANALYSIS", "A5", "=SUM(tbl_ValuationOutputs[FV_Base_INR])")
    with pytest.raises(InterfaceError, match="unknown table tbl_ValuationOutputs"):
        ctx.close()


def test_workbook_context_accepts_resolved_references(tmp_path):
    ctx = WorkbookContext(str(tmp_path / "t.xlsx"))
    ctx.create_sheets(["GLOBAL_ASSUMPTIONS", "SCENARIO_ANALYSIS"])
    ctx.sheet("00-main", "GLOBAL_ASSUMPTIONS")
    ctx.write_value("00-main", "GLOBAL_ASSUMPTIONS", "B2", 0.0, role="input")
    ctx.define_name("00-main", "in_Global_Price_Shock_Pct", "GLOBAL_ASSUMPTIONS", "B2")
    ctx.sheet("03-nav", "SCENARIO_ANALYSIS")
    ctx.add_table("03-nav", "SCENARIO_ANALYSIS", 2, 0, "tbl_SectorShocks",
                  [TableColumn("Sector"), TableColumn("Sector_Price_Shock_Pct", role="input"),
                   TableColumn("Effective", formula="=(1+[@Sector_Price_Shock_Pct])*(1+in_Global_Price_Shock_Pct)-1")],
                  [["Financial Services", 0.0]])
    ctx.close()


# ------------------------------------------------------------------ units
def test_units_and_fiscal_labels():
    assert market_value_inr_cr(4_000_000, 750.0) == pytest.approx(300.0)
    assert per_share_from_crore(24.375, 100_000_000) == pytest.approx(2.4375)
    assert fiscal_label(date(2026, 3, 31)) == "FY2026"
    assert fiscal_label(date(2026, 4, 1)) == "FY2027"
    assert fiscal_label(date(2026, 6, 30), quarterly=True) == "Q1FY2027"
    assert fiscal_label(date(2027, 3, 31), quarterly=True) == "Q4FY2027"
    assert year_fraction(date(2026, 3, 31), date(2026, 10, 25)) == pytest.approx(208 / 365.25)


# ------------------------------------------------------------------ build
def test_test_build_and_isolated_builds_succeed(tmp_path):
    full = build(test_build=True, out_dir=tmp_path / "full")
    assert Path(full["workbook"]).exists()
    assert "VAL_HDFC_BANK" in full["unbuilt_sheets"]          # gaps are listed, not hidden
    # D-030: only interfaces of modules that did not build are stubbed, whatever subset has merged
    unbuilt_owners = {w for w, spec in MODULE_BUILDERS if spec in full["not_implemented"]}
    manifest = json.loads((tmp_path / "full" / "manifest.json").read_text())
    for name in full["stubbed"]:
        assert ownership.sheet_owner(manifest["tables"][name]["sheet"]) in unbuilt_owners, name
    iso = build(test_build=True, only="03-nav", out_dir=tmp_path / "iso")
    assert "tbl_ValuationOutputs" in iso["stubbed"]


def test_production_build_rejects_synthetic_and_never_stubs(tmp_path):
    with pytest.raises(SystemExit):
        build(test_build=False, only="03-nav", out_dir=tmp_path)
