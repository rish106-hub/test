"""Monthly portfolio-disclosure import (spec <monthly_update_workflow>).

One parser per AMC layout (both layouts verified on the 30-Sep-2026 files):
  MF001  PPFAS Mutual Fund, single-scheme workbook `PPFCF_...xlsx` (sheet PPFCF)
         columns: A code | B name | C ISIN | D industry/rating | E quantity | F market value (Rs lakh) | G % to net assets (fraction)
  MF002  HDFC Mutual Fund, `Monthly HDFC Mid Cap Fund - <date>.xlsx` (sheet MIDCAP)
         columns: B ISIN | D name | E industry/rating | F quantity | G market value (Rs lacs) | H % to NAV (percent)

Line_Role policy (documented in src/ingestion/MODULE.md):
  * POSITION      exchange-listed equity, REIT/InvIT and foreign listed equity: they have a quantity and an
                  exchange close, so Method 2 can mark them (contract §7.3).
  * ONA_ASSET     TREPS/reverse repo, positive net receivables, and the instruments that have no exchange
                  close: certificates of deposit, commercial paper, treasury bills, units of another mutual
                  fund. They enter net assets at the AMC's disclosed fair value and carry adjustment 0,
                  as contract §7.0 prescribes for CARRYING_VALUE / MARKET_PASS_THROUGH lines.
  * ONA_LIABILITY net payables / negative net current assets (stored negative).
Futures positions disclosed in the derivatives annex are not part of net assets (marked to market and
settled daily); they are not imported as lines and are listed under Limitations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from src.common.enums import DataStatus
from src.common.units import lakh_to_crore

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


@dataclass(frozen=True)
class ImportDiff:
    added: tuple[str, ...]        # Security_IDs new this month
    removed: tuple[str, ...]      # Security_IDs no longer held
    unmatched_isins: tuple[str, ...]  # not in registry: need a registry row and a valuation status
    weight_sum: float
    weight_sum_status: str        # PASS | WARNING (outside 1 +/- in_Weight_Sum_Tol)


# ----------------------------------------------------------------------------- helpers
def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _txt(v) -> str:
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


def _clean_industry(text: str) -> str:
    return re.sub(r"\s*#+\s*$", "", _txt(text)).strip()


def _fmt(x: float, nd: int = 10) -> str:
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))


def _raw(v: float) -> str:
    """Raw numeric cell as printed in the file (no float noise beyond what the file holds)."""
    return repr(float(v)) if v != int(v) else str(int(v))


def load_sheet_rows(path: Path) -> list[tuple]:
    """First worksheet of an .xlsx file (the AMCs sometimes name it .xls) as value tuples."""
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # openpyxl rejects the .xls extension although the content is OOXML; read via a file object.
        with open(path, "rb") as fh:
            wb = openpyxl.load_workbook(fh, data_only=True, read_only=False)
    ws = wb.worksheets[0]
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def _portfolio_date(rows: Sequence[tuple]) -> date:
    for r in rows[:6]:
        for c in r:
            t = _txt(c)
            m = re.search(r"as on ([A-Za-z]+ \d{1,2}, \d{4})", t)
            if m:
                return datetime.strptime(m.group(1), "%B %d, %Y").date()
            m = re.search(r"as on (\d{1,2}-[A-Za-z]{3}-\d{4})", t)
            if m:
                return datetime.strptime(m.group(1), "%d-%b-%Y").date()
    raise ValueError("portfolio date not found in header rows")


# ----------------------------------------------------------------------------- layouts
def _parse_ppfas(rows: Sequence[tuple]) -> tuple[list[dict], dict]:
    """Returns raw line dicts and totals."""
    lines: list[dict] = []
    section = ""
    sub = ""
    grand = None
    grand_row = None
    for rn, r in enumerate(rows, start=1):
        r = tuple(r) + (None,) * 8
        a, b, c, d, e, f, g = (r[i] for i in range(7))
        name = _txt(b)
        if name.startswith("GRAND TOTAL"):
            grand, grand_row = _num(f), rn
            break
        if name in ("Equity & Equity related", "Equity & Equity related Foreign Investments",
                    "Money Market Instruments", "Others"):
            section, sub = name, ""
            continue
        if section == "Equity & Equity related" and name in ("(a) Listed / awaiting listing on Stock Exchanges",
                                                            "Arbitrage", "(b) Reits", "(c) Unlisted"):
            sub = name
            continue
        if section == "Equity & Equity related Foreign Investments" and name.startswith("("):
            sub = name
            continue
        if name in ("Certificate of Deposit", "Commercial Paper", "Treasury Bill", "Mutual Fund Units",
                    "Reverse Repo / TREPS"):
            sub = name
            continue
        if name.startswith("Net Receivables"):
            section, sub = "NET", ""
        mv = _num(f)
        if mv is None or name in ("", "Sub Total", "Total") or name.startswith("Sub Total"):
            continue
        isin = _txt(c)
        lines.append({
            "row": rn, "section": section, "sub": sub, "code": _txt(a), "name": name,
            "isin": isin if ISIN_RE.match(isin) else "", "industry": _clean_industry(d),
            "qty": _num(e), "mv_lakh": mv, "weight_disclosed": _num(g) if not isinstance(g, str) else None,
            "weight_text": _txt(g),
        })
    return lines, {"net_assets_lakh": grand, "grand_row": grand_row}


def _parse_hdfc(rows: Sequence[tuple]) -> tuple[list[dict], dict]:
    lines: list[dict] = []
    section = ""
    grand = None
    grand_row = None
    for rn, r in enumerate(rows, start=1):
        r = tuple(r) + (None,) * 10
        b, d, e, f, g, h = (r[i] for i in (1, 3, 4, 5, 6, 7))
        head = _txt(b)
        if head.startswith("Grand Total"):
            grand, grand_row = _num(g), rn
            break
        if head in ("EQUITY & EQUITY RELATED", "MONEY MARKET INSTRUMENTS", "OTHERS"):
            section = head
            continue
        mv = _num(g)
        if mv is None or head in ("Sub Total", "Total"):
            continue
        isin = head if ISIN_RE.match(head) else ""
        name = _txt(d)
        if not name:
            continue
        lines.append({
            "row": rn, "section": section, "sub": "", "code": "", "name": name, "isin": isin,
            "industry": _clean_industry(e), "qty": _num(f), "mv_lakh": mv,
            "weight_disclosed": (_num(h) / 100.0) if _num(h) is not None else None,
            "weight_text": _txt(h),
        })
    return lines, {"net_assets_lakh": grand, "grand_row": grand_row}


def _classify(fund_id: str, ln: dict) -> tuple[str, str]:
    """(Line_Role, Asset_Class) from the AMC section a line sits in."""
    sec, sub = ln["section"], ln["sub"]
    if fund_id == "MF001":
        if sec == "Equity & Equity related":
            if sub == "(b) Reits":
                return "POSITION", "REITs and InvITs"
            return "POSITION", "Indian listed equity"
        if sec == "Equity & Equity related Foreign Investments":
            return "POSITION", "Foreign listed equity"
        if sec == "Money Market Instruments":
            return "ONA_ASSET", "Money-market instruments"
        if sec == "Others" and sub == "Mutual Fund Units":
            return "ONA_ASSET", "Other eligible investments"
        if sec == "Others" and sub == "Reverse Repo / TREPS":
            return "ONA_ASSET", "Cash and cash equivalents"
        if sec == "NET":
            return ("ONA_ASSET" if ln["mv_lakh"] >= 0 else "ONA_LIABILITY"), "Cash and cash equivalents"
    elif fund_id == "MF002":
        if sec == "EQUITY & EQUITY RELATED":
            return "POSITION", "Indian listed equity"
        if sec == "MONEY MARKET INSTRUMENTS":
            return "ONA_ASSET", "Cash and cash equivalents"        # TREPS
        if sec == "OTHERS":
            return ("ONA_ASSET" if ln["mv_lakh"] >= 0 else "ONA_LIABILITY"), "Cash and cash equivalents"
    raise ValueError(f"{fund_id}: cannot classify line {ln['name']!r} in section {sec!r}/{sub!r}")


def read_disclosure(fund_id: str, path: Path) -> tuple[date, list[dict], dict]:
    rows = load_sheet_rows(Path(path))
    pdate = _portfolio_date(rows)
    if fund_id == "MF001":
        lines, totals = _parse_ppfas(rows)
    elif fund_id == "MF002":
        lines, totals = _parse_hdfc(rows)
    else:
        raise ValueError(f"no parser for fund {fund_id}")
    if not totals["net_assets_lakh"]:
        raise ValueError(f"{path}: grand total row not found")
    return pdate, lines, totals


def parse_disclosure(fund_id: str, path: Path, source_id: str, import_batch_id: str, *,
                     sector_of=None, status: str = DataStatus.IMPORTED_UNRECONCILED.value,
                     registry: Sequence[Mapping] | None = None) -> list[dict]:
    """AMC monthly portfolio file -> fund_holdings rows (schema.FUND_HOLDINGS stored columns).

    Converts lakh to crore, keeps Raw_Market_Value/Raw_Market_Value_Unit, assigns Line_Role.
    Weight_Pct_of_Scheme_NAV = line value / the file's own grand total (full precision); the rounded
    weight printed by the AMC is only used by `reconcile` as a cross-check. Security_ID is filled from
    `registry` by ISIN when one is supplied, else left blank (the caller registers new securities).
    `sector_of(industry, asset_class)` maps the AMC industry label to the Sector vocabulary.
    `status` is the Data_Status written to every row (reconciliation upgrades it afterwards).
    """
    from src.ingestion.registry import match_security
    pdate, lines, totals = read_disclosure(fund_id, Path(path))
    total_cr = lakh_to_crore(totals["net_assets_lakh"])
    out: list[dict] = []
    for n, ln in enumerate(lines, start=1):
        role, asset_class = _classify(fund_id, ln)
        mv_cr = lakh_to_crore(ln["mv_lakh"])
        unit = "INR lakh"
        sector = "Not applicable" if role != "POSITION" else (sector_of(ln["industry"], asset_class) if sector_of else "Other Sectors")
        sid = ""
        if registry is not None and ln["isin"] and role == "POSITION":
            sid = match_security(ln["isin"], None, registry) or ""
        out.append({
            "Holding_Line_ID": f"{fund_id}-{pdate.isoformat()}-{n:04d}",
            "Fund_ID": fund_id,
            "Portfolio_Date": pdate.isoformat(),
            "Line_Role": role,
            "Security_ID": sid,
            "ISIN": ln["isin"],
            "Instrument_Name_As_Disclosed": ln["name"],
            "Company_Name": "",
            "Sector": sector,
            "Industry": ln["industry"],
            "Asset_Class": asset_class,
            "Country_or_Market": "United States" if asset_class == "Foreign listed equity" else ("India" if role == "POSITION" else ""),
            "Trading_Currency": "USD" if asset_class == "Foreign listed equity" else ("INR" if role == "POSITION" else ""),
            "FX_Rate_to_INR": "",
            "Quantity_Held": _raw(ln["qty"]) if ln["qty"] is not None else "",
            "Market_Value_INR_Cr": _fmt(mv_cr),
            "Raw_Market_Value": _raw(ln["mv_lakh"]),
            "Raw_Market_Value_Unit": unit,
            "Weight_Pct_of_Scheme_NAV": _fmt(mv_cr / total_cr, 12),
            "Source_ID": source_id,
            "Import_Batch_ID": import_batch_id,
            "Data_Status": status,
        })
    return out


def disclosed_totals(fund_id: str, path: Path) -> dict:
    """Reported scheme net assets (INR crore), portfolio date and the AMC's own printed weights."""
    pdate, lines, totals = read_disclosure(fund_id, Path(path))
    return {"portfolio_date": pdate, "net_assets_lakh": totals["net_assets_lakh"], "grand_row": totals["grand_row"],
            "net_assets_cr": lakh_to_crore(totals["net_assets_lakh"]), "lines": lines}


