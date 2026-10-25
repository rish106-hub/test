"""Regenerate tests/fixtures/synthetic/*.csv from tests/contract/cases.py.

The contract tests and the stubbed test build therefore share one set of numbers.
Every row is marked SYNTHETIC TEST FIXTURE. A production build rejects these
rows (D-013).

usage: python tools/make_synthetic_fixtures.py [--check]
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import schema as S  # noqa: E402
from src.common.enums import DataStatus, LineRole  # noqa: E402
from tests.contract import cases as K  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "synthetic"
SYN = DataStatus.SYNTHETIC_TEST_FIXTURE.value
SRC = "SRC-SYNTH-000001"

SECURITIES = [
    # sid, entity, name, sector, business model, asset class, ccy, ownership, dedicated sheet, method
    ("S90001", "E9001", "SYNTHETIC Bank Alpha", "Financial Services", "Deposit-taking bank", "Indian listed equity", "INR", "Private", "VAL_HDFC_BANK", "Residual Income"),
    ("S90002", "E9002", "SYNTHETIC Bank Beta", "Financial Services", "Deposit-taking bank", "Indian listed equity", "INR", "Government-owned (PSU)", "", "Residual Income"),
    ("S90003", "E9003", "SYNTHETIC Industrial Gamma", "Industrials and Capital Goods", "Non-financial operating company", "Indian listed equity", "INR", "Private", "", "None"),
    ("S90004", "E9004", "SYNTHETIC Software Delta Inc", "Information Technology", "Non-financial operating company", "Foreign listed equity", "USD", "Private", "", "FCFF DCF (WACC)"),
    ("S90005", "E9005", "SYNTHETIC Bank Epsilon", "Financial Services", "Deposit-taking bank", "Indian listed equity", "INR", "Private", "", "Residual Income"),
]
FX = {"INR": 1.0, "USD": 85.0}


def _rows():
    t: dict[str, list[dict]] = {}
    t["security_registry"] = [dict(
        Security_ID=sid, Entity_ID=eid, ISIN=f"SYNTH{sid[1:]:0>7}", Exchange_Ticker=f"SYN{sid[-1]}",
        Company_Name=name, Sector=sector, Industry="", Business_Model=bm, Asset_Class=ac,
        Country_or_Market="India" if ccy == "INR" else "United States", Trading_Currency=ccy,
        Reporting_Currency=ccy, Ownership_Type=own, Listing_Status="Listed",
        Primary_Valuation_Method=meth, Secondary_Valuation_Method="", Dedicated_Sheet=sheet,
        Source_Status=SYN, Source_ID=SRC) for sid, eid, name, sector, bm, ac, ccy, own, sheet, meth in SECURITIES]

    t["market_prices"] = []
    for sid, *_rest in SECURITIES:
        ccy = _rest[5]
        inr = K.PRICE[sid]
        t["market_prices"].append(dict(
            Security_ID=sid, Price_Date=K.PRICE_DATE, Close_LCY=inr / FX[ccy], Currency=ccy,
            FX_Rate_to_INR=FX[ccy], FX_Date=K.PRICE_DATE, Close_INR=inr, Local_Close_Timestamp="",
            Corporate_Action_Adjusted="TRUE", Source_ID=SRC, Data_Status=SYN))

    t["valuation_outputs"] = []
    for sid in ("S90001", "S90002", "S90003", "S90004"):
        fv = K.FV[sid]
        valued = fv["Base"] is not None
        t["valuation_outputs"].append(dict(
            Security_ID=sid, Valuation_Date=K.PRICE_DATE, Anchor_Date="2026-03-31",
            Primary_Method="Residual Income" if sid in ("S90001", "S90002") else ("FCFF DCF (WACC)" if valued else "None"),
            Secondary_Methods="", FV_Base_INR=fv["Base"], FV_Bear_INR=fv["Bear"], FV_Bull_INR=fv["Bull"],
            Terminal_Value_Share_Base=0.33 if valued else None, Terminal_Flag="PASS" if valued else None,
            Peer_Flag="PASS" if valued else None,
            Valuation_Coverage_Status="MODEL_VALUED" if valued else "UNVALUED",
            Model_Sheet="FIXTURE", Methodology_Version="fixture", Data_Confidence_Note="SYNTHETIC"))

    t["fund_plans"] = [
        dict(Plan_ID="MF001-DIR-GR", Fund_ID="MF001", Scheme_Name="SYNTHETIC Flexi Cap Fund", AMC="SYNTHETIC AMC",
             Plan="Direct", Option="Growth", AMFI_Scheme_Code="900001", Benchmark_Name="SYNTHETIC TRI",
             Benchmark_Is_TRI="TRUE", Source_ID=SRC, Data_Status=SYN),
        dict(Plan_ID="MF001-REG-GR", Fund_ID="MF001", Scheme_Name="SYNTHETIC Flexi Cap Fund", AMC="SYNTHETIC AMC",
             Plan="Regular", Option="Growth", AMFI_Scheme_Code="900002", Benchmark_Name="SYNTHETIC TRI",
             Benchmark_Is_TRI="TRUE", Source_ID=SRC, Data_Status=SYN),
        dict(Plan_ID="MF002-DIR-GR", Fund_ID="MF002", Scheme_Name="SYNTHETIC Mid Cap Fund", AMC="SYNTHETIC AMC",
             Plan="Direct", Option="Growth", AMFI_Scheme_Code="900003", Benchmark_Name="SYNTHETIC TRI",
             Benchmark_Is_TRI="TRUE", Source_ID=SRC, Data_Status=SYN),
    ]

    t["fund_holdings"] = []
    for fund, lines in (("MF001", K.MF001), ("MF002", K.MF002)):
        for n, l in enumerate(lines, 1):
            t["fund_holdings"].append(dict(
                Holding_Line_ID=l.line_id, Fund_ID=fund, Portfolio_Date=K.PORTFOLIO_DATE, Line_Role=l.line_role.value,
                Security_ID=l.security_id or "", ISIN=f"SYNTH{l.security_id[1:]:0>7}" if l.security_id else "",
                Instrument_Name_As_Disclosed=l.security_id or ("Cash and TREPS" if l.line_role == LineRole.ONA_ASSET else "Net payables"),
                Company_Name="", Sector=l.sector.value, Industry="", Asset_Class=l.asset_class.value,
                Country_or_Market="", Trading_Currency="", FX_Rate_to_INR="",
                Quantity_Held=l.quantity if l.quantity is not None else "",
                Market_Value_INR_Cr=round(l.market_value_inr_cr, 10),
                Raw_Market_Value=round(l.market_value_inr_cr * 100, 10), Raw_Market_Value_Unit="INR lakh",
                Weight_Pct_of_Scheme_NAV=l.weight, Source_ID=SRC, Import_Batch_ID="BATCH-SYNTH-1", Data_Status=SYN))

    t["fund_scheme_totals"] = [
        dict(Fund_ID="MF001", Portfolio_Date=K.PORTFOLIO_DATE, Reported_Scheme_Net_Assets_INR_Cr=K.MF001_REPORTED_NA, Source_ID=SRC, Data_Status=SYN),
        dict(Fund_ID="MF002", Portfolio_Date=K.PORTFOLIO_DATE, Reported_Scheme_Net_Assets_INR_Cr=K.MF002_REPORTED_NA, Source_ID=SRC, Data_Status=SYN),
    ]
    t["official_nav"] = [dict(Plan_ID=p, NAV_Date=K.PRICE_DATE, NAV_INR=v, Source_ID=SRC, Data_Status=SYN)
                         for p, v in {**K.MF001_NAV, **K.MF002_NAV}.items()]

    t["peer_summary"] = [
        dict(Peer_Group_ID="PG_SYNTH", Metric_ID="PB", Exclude_Security_ID="S90001", Median=2.5, N_Valid=4, N_Excluded=1, Min=1.5, Max=3.5),
        dict(Peer_Group_ID="PG_SYNTH", Metric_ID="PE_TRAILING", Exclude_Security_ID="S90001", Median=15.0, N_Valid=4, N_Excluded=1, Min=10.0, Max=20.0),
    ]
    t["global_inputs"] = []
    with (ROOT / "data" / "reference" / "global_inputs.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["Name"] in ("in_Valuation_Date", "in_Price_Date"):
                r = dict(r, Value=K.PRICE_DATE, Assumption_Source_Type=SYN)
            if r["Name"] == "in_Risk_Free_Rate":
                r = dict(r, Value="0.065", Assumption_Source_Type=SYN)
            if r["Name"] == "in_Equity_Risk_Premium":
                r = dict(r, Value="0.06", Assumption_Source_Type=SYN)
            if r["Name"] == "in_Default_TC_Pct":
                r = dict(r, Value="0.001", Assumption_Source_Type=SYN)
            if r["Name"] == "in_Hypo_Capital_INR":
                r = dict(r, Value="1000000", Assumption_Source_Type=SYN)
            t["global_inputs"].append(r)
    return t


def _render(table_key: str, rows: list[dict]) -> str:
    table = S.TABLES[table_key]
    cols = [c.name for c in (table.stored_columns if table.csv_path else table.columns)]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c, "")) for c in cols})
    return buf.getvalue()


def main(check: bool) -> int:
    stale = []
    for key, rows in _rows().items():
        path = OUT / f"{key}.csv"
        text = _render(key, rows)
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print("stale fixtures (run python tools/make_synthetic_fixtures.py):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
