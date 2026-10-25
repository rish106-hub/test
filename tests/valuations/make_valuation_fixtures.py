"""Generate the 02-valuation synthetic fixtures for S90001 (entity E9001) on VAL_HDFC_BANK.

tests/fixtures/synthetic/ (frozen, 00-main) has no raw financials, corporate actions or
valuation assumptions, so an isolated `--test-build --only 02-valuation` would value S90001
from empty tables. Until CR-02-valuation-001 moves them there, these fixtures live here and
the 02-valuation builder appends them in test builds only (src/valuations/fixtures.py).

Every number is SYNTHETIC: invented round figures that resemble no real bank. Every row is
marked SYNTHETIC TEST FIXTURE with an SRC-SYNTH Source_ID, so a production build rejects it (D-013).

usage: python tests/valuations/make_valuation_fixtures.py [--check]
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.common import schema as S  # noqa: E402
from src.common.enums import DataStatus  # noqa: E402
from src.common.units import fiscal_label  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "synthetic"
SYN = DataStatus.SYNTHETIC_TEST_FIXTURE.value
SRC = "SRC-SYNTH-VAL-0001"
BATCH = "BATCH-SYNTH-VAL-1"
ENTITY, SECURITY = "E9001", "S90001"
SHARES = 1_000_000_000.0
ANCHOR_FY = 2026
N_FY = 10

# FY2026 (anchor year) levels, INR crore, and the annual growth used to back-cast history.
FY_FLOWS = {   # metric: (FY2026 value, growth per year)
    "BANK_INT_INCOME": (22_000.0, 0.14), "BANK_INT_EXPENSE": (11_800.0, 0.13), "BANK_NON_II": (3_600.0, 0.15),
    "BANK_OPEX": (5_400.0, 0.12), "BANK_PROVISIONS": (1_140.0, 0.10),
}
FY_BALANCES = {
    "BANK_NET_ADVANCES": (200_000.0, 0.15), "BANK_INVESTMENTS": (70_000.0, 0.12), "BANK_DEPOSITS": (230_000.0, 0.15),
    "BANK_CASA": (92_000.0, 0.14), "TOTAL_ASSETS": (300_000.0, 0.15), "COMMON_EQUITY": (25_000.0, 0.16),
}
FY_RATIOS = {   # metric: (FY2026 value, change per year going back)
    "BANK_GNPA_RATIO": (0.013, 0.0012), "BANK_NNPA_RATIO": (0.004, 0.0004), "BANK_NIM": (0.040, 0.0005),
    "BANK_CAR": (0.185, -0.002), "BANK_CET1": (0.165, -0.002),
}
TAX = 0.25
PAYOUT = 0.20
# Discrete quarters reported after the anchor (Q1FY2027, Q2FY2027): EPS per diluted share, INR.
INTERIM_EPS = {date(2026, 6, 30): 15.0, date(2026, 9, 30): 15.5}


def _round(x: float) -> float:
    return round(x, 6)


class _Obs:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, metric, ptype, period_end: date, value, unit, basis="Standalone", known_lag=45, supersedes="",
            note=""):
        n = len(self.rows) + 1
        label = fiscal_label(period_end, quarterly=(ptype != "FY"))
        self.rows.append(dict(
            Observation_ID=f"OBS-SYNTH-{ENTITY}-{n:05d}", Entity_ID=ENTITY, Metric_ID=metric, Period_Type=ptype,
            Period_End=period_end.isoformat(), Fiscal_Label=label, Accounting_Basis=basis, Value=_round(value),
            Unit=unit, Raw_Value=_round(value), Raw_Unit=unit, Source_ID=SRC, Data_Status=SYN, Import_Batch_ID=BATCH,
            Known_As_Of=(period_end + timedelta(days=known_lag)).isoformat(),
            Supersedes_Observation_ID=supersedes, Normalisation_Note=note or "SYNTHETIC TEST FIXTURE"))
        return self.rows[-1]["Observation_ID"]


def _fy_values(year: int) -> dict[str, float]:
    k = ANCHOR_FY - year
    v = {m: lvl / (1 + g) ** k for m, (lvl, g) in {**FY_FLOWS, **FY_BALANCES}.items()}
    v.update({m: lvl + step * k for m, (lvl, step) in FY_RATIOS.items()})
    nii = v["BANK_INT_INCOME"] - v["BANK_INT_EXPENSE"]
    pat = (nii + v["BANK_NON_II"] - v["BANK_OPEX"] - v["BANK_PROVISIONS"]) * (1 - TAX)
    v["NET_PROFIT_COMMON"] = pat
    v["EPS_DILUTED"] = pat * 1e7 / SHARES
    v["DPS"] = round(v["EPS_DILUTED"] * PAYOUT, 2)
    v["DILUTED_SHARES"] = SHARES
    return v


UNITS = {**{m: "INR_Cr" for m in (*FY_FLOWS, *FY_BALANCES, "NET_PROFIT_COMMON")},
         **{m: "decimal" for m in FY_RATIOS}, "EPS_DILUTED": "INR", "DPS": "INR", "DILUTED_SHARES": "count"}
QUARTER_FLOWS = ("BANK_INT_INCOME", "BANK_INT_EXPENSE", "BANK_NON_II", "BANK_OPEX", "BANK_PROVISIONS",
                 "NET_PROFIT_COMMON", "EPS_DILUTED")
QUARTER_POINTS = ("BANK_NET_ADVANCES", "BANK_DEPOSITS", "BANK_GNPA_RATIO", "BANK_NNPA_RATIO")


def raw_financials() -> list[dict]:
    obs = _Obs()
    for year in range(ANCHOR_FY - N_FY + 1, ANCHOR_FY + 1):
        fye = date(year, 3, 31)
        for metric, value in _fy_values(year).items():
            obs.add(metric, "FY", fye, value, UNITS[metric])
    # One revision (append-only, D-016): FY2025 profit restated; the original must be ignored.
    fy25 = _fy_values(2025)
    original = next(r["Observation_ID"] for r in obs.rows
                    if r["Metric_ID"] == "NET_PROFIT_COMMON" and r["Period_End"] == "2025-03-31")
    for r in obs.rows:
        if r["Observation_ID"] == original:
            r["Value"] = r["Raw_Value"] = _round(fy25["NET_PROFIT_COMMON"] - 25.0)
    obs.add("NET_PROFIT_COMMON", "FY", date(2025, 3, 31), fy25["NET_PROFIT_COMMON"], "INR_Cr", known_lag=120,
            supersedes=original, note="SYNTHETIC TEST FIXTURE: restated")
    # A consolidated observation that a Standalone valuation must never pick up.
    obs.add("COMMON_EQUITY", "FY", date(2026, 3, 31), 31_000.0, "INR_Cr", basis="Consolidated")
    # 20 quarters ending Q2FY2027: discrete quarterly flows (FY / 4) and quarter-end balances.
    q_ends = [date(2021, 12, 31)]
    while len(q_ends) < 20:
        last = q_ends[-1]
        m = last.month + 3
        y = last.year + (m > 12)
        m = m - 12 if m > 12 else m
        q_ends.append(date(y, m, {3: 31, 6: 30, 9: 30, 12: 31}[m]))
    for qe in q_ends:
        fy_year = qe.year if qe.month <= 3 else qe.year + 1
        if qe in INTERIM_EPS:
            eps = INTERIM_EPS[qe]
            pat = eps * SHARES / 1e7
            base = _fy_values(ANCHOR_FY)
            flows = {m: base[m] * 1.04 / 4 for m in QUARTER_FLOWS[:5]}
            flows["NET_PROFIT_COMMON"], flows["EPS_DILUTED"] = pat, eps
            points = {m: base[m] * (1.035 if qe.month == 6 else 1.07) for m in QUARTER_POINTS[:2]}
            points.update({m: base[m] for m in QUARTER_POINTS[2:]})
        else:
            fy = _fy_values(fy_year)
            flows = {m: fy[m] / 4 for m in QUARTER_FLOWS}
            points = {m: fy[m] for m in QUARTER_POINTS}
        for m, v in flows.items():
            obs.add(m, "Q", qe, v, UNITS[m], known_lag=18)
        for m, v in points.items():
            obs.add(m, "POINT", qe, v, UNITS[m], known_lag=18)
    return obs.rows


def corporate_actions() -> list[dict]:
    rows = [("CA-SYNTH-0001", "Split", "2019-09-19", "5:1"),
            ("CA-SYNTH-0002", "Dividend", "2025-06-20", "9.5"),     # before the anchor: in BV_A already gone
            ("CA-SYNTH-0003", "Dividend", "2026-06-20", "11.0")]    # FY2026 final, ex in (A, V]
    return [dict(Action_ID=a, Security_ID=SECURITY, Action_Type=t, Ex_Date=d, Record_Date="", Ratio_or_Amount=x,
                 Source_ID=SRC, Data_Status=SYN) for a, t, d, x in rows]


def assumptions() -> list[dict]:
    out = []

    def add(case, param, period, value, unit, why):
        out.append(dict(Assumption_ID=f"A-{SECURITY}-{case}-{param}-{period}", Scope=SECURITY, Case=case,
                        Parameter=param, Period=period, Value=value, Unit=unit, Assumption_Source_Type=SYN,
                        Source_ID=SRC, Rationale=f"SYNTHETIC TEST FIXTURE: {why}"))

    add("All", "BETA", "ALL", 1.0, "x", "round number for the isolated build")
    add("All", "IEA_TO_ADV_ANCHOR", "ALL", 1.35, "x", "(advances + investments) / advances at the synthetic anchor")
    sets = {
        "Bear": dict(ADV_GROWTH=0.10, IEA_TO_ADV=1.35, NIM=0.036, NONII_GROWTH=0.10, OPEX_GROWTH=0.12,
                     CREDIT_COST=0.010, TAX_RATE=0.25, PAYOUT=0.20, TERMINAL_ROE=0.14, TERMINAL_GROWTH=0.05,
                     TERMINAL_PAYOUT=0.64, EXIT_PB=1.8),
        "Base": dict(IEA_TO_ADV=1.35, NIM=0.040, NONII_GROWTH=0.15, OPEX_GROWTH=0.12, CREDIT_COST=0.006,
                     TAX_RATE=0.25, PAYOUT=0.20, TERMINAL_ROE=0.17, TERMINAL_GROWTH=0.06, TERMINAL_PAYOUT=0.65,
                     EXIT_PB=2.5),
        "Bull": dict(ADV_GROWTH=0.19, IEA_TO_ADV=1.35, NIM=0.042, NONII_GROWTH=0.18, OPEX_GROWTH=0.12,
                     CREDIT_COST=0.005, TAX_RATE=0.25, PAYOUT=0.20, TERMINAL_ROE=0.19, TERMINAL_GROWTH=0.065,
                     TERMINAL_PAYOUT=0.66, EXIT_PB=3.0),
    }
    units = {"IEA_TO_ADV": "x", "EXIT_PB": "x"}
    for case, params in sets.items():
        for p, v in params.items():
            add(case, p, "ALL", v, units.get(p, "decimal"), f"{case} case {p}")
    # Base advance growth varies by year, to exercise per-year resolution.
    for fy, g in zip(range(2027, 2033), (0.16, 0.16, 0.15, 0.15, 0.14, 0.14)):
        add("Base", "ADV_GROWTH", f"FY{fy}", g, "decimal", f"Base advance growth FY{fy}")
    return out


def _render(table: S.Table, rows: list[dict]) -> str:
    cols = [c.name for c in table.stored_columns]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


FIXTURES = {"raw_financials": (S.RAW_FINANCIALS, raw_financials), "corporate_actions": (S.CORPORATE_ACTIONS,
            corporate_actions), "assumptions": (S.ASSUMPTIONS, assumptions)}


def main(check: bool) -> int:
    stale = []
    for key, (table, fn) in FIXTURES.items():
        path = OUT / f"{key}.csv"
        text = _render(table, fn())
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print("stale fixtures (run python tests/valuations/make_valuation_fixtures.py):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
