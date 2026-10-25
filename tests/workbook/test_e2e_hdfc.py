"""E layer: end-to-end acceptance on the production build (spec/test_plan.md §E, gate G1, D-028).

HDFC Bank -> one real holding -> that fund's Direct Growth Fair NAV, with independent controls.
Every test is NOT RUN until the validated build is a production build with real data.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tests.independent.cleanroom import valuation as QV
from tests.workbook import test_W_10_manual as M
from tests.workbook import wbread as RD
from tests.workbook.conftest import require_production, require_real
from tests.workbook.test_W_values import CLEANROOM_FNS, nav_summary_diffs
from tests.workbook.wbmodel import as_date, num

pytestmark = pytest.mark.workbook
ROOT = Path(__file__).resolve().parents[2]


def _csv(rel):
    p = ROOT / rel
    if not p.exists():
        return None
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def hdfc(wb) -> str:
    require_production(wb)
    require_real(wb, "tbl_Registry", "tbl_ValuationOutputs")
    rows = [r for r in wb.rows("tbl_Registry") if r.get("Entity_ID") == "C001"
            or str(r.get("Company_Name", "")).upper().startswith("HDFC BANK")]
    eq = [r for r in rows if r.get("Asset_Class") == "Indian listed equity"]
    if len(eq) != 1:
        pytest.fail(f"expected exactly one HDFC Bank equity security in tbl_Registry, found {[r['Security_ID'] for r in eq]}")
    return eq[0]["Security_ID"]


def direct_growth_holder(wb, sid):
    plans = RD.by_key(wb.rows("tbl_FundPlans"), "Plan_ID")
    for f in M.holders(wb, sid):
        for p, r in plans.items():
            if r["Fund_ID"] == f and r["Plan"] == "Direct" and r["Option"] == "Growth":
                return f, p
    pytest.fail(f"{sid} is not held by any fund with a Direct Growth plan")


def test_E_01_hdfc_valued_by_full_ri_path(built, record_property):
    sid = hdfc(built)
    r = RD.by_key(built.rows("tbl_ValuationOutputs"), "Security_ID")[sid]
    problems = []
    if r["Valuation_Coverage_Status"] != "MODEL_VALUED":
        problems.append("not MODEL_VALUED")
    if r["Primary_Method"] != "Residual Income":
        problems.append(f"primary method {r['Primary_Method']}")
    for c in ("FV_Base_INR", "FV_Bear_INR", "FV_Bull_INR", "BV_Reported_At_Anchor_INR", "BV_Estimated_At_Valuation_INR",
              "Terminal_Value_Share_Base", "Financials_Age_Days", "Anchor_Age_Days"):
        if num(r.get(c)) is None:
            problems.append(f"{c} blank")
    A, R, V = as_date(r["Anchor_Date"]), as_date(r["Latest_Results_Period_End"]), as_date(r["Valuation_Date"])
    if None in (A, R, V):
        problems.append("a model date is blank")
    else:
        g = lambda n: int(num(RD.global_input(built, n)))   # noqa: E731
        fin, anc, status = QV.freshness(A, R, V, g("in_Financials_Stale_Days"), g("in_Anchor_Max_Age_Days"))
        if (num(r["Financials_Age_Days"]), num(r["Anchor_Age_Days"]), r["Freshness_Status"]) != (fin, anc, status):
            problems.append(f"freshness {r['Financials_Age_Days']}/{r['Anchor_Age_Days']}/{r['Freshness_Status']} "
                            f"!= clean-room {fin}/{anc}/{status}")
    if r["Model_Sheet"] not in built.wf.sheetnames:
        problems.append(f"model sheet {r['Model_Sheet']} missing")
    record_property("qa_evidence", f"{sid}: FV {r['FV_Bear_INR']}/{r['FV_Base_INR']}/{r['FV_Bull_INR']}, A={A}, R={R}, "
                                   f"V={V}, freshness {r['Freshness_Status']}; problems {problems}. Full RI recompute "
                                   "from VAL_HDFC_BANK inputs needs F-012")
    assert problems == []


def test_E_02_hdfc_is_a_disclosed_holding_of_a_direct_growth_scheme(built, record_property):
    sid = hdfc(built)
    fund, plan = direct_growth_holder(built, sid)
    line = next(r for r in built.rows(RD.holdings_table(built, fund)) if r.get("Security_ID") == sid)
    log = {r["Source_ID"]: r for r in (_csv("data/canonical/source_log.csv") or [])}
    man = {r["Source_Doc_ID"]: r for r in (_csv("data/source_manifest.csv") or [])}
    src = log.get(line["Source_ID"])
    doc = man.get(src["Source_Doc_ID"]) if src else None
    record_property("qa_evidence", f"{sid} in {fund} ({plan}) line {line['Holding_Line_ID']} Source_ID {line['Source_ID']} "
                                   f"-> doc {doc and doc['Source_Doc_ID']} {doc and doc['Document_Name']}")
    assert src is not None, f"{line['Source_ID']} not in source_log"
    assert doc is not None and doc["Entity_or_Fund_ID"] in (fund, plan), "disclosure is not the scheme's own document"
    assert "portfolio" in doc["Document_Type"].lower()


def test_E_03_fund_fair_nav_reconciled_with_three_quality_measures(built, record_property):
    sid = hdfc(built)
    fund, plan = direct_growth_holder(built, sid)
    require_real(built, "tbl_NAVSummary", "tbl_PriceControls")
    r = RD.by_key(built.rows("tbl_NAVSummary"), "Plan_ID")[plan]
    problems = [c for c in ("Fair_NAV_Base", "Fair_NAV_M2_Base", "Official_NAV") if num(r.get(c)) is None]
    if r["Recon_Status"] != "PASS":
        problems.append(f"Recon_Status {r['Recon_Status']} (gap {r['Recon_Gap_Pct']})")
    if not str(r.get("Coverage_Caption", "")).startswith("Covers "):
        problems.append("no coverage caption")
    for c in ("Holdings_Coverage_Status", "Valuation_Coverage_Status", "Freshness_Status"):
        if r.get(c) not in ("PASS", "WARNING", "FAIL", "STALE"):
            problems.append(f"{c}={r.get(c)!r}")
    diffs = [d for d in nav_summary_diffs(built, CLEANROOM_FNS) if d[0] == plan]
    record_property("qa_evidence", f"{plan}: Official {r['Official_NAV']}, M1 {r['Fair_NAV_Base']}, M2 {r['Fair_NAV_M2_Base']}, "
                                   f"recon {r['Recon_Status']}, '{r['Coverage_Caption']}', holdings {r['Holdings_Coverage_Status']}, "
                                   f"valuation {r['Valuation_Coverage_Status']}, freshness {r['Freshness_Status']}; "
                                   f"clean-room diffs {diffs[:3]}")
    assert problems == [] and diffs == [], (problems, diffs[:5])


@pytest.mark.parametrize("body", ["manual_1_shock", "manual_2_bias", "manual_3_absolute"])
def test_E_04_hdfc_controls_move_only_expected_outputs(built, tmp_path, body, record_property):
    sid = hdfc(built)
    require_real(built, "tbl_PriceControls", "tbl_NAVSummary")
    record_property("qa_evidence", getattr(M, body)(built, sid, tmp_path))