def reconcile(rows: Sequence[Mapping], reported_net_assets_cr: float, tolerance: float) -> dict:
    """Imported value vs reported net assets, weight sum, unmatched POSITION lines."""
    imported = sum(float(r["Market_Value_INR_Cr"]) for r in rows)
    wsum = sum(float(r["Weight_Pct_of_Scheme_NAV"]) for r in rows)
    gap = (imported - reported_net_assets_cr) / reported_net_assets_cr
    unmatched = [r["Holding_Line_ID"] for r in rows if r["Line_Role"] == "POSITION" and not r["Security_ID"]]
    return {"imported_cr": imported, "reported_cr": reported_net_assets_cr, "gap_pct": gap,
            "recon_status": "PASS" if abs(gap) <= tolerance else "FAIL",
            "weight_sum": wsum, "weight_sum_status": "PASS" if abs(wsum - 1) <= tolerance else "WARNING",
            "unmatched_lines": unmatched, "n_lines": len(rows)}


def diff_portfolios(previous: Sequence[Mapping], current: Sequence[Mapping], tolerance: float) -> ImportDiff:
    def positions(rows):
        return [r for r in rows if (r.get("Line_Role") or "POSITION") == "POSITION"]

    prev_ids = {r["Security_ID"] for r in positions(previous) if (r.get("Security_ID") or "").strip()}
    cur_ids = {r["Security_ID"] for r in positions(current) if (r.get("Security_ID") or "").strip()}
    unmatched = sorted({(r.get("ISIN") or "").strip() for r in positions(current)
                        if not (r.get("Security_ID") or "").strip() and (r.get("ISIN") or "").strip()})
    wsum = sum(float(r["Weight_Pct_of_Scheme_NAV"]) for r in current if (r.get("Weight_Pct_of_Scheme_NAV") or "") != "")
    status = "PASS" if abs(wsum - 1.0) <= tolerance else "WARNING"
    return ImportDiff(tuple(sorted(cur_ids - prev_ids)), tuple(sorted(prev_ids - cur_ids)), tuple(unmatched),
                      wsum, status)
