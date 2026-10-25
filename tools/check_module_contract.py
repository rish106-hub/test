"""Accept or reject a worker's module against spec/module_contracts.toml (D-027).

usage: python tools/check_module_contract.py <worker-id> [--manifest PATH] [--run-tests]

  --manifest   build/out/manifest.json from a build that includes the worker
               (e.g. `python build/generate_workbook.py --test-build --only 03-nav`)
  --run-tests  also run the worker's contract tests with --strict-impl

Exit code 0 = accepted. Every problem is printed; 00-main sends the list back to the owner.
Ownership of changed files is a separate check: tools/check_ownership.py.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import schema as S  # noqa: E402
from src.common.validate import validate_csv  # noqa: E402

CONTRACTS = ROOT / "spec" / "module_contracts.toml"
DOC_SECTIONS = ("Inputs", "Outputs", "Assumptions", "Limitations", "Tests")


def load_contracts() -> dict:
    with CONTRACTS.open("rb") as fh:
        return tomllib.load(fh)["modules"]


def _matches(name: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def schema_for_excel_table(name: str) -> S.Table | None:
    for t in S.ALL_TABLES:
        if t.excel_name == name or ("<" in t.excel_name and fnmatch.fnmatchcase(name, re.sub(r"<[^>]+>", "*", t.excel_name))):
            return t
    return None


def check_manifest(worker: str, c: dict, manifest: dict) -> list[str]:
    problems = []
    built = {n: t for n, t in manifest["tables"].items() if t["owner"] == worker}
    stubbed = {n for n, t in manifest["tables"].items() if t["owner"] == "STUB"}
    for name in c["builds_tables"]:
        if name not in built:
            problems.append(f"missing interface table {name}" + (" (stubbed)" if name in stubbed else ""))
    for name, t in built.items():
        if name in c["builds_tables"]:
            sch = schema_for_excel_table(name)
            if sch is not None and t["columns"] != [col.name for col in sch.columns]:
                exp = [col.name for col in sch.columns]
                missing = [x for x in exp if x not in t["columns"]]
                extra = [x for x in t["columns"] if x not in exp]
                problems.append(f"{name}: columns differ from schema '{sch.key}'"
                                f" (missing {missing}, extra {extra}, or order differs)")
        elif not _matches(name, c["private_tables"]):
            problems.append(f"undeclared table {name}: add it to builds_tables by change request, "
                            f"or name it to match a private pattern {c['private_tables']}")
    for name, n in manifest["names"].items():
        if n["owner"] == worker and not _matches(name, c["defines_names"]):
            problems.append(f"undeclared defined name {name} (allowed: {c['defines_names']})")
    refs = manifest.get("references", {}).get(worker, {"tables": [], "names": []})
    for t in refs["tables"]:
        if t not in built and not _matches(t, c["consumes"]):
            problems.append(f"references {t}, which is neither built by {worker} nor in its consumes list")
    for n in refs["names"]:
        own = manifest["names"].get(n, {}).get("owner") == worker
        if not own and not _matches(n, c["consumes"]):
            problems.append(f"references name {n}, which is neither defined by {worker} nor in its consumes list")
    for t in refs["tables"]:
        tw = manifest["tables"].get(t, {}).get("owner")
        other = load_contracts().get(tw, {}) if tw not in (None, "STUB", worker) else {}
        if other and t not in other.get("builds_tables", []) and _matches(t, other.get("private_tables", [])):
            problems.append(f"references {t}, a private table of {tw}")
    return problems


def check_functions(c: dict) -> list[str]:
    problems = []
    for spec in c["reference_functions"]:
        mod, fn = spec.split(":")
        try:
            obj = getattr(importlib.import_module(mod), fn)
        except (ImportError, AttributeError) as e:
            problems.append(f"reference function {spec} not importable: {e}")
            continue
        if not callable(obj):
            problems.append(f"reference function {spec} is not callable")
    return problems


def check_doc(c: dict) -> list[str]:
    if not c["module_doc"]:
        return []
    path = ROOT / c["module_doc"]
    if not path.exists():
        return [f"{c['module_doc']} missing"]
    text = path.read_text(encoding="utf-8")
    problems = []
    for sec in DOC_SECTIONS:
        m = re.search(rf"^## {sec}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        body = m.group(1) if m else ""
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
        if not m:
            problems.append(f"{c['module_doc']}: section '## {sec}' missing")
        elif not body or "TODO" in body:
            problems.append(f"{c['module_doc']}: section '## {sec}' is empty or still has TODO")
    return problems


def check_csvs(c: dict) -> list[str]:
    problems = []
    for key in c["writes_csv"]:
        t = S.TABLES[key]
        path = ROOT / t.csv_path
        if not path.exists():
            problems.append(f"{t.csv_path} missing (writes_csv '{key}')")
        else:
            problems += validate_csv(t, path)
    return problems


def run_tests(c: dict) -> list[str]:
    if not c["contract_tests"]:
        return []
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--strict-impl", *c["contract_tests"]],
                       cwd=ROOT, capture_output=True, text=True)
    return [] if r.returncode == 0 else ["contract tests fail under --strict-impl:\n" + r.stdout[-3000:]]


def check(worker: str, manifest: dict | None, tests: bool) -> list[str]:
    c = load_contracts()[worker]
    problems = check_doc(c) + check_functions(c) + check_csvs(c)
    if manifest is not None:
        problems += check_manifest(worker, c, manifest)
    if tests:
        problems += run_tests(c)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worker", choices=sorted(load_contracts()))
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--run-tests", action="store_true")
    a = ap.parse_args(argv)
    manifest = json.loads(a.manifest.read_text()) if a.manifest else None
    problems = check(a.worker, manifest, a.run_tests)
    for p in problems:
        print(f"REJECT {a.worker}: {p}")
    if not problems:
        print(f"module contract OK for {a.worker}" + ("" if manifest else " (no manifest given: workbook interface not checked)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
