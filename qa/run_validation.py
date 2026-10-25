"""05-qa validation runner: executes the C, I, W and E suites and writes
build/out/validation_results.csv (schema `validation_results`), recording only what ran.

usage:
  python qa/run_validation.py                          fresh synthetic test build, all suites
  python qa/run_validation.py --workbook build/out/Indian_Equity_Valuation_and_MF_NAV_Model.xlsx
                                                       validate an existing (integration/production) build;
                                                       its build_report.json and manifest.json are read
                                                       from the same folder
  python qa/run_validation.py --only 03-nav            fresh isolated `--only` test build

Result mapping (spec/test_plan.md, CLAUDE.md non-negotiables):
  passed                       PASS (or WARNING if the test records qa_result=WARNING)
  failed                       FAIL
  xfailed (known finding)      FAIL, evidence names the finding
  skipped / errored / missing  NOT RUN, Executed = FALSE, with the reason
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.enums import CheckResult  # noqa: E402
from src.common.schema import VALIDATION_RESULTS  # noqa: E402
from src.common.validate import validate_rows  # noqa: E402

SUITES = {"contract": "tests/contract", "independent": "tests/independent", "workbook": "tests/workbook"}
CATEGORY = {"T": "C contract", "I": "I independent", "W": "W workbook", "E": "E end-to-end", "PROV": "Provenance",
            "QA": "QA harness self-test"}

# Checks in the plan that no automated test covers; always listed so they are never forgotten.
PLANNED_MANUAL = [
    ("PROV-03", "Provenance", "Sampled audit (>= 10% of source_log, stratified) of value, unit, period and basis "
                              "against the cited document and page (qa/provenance_audit.md)",
     "needs real source_log and data/raw from 01-data; not yet merged"),
    ("H-01", "H historical", "Historical / backtest validation with point-in-time data (spec/test_plan.md §H)",
     "no point-in-time data (raw_financials.Known_As_Of) exists yet; look-ahead and survivorship cannot be assessed"),
]

_ID = re.compile(r"^test_((?:[A-Z]+_)*?[A-Z]+)_(\d+[a-z]?)(?:_|$)")


def check_id(name: str, param: str | None) -> str:
    base = name.split("[", 1)[0]
    m = _ID.match(base)
    cid = f"{m.group(1).replace('_', '-')}-{m.group(2)}" if m else base.removeprefix("test_")
    return f"{cid}[{param}]" if param else cid


def classify(e: dict) -> tuple[str, bool, str]:
    ph = e["phases"]
    setup, call, teardown = ph.get("setup", {}), ph.get("call"), ph.get("teardown", {})
    if setup.get("outcome") == "failed":
        return CheckResult.NOT_RUN.value, False, "ERROR in setup (not executed): " + _short(setup.get("text"))
    if setup.get("outcome") == "skipped" and not setup.get("wasxfail"):
        return CheckResult.NOT_RUN.value, False, _skip_reason(setup.get("text"))
    if call is None:
        return CheckResult.NOT_RUN.value, False, "no call phase recorded"
    if call.get("wasxfail") is not None:
        if call["outcome"] == "skipped":          # xfailed: executed and failing on a known finding
            return CheckResult.FAIL.value, True, f"{call['wasxfail']} | " + _short(call.get("text"))
        return CheckResult.PASS.value, True, f"XPASS: the known finding no longer reproduces ({call['wasxfail']})"
    if call["outcome"] == "skipped":
        return CheckResult.NOT_RUN.value, False, _skip_reason(call.get("text"))
    if call["outcome"] == "failed":
        return CheckResult.FAIL.value, True, _short(call.get("text"))
    if teardown.get("outcome") == "failed":
        return CheckResult.FAIL.value, True, "teardown error: " + _short(teardown.get("text"))
    res = e["props"].get("qa_result", CheckResult.PASS.value)
    return res, True, e["props"].get("qa_evidence", "pytest passed")


def _skip_reason(text: str | None) -> str:
    t = (text or "").strip()
    t = re.sub(r"^Skipped:\s*", "", t)
    return t if t.startswith("NOT RUN") else f"NOT RUN: {t}"


def _short(text: str | None, n: int = 600) -> str:
    lines = [l for l in (text or "").splitlines() if l.startswith("E ") or "Error" in l]
    s = " | ".join(l.strip() for l in lines[:6]) or (text or "").strip()[-n:]
    return s[:n]


def run(args) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if args.workbook:
        env["QA_WORKBOOK"] = str(Path(args.workbook).resolve())
    if args.only:
        env["QA_BUILD_ONLY"] = args.only
    with tempfile.TemporaryDirectory() as tmp:
        res_json = Path(tmp) / "results.json"
        env["QA_RESULTS_JSON"] = str(res_json)
        paths = [SUITES[s] for s in args.suites]
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "qa.pytest_qa_plugin", "-p", "no:cacheprovider", *paths]
        started = datetime.now(timezone.utc).replace(microsecond=0)
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        if not res_json.exists():
            print(proc.stdout[-3000:], proc.stderr[-3000:])
            raise SystemExit("pytest produced no results; nothing is reported (a check that did not run is NOT RUN)")
        results = json.loads(res_json.read_text())
    stamp = started.isoformat()
    rows, seen = [], set()
    for e in results:
        cid = check_id(e["name"], e.get("param"))
        if cid in seen:
            cid = f"{cid}@{e['nodeid']}"
        seen.add(cid)
        result, executed, evidence = classify(e)
        prefix = cid.split("-", 1)[0]
        category = "QA harness self-test" if cid.startswith("W-SELF") else CATEGORY.get(prefix, "Other")
        rows.append({"Check_ID": cid, "Category": category,
                     "Description": e["doc"] or e["name"], "Executed": "TRUE" if executed else "FALSE",
                     "Executed_At": stamp, "Result": result, "Evidence": evidence.replace("\n", " ")[:1500],
                     "Tool": f"pytest {e['nodeid']}"})
    for cid, cat, desc, why in PLANNED_MANUAL:
        rows.append({"Check_ID": cid, "Category": cat, "Description": desc, "Executed": "FALSE", "Executed_At": stamp,
                     "Result": CheckResult.NOT_RUN.value, "Evidence": f"NOT RUN: {why}", "Tool": "manual (05-qa)"})
    problems = validate_rows(VALIDATION_RESULTS, rows, allow_synthetic=True)
    if problems:
        raise SystemExit("validation_results rows fail the schema:\n  " + "\n  ".join(problems[:20]))
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[c.name for c in VALIDATION_RESULTS.columns])
        w.writeheader()
        w.writerows(rows)
    counts = {r: sum(1 for x in rows if x["Result"] == r) for r in CheckResult.values()}
    executed = sum(1 for x in rows if x["Executed"] == "TRUE")
    meta = {"started": stamp, "workbook": env.get("QA_WORKBOOK", "fresh test build" + (f" --only {args.only}" if args.only else "")),
            "suites": args.suites, "checks": len(rows), "executed": executed, "counts": counts,
            "pytest_exit": proc.returncode}
    (out.parent / "validation_run.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {out}: {len(rows)} checks, executed {executed}, " +
          ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"validated: {meta['workbook']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workbook", help="validate this generated .xlsx instead of a fresh test build")
    ap.add_argument("--only", choices=["01-data", "02-valuation", "03-nav", "04-charts"])
    ap.add_argument("--suites", nargs="+", default=list(SUITES), choices=list(SUITES))
    ap.add_argument("--out", default=str(ROOT / VALIDATION_RESULTS.csv_path))
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
