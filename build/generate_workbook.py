"""Integration build: assembles every module's sheets into one workbook.

usage:
  python build/generate_workbook.py                     production build from data/canonical
  python build/generate_workbook.py --test-build        synthetic fixtures, watermarked
  python build/generate_workbook.py --test-build --only 03-nav
                                                        one worker + main, other interfaces stubbed
Outputs go to build/out/ (git-ignored): the .xlsx, manifest.json and build_report.txt.
The .xlsx is a build artefact and is never committed or hand-edited (D-001).
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build import main_sheets  # noqa: E402
from build.data_loader import load_model_data  # noqa: E402
from build.interface_stubs import add_stubs  # noqa: E402
from src.common.workbook import WorkbookContext  # noqa: E402

OUTPUT_NAME = "Indian_Equity_Valuation_and_MF_NAV_Model.xlsx"

SHEET_ORDER = [
    "START_HERE", "EXECUTIVE_DASHBOARD", "GLOBAL_ASSUMPTIONS", "DATA_FEASIBILITY",
    "MASTER_SECURITY_REGISTRY", "SECTOR_CLASSIFICATION", "SOURCE_LOG", "MISSING_DATA",
    "RAW_FINANCIAL_DATA", "MARKET_PRICES", "HISTORICAL_METRICS", "METRIC_DICTIONARY", "PEER_GROUPS",
    "VALUATION_ASSUMPTIONS", "VAL_HDFC_BANK", "VAL_FEDERAL_BANK", "VAL_AU_SFB", "VAL_INDIAN_BANK",
    "VAL_ICICI_BANK", "VAL_KOTAK_BANK", "VAL_MAX_FINANCIAL", "VALUATION_OUTPUTS",
    "SCENARIO_ANALYSIS", "PPFAS_FLEXICAP_HOLDINGS", "HDFC_MIDCAP_HOLDINGS", "MF_NAV_CALCULATOR",
    "MF_SCENARIO_BUILDER", "MF_SECTOR_ANALYSIS", "MF_NAV_SENSITIVITY", "MF_COVERAGE_AUDIT",
    "PORTFOLIO_REBALANCING", "FUND_PERFORMANCE", "MODEL_GOVERNANCE", "VALIDATION_CHECKS",
]

# (worker, "module:function"), in build order. Charts render last, into reserved zones.
MODULE_BUILDERS = [
    ("01-data", "src.ingestion.sheets:build_sheets"),
    ("02-valuation", "src.valuations.sheets:build_sheets"),
    ("04-charts", "src.peers.sheets:build_sheets"),
    ("03-nav", "src.fund_nav.sheets:build_sheets"),
]
CHART_BUILDER = ("04-charts", "src.charts.render:render_charts")


def _call(spec: str, ctx, data):
    module, fn = spec.split(":")
    getattr(importlib.import_module(module), fn)(ctx, data)


def build(test_build: bool, only: str | None = None, out_dir: Path | None = None) -> dict:
    if only and not test_build:
        raise SystemExit("--only requires --test-build (stubs use synthetic fixtures)")
    out_dir = Path(out_dir or ROOT / "build" / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_model_data(test_build)
    if data.problems and not test_build:
        raise SystemExit("canonical data failed validation:\n  " + "\n  ".join(data.problems))

    path = out_dir / OUTPUT_NAME
    ctx = WorkbookContext(str(path), test_build=test_build)
    ctx.create_sheets(SHEET_ORDER)
    report = {"test_build": test_build, "only": only, "not_implemented": {}, "stubbed": [],
              "data_problems": data.problems, "data_sources": data.sources}

    main_sheets.build_sheets(ctx, data)
    built = {"00-main"}
    for worker, spec in MODULE_BUILDERS:
        if only and worker != only:
            continue
        try:
            _call(spec, ctx, data)
            built.add(worker)
        except NotImplementedError as exc:
            report["not_implemented"][spec] = str(exc)
    if only:
        report["stubbed"] = add_stubs(ctx, data, built)
    main_sheets.build_dashboard(ctx, data)
    if not only or only == CHART_BUILDER[0]:
        try:
            _call(CHART_BUILDER[1], ctx, data)
        except NotImplementedError as exc:
            report["not_implemented"][CHART_BUILDER[1]] = str(exc)

    for name in ctx.unbuilt_sheets():   # visible gap, never a silently missing sheet
        ctx.sheets[name].write(2, 0, f"NOT YET BUILT - owner {ctx.sheet_owner[name]}",
                               ctx.wb.add_format({"bold": True, "font_color": "#9C0006", "bg_color": "#FFC7CE"}))
    report["unbuilt_sheets"] = ctx.unbuilt_sheets()
    ctx.close()   # raises InterfaceError on unresolved tbl_/in_/out_ references

    report["workbook"] = str(path)
    (out_dir / "manifest.json").write_text(json.dumps(ctx.manifest(), indent=2, default=str))
    (out_dir / "build_report.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test-build", action="store_true")
    ap.add_argument("--only", choices=["01-data", "02-valuation", "03-nav", "04-charts"])
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args(argv)
    report = build(args.test_build, args.only, args.out_dir)
    print(f"built {report['workbook']}")
    print(f"  not implemented: {len(report['not_implemented'])} module(s); unbuilt sheets: {len(report['unbuilt_sheets'])}")
    if report["stubbed"]:
        print(f"  stubbed interfaces: {', '.join(report['stubbed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
