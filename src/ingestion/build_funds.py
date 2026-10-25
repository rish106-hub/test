"""Wave 1 build, part 1: registry, fund holdings, scheme totals, fund plans, official NAV, market prices.

Re-runnable and deterministic: reads only files under data/raw/ (plus the hash-only documents listed in
HASH_ONLY, whose SHA256 was computed when they were retrieved), writes the canonical CSVs and appends
document / log rows through SourceBook. Run:  python -I -m src.ingestion.build_funds
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.common.schema import TABLES  # noqa: E402
from src.common.validate import validate_csv  # noqa: E402
from src.ingestion import classification as cls  # noqa: E402
from src.ingestion.holdings_import import (diff_portfolios, disclosed_totals, parse_disclosure,  # noqa: E402
                                           reconcile)
from src.ingestion.nav_import import parse_amfi_nav  # noqa: E402
from src.ingestion.registry import match_security, next_security_id  # noqa: E402
from src.ingestion.sources import SourceBook, read_csv, write_csv  # noqa: E402

RETRIEVED = "2026-10-25"
PRICE_DATE = "2026-10-23"
CANON = ROOT / "data" / "canonical"
RECON_TOL = 0.005          # in_Recon_Tolerance_Pct / in_Weight_Sum_Tol default (data/reference/global_inputs.csv)
VERIFIED = "Retrieved and verified"
UNRECON = "Imported but not yet reconciled"
USER_ASSUMPTION = "User assumption"

FUND_FILES = {
    "MF001": ("data/raw/MF001/PPFCF_PPFAS_Monthly_Portfolio_Report_September_30_2026.xlsx",
              "data/raw/MF001/PPFCF_PPFAS_Monthly_Portfolio_Report_August_31_2026.xlsx", "PPFCF"),
    "MF002": ("data/raw/MF002/Monthly_HDFC_Mid_Cap_Fund_-_30_September_2026.xlsx",
              "data/raw/MF002/Monthly_HDFC_Mid_Cap_Fund_-_31_August_2026.xlsx", "MIDCAP"),
}
NSE_ZIP = "data/raw/prices/BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv.zip"
RBI_PAGE = "data/raw/fx/RBI_home_page_2026-10-25.html"
NAVALL = "data/raw/amfi/NAVAll_retrieved_2026-10-25.txt"
NAV_HISTORY = {"MF001": "data/raw/MF001/amfi_nav_history_ppfas_flexicap_extract.txt",
               "MF002": "data/raw/MF002/amfi_nav_history_hdfc_midcap_extract.txt"}

# hash-only documents (licence terms: personal / non-commercial use only; not redistributed in the repo)
FOREIGN = {  # ISIN -> (Nasdaq symbol, sha256 of the retrieved JSON for 2026-10-15..10-25, Sep-30 check JSON sha)
    "US02079K3059": ("GOOGL", "326b8289ad8b67ca0c5b503d2e91642bbf71a3ceb21b05c84519176afd9ccbb0", "018c599a6ec0c32f41701b19202c594e9b98e6021a9085bd31c1739977bb2afe", "320.21", "344.08"),
    "US30303M1027": ("META", "2aa50b19c464f0f7e38d11dcad730839320a6d28768327fd63f720fdfc16c900", "0de401babe4f3656318bde0614e635facc85fa8dfed0a6ed96b2d07b8f5e4ea8", "642.62", "725.18"),
    "US5949181045": ("MSFT", "ce86ed8b2c6caa87217cae5b34e7b768561a2562665f076d9d58d565b7e7ba24", "19d1db7a1dcb0a6beac125cb3cf718802dae9f1aae52f5f4b4fd3fe35d328968", "524.51", "512.9"),
    "US0231351067": ("AMZN", "cf240554b0788a5c6beddaccf526b6db64187e54bd9d6d69a0b672b943e051ce", "e7d20018d5619b240a89e0858becd9f1829c95752414b756c16c69700d37e65d", "248.00", "249.15"),
}
FX_USD_INR = "94.9432"      # RBI home page, "INR / 1 USD : 94.9432 (As at 1.00pm of October 23, 2026) (Source : FBIL)"

SEEDS = ["C001", "C002", "C003", "C004", "C005", "C006", "C007"]
SEED_ISIN = {"C001": "INE040A01034", "C002": "INE171A01029", "C003": "INE949L01017", "C004": "INE562A01011",
             "C005": "INE090A01021", "C006": "INE237A01036", "C007": "INE180A01020"}

PLANS = [  # Plan_ID, Fund_ID, scheme name as AMFI prints it, AMC, plan, option, AMFI code
    ("MF001-DIR-GR", "MF001", "Parag Parikh Flexi Cap Fund", "PPFAS Mutual Fund", "Direct", "Growth", "122639"),
    ("MF001-REG-GR", "MF001", "Parag Parikh Flexi Cap Fund", "PPFAS Mutual Fund", "Regular", "Growth", "122640"),
    ("MF002-DIR-GR", "MF002", "HDFC Mid Cap Fund", "HDFC Mutual Fund", "Direct", "Growth", "118989"),
    ("MF002-REG-GR", "MF002", "HDFC Mid Cap Fund", "HDFC Mutual Fund", "Regular", "Growth", "105758"),
]
BENCHMARK = {"MF001": "Nifty 500 (TRI)", "MF002": "NIFTY Midcap 150 TRI"}


def load_nse() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with zipfile.ZipFile(ROOT / NSE_ZIP) as z:
        rows = csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8"))
        for r in rows:
            cur = out.get(r["ISIN"])
            if cur is None or (r["SctySrs"] == "EQ" and cur["SctySrs"] != "EQ"):
                out[r["ISIN"]] = r
    return out


def build() -> dict:
    book = SourceBook()
    report: dict = {"funds": {}}
    scope = {r["Entity_ID"]: r for r in read_csv(ROOT / "data/reference/initial_scope.csv")}
    nse = load_nse()

    # ---------------------------------------------------------------- documents
    doc = {}
    doc["MF001"] = book.add_doc(
        entity="MF001", name="PPFAS Flexi Cap Fund monthly portfolio statement, 30 Sep 2026", doc_type="Portfolio disclosure",
        tier="2", url="https://amc.ppfas.com/downloads/portfolio-disclosure/2026/PPFCF_PPFAS_Monthly_Portfolio_Report_September_30_2026.xlsx",
        local_path=FUND_FILES["MF001"][0], period="2026-09-30", retrieved=RETRIEVED,
        note="PPFAS Mutual Fund website, statutory monthly portfolio disclosure. Publication date is not stated in the file.")
    doc["MF001_prev"] = book.add_doc(
        entity="MF001", name="PPFAS Flexi Cap Fund monthly portfolio statement, 31 Aug 2026", doc_type="Portfolio disclosure",
        tier="2", url="https://amc.ppfas.com/downloads/portfolio-disclosure/2026/PPFCF_PPFAS_Monthly_Portfolio_Report_August_31_2026.xlsx",
        local_path=FUND_FILES["MF001"][1], period="2026-08-31", retrieved=RETRIEVED,
        note="Prior-month disclosure, used only for the month-on-month diff.")
    doc["MF002"] = book.add_doc(
        entity="MF002", name="HDFC Mid Cap Fund monthly portfolio, 30 Sep 2026", doc_type="Portfolio disclosure", tier="2",
        url="https://files.hdfcfund.com/s3fs-public/2026-10/Monthly%20HDFC%20Mid%20Cap%20Fund%20-%2030%20September%202026.xlsx",
        local_path=FUND_FILES["MF002"][0], period="2026-09-30", retrieved=RETRIEVED,
        note="HDFC Mutual Fund file host. www.hdfcfund.com returned HTTP 403 (Access Denied) to every request, so the file URL was built from the AMC's naming pattern and the content verified (scheme name, date, totals). Publication date not stated.")
    doc["MF002_prev"] = book.add_doc(
        entity="MF002", name="HDFC Mid Cap Fund monthly portfolio, 31 Aug 2026", doc_type="Portfolio disclosure", tier="2",
        url="https://files.hdfcfund.com/s3fs-public/2026-09/Monthly%20HDFC%20Mid%20Cap%20Fund%20-%2031%20August%202026.xlsx",
        local_path=FUND_FILES["MF002"][1], period="2026-08-31", retrieved=RETRIEVED,
        note="Prior-month disclosure, used only for the month-on-month diff.")
    doc["nse"] = book.add_doc(
        entity="MARKET", name="NSE CM UDiFF Common Bhavcopy, trade date 2026-10-23", doc_type="Price file", tier="2",
        url="https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv.zip", local_path=NSE_ZIP,
        pub_date="2026-10-23", period="2026-10-23", retrieved=RETRIEVED,
        note="NSE public end-of-day report (nsearchives.nseindia.com). www.nseindia.com itself returns HTTP 403. Unadjusted as-traded closes.")
    doc["rbi"] = book.add_doc(
        entity="MARKET", name="RBI home page: current rates and FBIL reference rate, as at 1.00pm of 23 Oct 2026", doc_type="FX rate", tier="2",
        url="https://www.rbi.org.in/", local_path=RBI_PAGE, pub_date="2026-10-23", period="2026-10-23", retrieved=RETRIEVED,
        note="Page captured on 2026-10-25; it states the FBIL reference rate of 23 Oct 2026. The RBI archive form (ReferenceRateArchive.aspx) needs a POST and was not used.")
    doc["navall"] = book.add_doc(
        entity="AMFI", name="AMFI NAVAll.txt as retrieved 2026-10-25", doc_type="NAV file", tier="2",
        url="https://www.amfiindia.com/spages/NAVAll.txt", local_path=NAVALL, pub_date="2026-10-23", period="2026-10-23", retrieved=RETRIEVED,
        note="Redirects to portal.amfiindia.com/spages/NAVAll.txt. Latest NAV date in the file for the four schemes: 23-Oct-2026.")
    nasdaq_docs = {}
    for isin, (sym, sha_oct, sha_sep, _, _) in FOREIGN.items():
        nasdaq_docs[isin] = book.add_doc(
            entity="MARKET", name=f"Nasdaq.com historical quotes API, {sym}, 2026-10-15..2026-10-25", doc_type="Price file", tier="3",
            url=f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass=stocks&fromdate=2026-10-15&todate=2026-10-25&limit=10",
            sha256=sha_oct, pub_date="2026-10-23", period="2026-10-15..2026-10-25", retrieved=RETRIEVED,
            note="Tier 3 third-party market data. Hash only: Nasdaq's terms permit personal, non-commercial use, so the JSON is not redistributed in this repository. Local copy kept outside the repo for audit.")
    book.save()

    # ---------------------------------------------------------------- holdings parse (latest month)
    parsed = {}
    for fid, (cur, prev, _) in FUND_FILES.items():
        parsed[fid] = disclosed_totals(fid, ROOT / cur)

    # ---------------------------------------------------------------- registry
    registry: list[dict] = []
    # seeds first (S00001..S00007 follow C001..C007)
    for ent in SEEDS:
        sc = scope[ent]
        sid = next_security_id(registry)
        isin = SEED_ISIN[ent]
        n = nse[isin]
        registry.append({
            "Security_ID": sid, "Entity_ID": ent, "ISIN": isin, "Exchange_Ticker": n["TckrSymb"], "Company_Name": sc["Company_Name"],
            "Sector": sc["Sector"], "Industry": "", "Business_Model": sc["Business_Model"], "Asset_Class": "Indian listed equity",
            "Country_or_Market": "India", "Trading_Currency": "INR", "Reporting_Currency": "INR", "Ownership_Type": sc["Ownership_Type"],
            "Listing_Status": "Listed", "Primary_Valuation_Method": sc["Primary_Valuation_Method"], "Secondary_Valuation_Method": "",
            "Dedicated_Sheet": sc["Dedicated_Sheet"], "Source_Status": USER_ASSUMPTION, "Source_ID": "",
        })
    id_src = {}   # Source_ID for identifiers (NSE row) set after log creation
    entity_n = 0
    holdings_by_fund: dict[str, list[dict]] = {}
    pending_lines: dict[str, list[dict]] = {}
    for fid in ("MF001", "MF002"):
        rows = parse_disclosure(fid, ROOT / FUND_FILES[fid][0], "SRC-PENDING", f"BATCH-{fid}-2026-09-30", sector_of=cls.sector_of)
        pending_lines[fid] = rows
        for r in rows:
            if r["Line_Role"] != "POSITION":
                continue
            sid = match_security(r["ISIN"], None, registry)
            if sid:
                reg = next(x for x in registry if x["Security_ID"] == sid)
                if not reg["Industry"]:
                    reg["Industry"] = r["Industry"]
                continue
            entity_n += 1
            sid = next_security_id(registry)
            foreign = r["Asset_Class"] == "Foreign listed equity"
            n = nse.get(r["ISIN"])
            ticker = FOREIGN[r["ISIN"]][0] if foreign else (n["TckrSymb"] if n else "")
            registry.append({
                "Security_ID": sid, "Entity_ID": f"E{entity_n:04d}", "ISIN": r["ISIN"], "Exchange_Ticker": ticker,
                "Company_Name": r["Instrument_Name_As_Disclosed"], "Sector": r["Sector"], "Industry": r["Industry"],
                "Business_Model": cls.business_model_of(r["Industry"], r["Asset_Class"]), "Asset_Class": r["Asset_Class"],
                "Country_or_Market": "United States (Nasdaq)" if foreign else "India",
                "Trading_Currency": "USD" if foreign else "INR", "Reporting_Currency": "",
                "Ownership_Type": "Other", "Listing_Status": "Listed", "Primary_Valuation_Method": "", "Secondary_Valuation_Method": "",
                "Dedicated_Sheet": "", "Source_Status": UNRECON, "Source_ID": "",
            })
    for reg in registry:
        if reg["Industry"] == "" and reg["Entity_ID"] in SEEDS:
            pass

    # ---------------------------------------------------------------- source log rows
    sl = {}
    nse_log = book.add_log(doc_id=doc["nse"], entity="MARKET", metric="CLOSE_PRICE_LCY", reported_value="ClsPric per ISIN (see Page_or_Table)",
                           unit="INR", period=PRICE_DATE, obs_date=PRICE_DATE,
                           page="CSV rows by ISIN column (ISIN -> ClsPric); one row per registry security listed on NSE",
                           dest="market_prices;security_registry", status=VERIFIED)
    for reg in registry:
        reg["Source_ID"] = nse_log if reg["Asset_Class"] != "Foreign listed equity" else \
            book.add_log(doc_id=nasdaq_docs[reg["ISIN"]], entity=reg["Security_ID"], metric="CLOSE_PRICE_LCY",
                         reported_value=FOREIGN[reg["ISIN"]][3], unit="USD", period=PRICE_DATE, obs_date=PRICE_DATE,
                         page=f"JSON tradesTable.rows[date=10/23/2026].close, symbol {FOREIGN[reg['ISIN']][0]}",
                         dest="market_prices;security_registry", status=UNRECON)
    fx_log = book.add_log(doc_id=doc["rbi"], entity="MARKET", metric="FX_RATE_INR", reported_value=FX_USD_INR, unit="INR per USD",
                          period=PRICE_DATE, obs_date=PRICE_DATE,
                          page="Home page > Current Rates > Exchange Rates: 'INR / 1 USD : 94.9432 (As at 1.00pm of October 23, 2026) (Source : FBIL)'",
                          dest="market_prices", status=VERIFIED)

    # ---------------------------------------------------------------- holdings, totals
    holdings: list[dict] = []
    totals: list[dict] = []
    for fid in ("MF001", "MF002"):
        t = parsed[fid]
        pdate = t["portfolio_date"].isoformat()
        sheet = "PPFCF" if fid == "MF001" else "MIDCAP"
        first, last = t["lines"][0]["row"], t["lines"][-1]["row"]
        hs = book.add_log(doc_id=doc[fid], entity=fid, metric="FUND_HOLDINGS",
                          reported_value=f"{len(t['lines'])} lines; grand total {t['net_assets_lakh']:.2f}", unit="INR lakh",
                          period=pdate, obs_date=pdate, page=f"sheet {sheet}, rows {first}-{last} (all instrument and net-asset lines)",
                          dest="fund_holdings", status=VERIFIED)
        ts = book.add_log(doc_id=doc[fid], entity=fid, metric="FUND_AUM", reported_value=f"{t['net_assets_lakh']:.2f}", unit="INR lakh",
                          period=pdate, obs_date=pdate, page=f"sheet {sheet}, row {t['grand_row']} (Grand Total)",
                          dest="fund_scheme_totals", status=VERIFIED)
        rows = parse_disclosure(fid, ROOT / FUND_FILES[fid][0], hs, f"BATCH-{fid}-{pdate}", sector_of=cls.sector_of,
                                registry=registry, status=VERIFIED)
        rec = reconcile(rows, t["net_assets_cr"], RECON_TOL)
        if rec["recon_status"] != "PASS" or rec["weight_sum_status"] != "PASS" or rec["unmatched_lines"]:
            for r in rows:
                r["Data_Status"] = UNRECON
        # foreign lines: FX in the disclosure is not stated per line; leave blank
        holdings += rows
        totals.append({"Fund_ID": fid, "Portfolio_Date": pdate, "Reported_Scheme_Net_Assets_INR_Cr": f"{t['net_assets_cr']:.4f}".rstrip("0").rstrip("."),
                       "Source_ID": ts, "Data_Status": VERIFIED})
        report["funds"][fid] = {"portfolio_date": pdate, **rec, "lines": len(rows)}
        # month-on-month diff by ISIN (prior month positions are not in fund_holdings)
        prev_rows = parse_disclosure(fid, ROOT / FUND_FILES[fid][1], "SRC-PREV", "BATCH-PREV", sector_of=cls.sector_of)
        isin_sid = {r["ISIN"]: r["Security_ID"] for r in registry}
        for r in prev_rows:
            r["Security_ID"] = isin_sid.get(r["ISIN"], "") if r["Line_Role"] == "POSITION" else ""
        prev_pos = {r["ISIN"] for r in prev_rows if r["Line_Role"] == "POSITION"}
        cur_pos = {r["ISIN"] for r in rows if r["Line_Role"] == "POSITION"}
        report["funds"][fid]["prior_month_lines"] = len(prev_rows)
        report["funds"][fid]["added_isins_vs_prior"] = sorted(cur_pos - prev_pos)
        report["funds"][fid]["removed_isins_vs_prior"] = sorted(prev_pos - cur_pos)
        d = diff_portfolios(prev_rows, rows, RECON_TOL)
        report["funds"][fid]["diff_weight_sum"] = d.weight_sum
        report["funds"][fid]["diff_unmatched_isins"] = list(d.unmatched_isins)

    # ---------------------------------------------------------------- market prices (one common date)
    prices: list[dict] = []
    xdev = []
    bse_path = None
    for reg in registry:
        isin = reg["ISIN"]
        if reg["Asset_Class"] == "Foreign listed equity":
            close = FOREIGN[isin][3]
            prices.append({"Security_ID": reg["Security_ID"], "Price_Date": PRICE_DATE, "Close_LCY": close, "Currency": "USD",
                           "FX_Rate_to_INR": FX_USD_INR, "FX_Date": PRICE_DATE, "Close_INR": f"{float(close) * float(FX_USD_INR):.4f}",
                           "Local_Close_Timestamp": "2026-10-23 US regular-session close (time not stated in source)",
                           "Corporate_Action_Adjusted": "FALSE", "Source_ID": reg["Source_ID"], "Data_Status": UNRECON})
            continue
        n = nse.get(isin)
        if n is None:
            continue    # no NSE record: listed in missing_data by the caller
        prices.append({"Security_ID": reg["Security_ID"], "Price_Date": PRICE_DATE, "Close_LCY": n["ClsPric"], "Currency": "INR",
                       "FX_Rate_to_INR": "1.0", "FX_Date": PRICE_DATE, "Close_INR": n["ClsPric"],
                       "Local_Close_Timestamp": f"{PRICE_DATE} NSE end of day (time not stated in file); series {n['SctySrs']}",
                       "Corporate_Action_Adjusted": "FALSE", "Source_ID": nse_log, "Data_Status": VERIFIED})
    # ---------------------------------------------------------------- fund plans / NAV
    plan_rows, nav_rows = [], []
    codes = {p[6]: p[0] for p in PLANS}
    navall_lines = (ROOT / NAVALL).read_text(encoding="utf-8", errors="replace").splitlines()
    nav_by_key: dict[tuple, dict] = {}
    for fid, rel in NAV_HISTORY.items():
        pth = ROOT / rel
        if not pth.exists():
            continue
        hdoc = book.add_doc(entity=fid, name=f"AMFI NAV history extract ({fid}), scheme codes {', '.join(p[6] for p in PLANS if p[1] == fid)}",
                            doc_type="NAV file", tier="2", url="https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?mf={9|64}&tp=1&frmdt=..&todt=..",
                            local_path=rel, retrieved=RETRIEVED,
                            note="Lines for the listed scheme codes taken verbatim from AMFI's NAV history downloads (90-day windows; AMFI rejects longer ranges). Response URLs and SHA256 of every window are in the *_chunks.csv next to this file.")
        hsrc = book.add_log(doc_id=hdoc, entity=fid, metric="OFFICIAL_NAV", reported_value="daily NAV series", unit="INR per unit",
                            page="extract file, one line per scheme code and date", dest="official_nav", status=VERIFIED)
        for r in parse_amfi_nav(pth.read_text(encoding="utf-8").splitlines(), codes, hsrc):
            nav_by_key[(r["Plan_ID"], r["NAV_Date"])] = r
    for pid, fid, name, amc, plan, option, code in PLANS:
        ns = book.add_log(doc_id=doc["navall"], entity=pid, metric="OFFICIAL_NAV", reported_value="latest NAV line", unit="INR per unit",
                          period="2026-10-23", obs_date="2026-10-23", page=f"NAVAll.txt line for scheme code {code}", dest="official_nav;fund_plans",
                          status=VERIFIED)
        plan_rows.append({"Plan_ID": pid, "Fund_ID": fid, "Scheme_Name": name, "AMC": amc, "Plan": plan, "Option": option,
                          "AMFI_Scheme_Code": code, "Benchmark_Name": BENCHMARK[fid], "Benchmark_Is_TRI": "TRUE", "Source_ID": ns,
                          "Data_Status": VERIFIED})
        for r in parse_amfi_nav(navall_lines, {code: pid}, ns):
            nav_by_key.setdefault((r["Plan_ID"], r["NAV_Date"]), r)
    nav_rows = [nav_by_key[k] for k in sorted(nav_by_key)]

    # ---------------------------------------------------------------- write
    book.save()
    CANON.mkdir(parents=True, exist_ok=True)
    outs = {"security_registry": registry, "fund_holdings": holdings, "fund_scheme_totals": totals, "fund_plans": plan_rows,
            "official_nav": nav_rows, "market_prices": prices}
    for key, rows in outs.items():
        t = TABLES[key]
        write_csv(ROOT / t.csv_path, [c.name for c in t.stored_columns], rows)
        problems = validate_csv(t, ROOT / t.csv_path)
        report.setdefault("validation", {})[key] = problems[:5]
        report.setdefault("row_counts", {})[key] = len(rows)
    report["unpriced_registry"] = [r["Security_ID"] + " " + r["ISIN"] for r in registry
                                    if r["Security_ID"] not in {p["Security_ID"] for p in prices}]
    return report


if __name__ == "__main__":
    rep = build()
    print(json.dumps(rep, indent=1, default=str)[:6000])
