"""I layer on real canonical data (01-data) and the provenance audit's automated part (R002, D-016).

Every test is NOT RUN until data/canonical/ holds the relevant CSVs. The sampled manual audit of
values against the cited documents is qa/provenance_audit.md.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

import pytest

from src.common import schema as S
from src.fund_nav.model import HoldingLine
from tests.independent._support import diff_fields
from tests.independent.cleanroom import nav as QN

ROOT = Path(__file__).resolve().parents[2]


def _rows(table: S.Table) -> list[dict] | None:
    p = ROOT / table.csv_path
    if not p.exists():
        return None
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _need(*tables: S.Table) -> list[list[dict]]:
    out = []
    for t in tables:
        rows = _rows(t)
        if not rows:
            pytest.skip(f"NOT RUN: {t.csv_path} not present or empty (01-data not merged)")
        if any("SYNTHETIC" in str(v).upper() for r in rows for v in r.values()):
            pytest.skip(f"NOT RUN: {t.csv_path} holds synthetic fixture rows, not real data")
        out.append(rows)
    return out


def test_PROV_01_every_source_id_traces_to_log_and_manifest(record_property):
    """R002: Source_ID -> source_log -> source_manifest for every canonical row."""
    log, man = _need(S.SOURCE_LOG, S.SOURCE_MANIFEST)
    log_ids = {r["Source_ID"] for r in log}
    doc_ids = {r["Source_Doc_ID"] for r in man}
    broken, n = [], 0
    for t in S.ALL_TABLES:
        if not t.csv_path or t.key in ("source_log", "source_manifest") or not t.csv_path.startswith("data/"):
            continue
        for i, r in enumerate(_rows(t) or [], start=2):
            for c, v in r.items():
                if c.endswith("Source_ID") and v:
                    n += 1
                    if v not in log_ids:
                        broken.append((t.csv_path, i, c, v))
    broken += [("source_log", r["Source_ID"], "Source_Doc_ID", r["Source_Doc_ID"]) for r in log if r["Source_Doc_ID"] not in doc_ids]
    broken += [("source_log", r["Source_ID"], "missing URL/page/unit/period") for r in log
               if not (r["URL_or_File_Path"] and r["Page_or_Table"] and r["Unit"])]
    record_property("qa_evidence", f"{n} Source_ID references, {len(log)} log rows, {len(man)} documents; {len(broken)} broken")
    assert broken == [], broken[:20]


def test_PROV_02_manifest_sha256_matches_raw_files(record_property):
    (man,) = _need(S.SOURCE_MANIFEST)
    bad, checked = [], 0
    for r in man:
        if not r.get("Local_Path"):
            if not r.get("URL"):
                bad.append((r["Source_Doc_ID"], "neither a local file nor a URL"))
            continue
        p = ROOT / r["Local_Path"]
        if not p.exists():
            bad.append((r["Source_Doc_ID"], "file missing", r["Local_Path"]))
            continue
        checked += 1
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h.lower() != (r.get("SHA256") or "").lower():
            bad.append((r["Source_Doc_ID"], "SHA256 mismatch", r["Local_Path"]))
    record_property("qa_evidence", f"{checked} local files hashed of {len(man)} documents; {len(bad)} problems")
    assert bad == [], bad[:20]


def _real_lines(fund_id: str, price_date: str):
    holdings, registry, prices = _need(S.FUND_HOLDINGS, S.SECURITY_REGISTRY, S.MARKET_PRICES)
    reg = {r["Security_ID"] for r in registry}
    px = {r["Security_ID"]: float(r["Close_INR"]) for r in prices if r["Price_Date"] == price_date}
    snap = [r for r in holdings if r["Fund_ID"] == fund_id]
    if not snap:
        pytest.skip(f"NOT RUN: no holdings for {fund_id}")
    latest = max(r["Portfolio_Date"] for r in snap)
    lines = []
    for r in snap:
        if r["Portfolio_Date"] != latest:
            continue
        sid = r["Security_ID"] or None
        lines.append(HoldingLine(line_id=r["Holding_Line_ID"], line_role=r["Line_Role"], asset_class=r["Asset_Class"],
                                 sector=r["Sector"], weight=float(r["Weight_Pct_of_Scheme_NAV"]),
                                 market_value_inr_cr=float(r["Market_Value_INR_Cr"]),
                                 security_id=sid if sid in reg else None,
                                 quantity=float(r["Quantity_Held"]) if r["Quantity_Held"] else None,
                                 price_inr=px.get(sid), scenario_price_inr=px.get(sid)))
    return lines, date.fromisoformat(latest)


@pytest.mark.parametrize("fund_id", ["MF001", "MF002"])
def test_I_REAL_01_holdings_coverage_on_real_snapshot(fund_id, record_property):
    """G1: one complete source-backed snapshot per fund with Holdings_Coverage_Status = PASS, computed
    by the clean-room and compared with the 03-nav reference (when merged)."""
    gi = {r["Name"]: r["Value"] for r in (_rows(S.GLOBAL_INPUTS) or [])}
    if not gi.get("in_Price_Date"):
        pytest.skip("NOT RUN: in_Price_Date not set in data/reference/global_inputs.csv")
    lines, pdt = _real_lines(fund_id, gi["in_Price_Date"])
    (totals,) = _need(S.FUND_SCHEME_TOTALS)
    rep = [float(r["Reported_Scheme_Net_Assets_INR_Cr"]) for r in totals if r["Fund_ID"] == fund_id
           and r["Portfolio_Date"] == pdt.isoformat()]
    assert rep, f"no reported scheme net assets for {fund_id} at {pdt}"
    tol = float(gi.get("in_Recon_Tolerance_Pct") or 0.005)
    mine = QN.holdings_coverage(lines, rep[0], tol)
    record_property("qa_evidence", f"{fund_id} @ {pdt}: value coverage {mine.value_coverage_pct:.4%}, match "
                                   f"{mine.match_pct:.4%}, recon {mine.recon_status}, unmatched {mine.unmatched_line_ids[:10]}")
    from src.fund_nav.coverage import holdings_coverage
    try:
        worker = holdings_coverage(lines, rep[0], tol)
    except NotImplementedError:
        worker = None
    if worker is not None:
        assert diff_fields(worker, mine) == {}
    assert mine.status == "PASS", mine
