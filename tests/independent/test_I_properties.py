"""I layer, part 2: property tests (spec/worker_briefs/05-qa.md, I layer list).

Each property is checked twice: on the 05-qa clean-room implementation (runs now; proves the
contract's definitions are mutually consistent) and on the workers' reference functions
(NOT RUN while they raise NotImplementedError; runs for real after 00-main merges them).
"""
import dataclasses
import random

import pytest

from src.common.enums import Case
from src.fund_nav import classify as WC, coverage as WCOV, methods as WM
from src.scenarios import pricing as WP
from src.valuations import bank_ri as WRI, ddm as WDDM, justified_pb as WPB
from tests.contract import cases as K
from tests.independent import _gen as G
from tests.independent._support import call_worker
from tests.independent.cleanroom import controls as QC, nav as QN, valuation as QV

approx = pytest.approx
CASES = ("Base", "Bear", "Bull", "Selected")


# --------------------------------------------------------------- P-01 RI = DDM = P/B in steady state
def _p01(ri_fn, ddm_fn, pb_fn, getv=lambda x: x.value_at_anchor):
    rng = random.Random(101)
    for k in range(G.N_DRAWS):
        bv0, eps, dps, r, roe, payout, g = G.steady_state(rng)
        ri = getv(ri_fn(bv0, eps, dps, r, roe, g))
        ddm = getv(ddm_fn(bv0, eps, dps, r, roe, payout, g))
        pb = pb_fn(roe, r, g) * bv0
        assert ri == approx(ddm, rel=1e-9) and ri == approx(pb, rel=1e-9), f"draw {k}: r={r} roe={roe} payout={payout}"


def test_I_PROP_01a_steady_state_methods_agree_cleanroom():
    _p01(QV.residual_income, QV.dividend_discount, QV.justified_pb)


def test_I_PROP_01b_steady_state_methods_agree_worker():
    call_worker(WRI.residual_income_value, 100.0, [15.0], [7.5], 0.12, 0.15, 0.075)
    _p01(WRI.residual_income_value, WDDM.dividend_discount_value, WPB.justified_pb)


# --------------------------------------------------------------- P-02 Method 1 = Method 2 with q×P/NA weights
def _p02(m1, m2):
    rng = random.Random(202)
    for k in range(G.N_DRAWS):
        lines, nav, _ = G.fund(rng, consistent_weights=True)
        for case in CASES:
            assert m1(nav, lines, case).nav == approx(m2(nav, lines, case).nav, rel=1e-9), f"draw {k} case {case}"


def test_I_PROP_02a_method1_equals_method2_cleanroom():
    _p02(QN.weighted_adjustment_nav, QN.quantity_based_nav)


def test_I_PROP_02b_method1_equals_method2_worker():
    call_worker(WM.weighted_adjustment_nav, 80.0, K.MF001, "Base")
    _p02(WM.weighted_adjustment_nav, WM.quantity_based_nav)


# --------------------------------------------------------------- P-03 sector contributions sum to total
def _p03(m1):
    rng = random.Random(303)
    for k in range(G.N_DRAWS):
        lines, nav, _ = G.fund(rng)
        for case in CASES:
            r = m1(nav, lines, case)
            assert sum(r.adjustment_by_sector.values()) == approx(r.sum_adjustment, rel=1e-12, abs=1e-15), k
            assert sum(r.adjustment_by_line.values()) == approx(r.sum_adjustment, rel=1e-12, abs=1e-15), k
            assert r.nav == approx(nav * (1 + r.sum_adjustment), rel=1e-12), k


def test_I_PROP_03a_sector_contributions_sum_cleanroom():
    _p03(QN.weighted_adjustment_nav)


def test_I_PROP_03b_sector_contributions_sum_worker():
    call_worker(WM.weighted_adjustment_nav, 80.0, K.MF001, "Base")
    _p03(WM.weighted_adjustment_nav)


# --------------------------------------------------------------- P-04 Scenario NAV = Official at defaults
def _p04(m3, resolve, mk_inputs):
    rng = random.Random(404)
    for k in range(G.N_DRAWS):
        lines, nav, _ = G.fund(rng)
        # default controls: each line's scenario price is what the control resolver selects
        resolved = []
        for l in lines:
            if l.price_inr is None:
                resolved.append(l)
                continue
            fv = l.fv_inr.get("Base")
            out = resolve(mk_inputs(l.price_inr, fv, l.fv_inr.get("Bear"), l.fv_inr.get("Bull")))
            resolved.append(dataclasses.replace(l, scenario_price_inr=out.selected_scenario_market_price))
        assert m3(nav, resolved).nav == approx(nav, rel=1e-12), k


def test_I_PROP_04a_scenario_nav_identity_at_defaults_cleanroom():
    _p04(QN.scenario_market_nav, QC.resolve, lambda p, b, be, bu: QC.Controls(p, b, be, bu, required_margin_of_safety_pct=0.2))


def test_I_PROP_04b_scenario_nav_identity_at_defaults_worker():
    call_worker(WM.scenario_market_nav, 80.0, K.MF001)
    call_worker(WP.resolve_controls, WP.PriceControlInputs(750.0, 500.0))
    _p04(WM.scenario_market_nav, WP.resolve_controls,
         lambda p, b, be, bu: WP.PriceControlInputs(p, b, be, bu, required_margin_of_safety_pct=0.2))


# --------------------------------------------------------------- P-05 monotone FV -> monotone NAV
def _p05(m1, m2):
    rng = random.Random(505)
    for k in range(G.N_DRAWS):
        lines, nav, _ = G.fund(rng, unvalued_share=0.1)
        valued = [i for i, l in enumerate(lines) if l.fv_inr.get("Base") is not None and l.weight > 0]
        if not valued:
            continue
        i = rng.choice(valued)
        bump = rng.uniform(1.001, 1.5)
        hi = list(lines)
        hi[i] = dataclasses.replace(lines[i], fv_inr=dict(lines[i].fv_inr, Base=lines[i].fv_inr["Base"] * bump))
        for m in (m1, m2):
            assert m(nav, hi, "Base").nav > m(nav, lines, "Base").nav, f"draw {k} line {i}"
        lo = list(lines)
        lo[i] = dataclasses.replace(lines[i], fv_inr=dict(lines[i].fv_inr, Base=lines[i].fv_inr["Base"] / bump))
        for m in (m1, m2):
            assert m(nav, lo, "Base").nav < m(nav, lines, "Base").nav, f"draw {k} line {i}"


def test_I_PROP_05a_monotone_fair_value_cleanroom():
    _p05(QN.weighted_adjustment_nav, QN.quantity_based_nav)


def test_I_PROP_05b_monotone_fair_value_worker():
    call_worker(WM.weighted_adjustment_nav, 80.0, K.MF001, "Base")
    _p05(WM.weighted_adjustment_nav, WM.quantity_based_nav)


# --------------------------------------------------------------- P-06 coverage in [0, 1]
def _ona_net(lines):
    return sum(l.weight for l in lines if l.line_role != "POSITION")


def _p06(cov, hcov):
    """Equity coverage and holdings match always lie in [0, 1]. Total coverage is <= the sum of the
    disclosed weights (1 up to rounding) and >= 0 only when other net assets are >= 0 (I-PROP-06c, F-013)."""
    rng = random.Random(606)
    for k in range(G.N_DRAWS):
        lines, _, reported = G.fund(rng, unvalued_share=rng.uniform(0, 1), allow_unmatched=True)
        c = cov(lines, 0.9, 0.75)
        w_sum = sum(l.weight for l in lines)       # disclosed weights may miss 1 by rounding (in_Weight_Sum_Tol)
        assert c.coverage_total_pct <= w_sum + 1e-12, k
        if _ona_net(lines) >= 0:
            assert c.coverage_total_pct >= -1e-12, k
            assert c.unvalued_weight_pct <= w_sum + 1e-12, k
        assert c.coverage_equity_pct is None or -1e-12 <= c.coverage_equity_pct <= 1 + 1e-12, k
        assert c.unvalued_weight_pct >= -1e-12, k
        assert c.coverage_total_pct + c.unvalued_weight_pct == approx(sum(l.weight for l in lines)), k
        h = hcov(lines, reported, 0.005)
        assert -1e-12 <= h.match_pct <= 1 + 1e-12, k


def test_I_PROP_06a_coverage_in_unit_interval_cleanroom():
    _p06(QN.coverage_summary, QN.holdings_coverage)


def test_I_PROP_06b_coverage_in_unit_interval_worker():
    call_worker(WCOV.coverage_summary, K.MF001, 0.9, 0.75)
    _p06(WCOV.coverage_summary, WCOV.holdings_coverage)


def test_I_PROP_06c_total_coverage_negative_when_ona_is_net_negative(record_property):
    """Counterexample to the brief's "coverage lies in [0, 1]" under contract §7.5b / D-005:
    one unvalued equity line (weight 1.02) and net payables of -2% give
    Valuation_Coverage_Total_Pct = -0.02 and "102.0% of net assets unvalued". Finding F-013."""
    from src.common.enums import AssetClass as A, LineRole as R, Sector as S
    from src.fund_nav.model import HoldingLine
    lines = [HoldingLine("X1", R.POSITION, A.INDIAN_EQUITY, S.IT, 1.02, 102.0, "S1", 1e6, 1020.0,
                         {"Base": None, "Bear": None, "Bull": None}, 1020.0, None),
             HoldingLine("X2", R.ONA_LIABILITY, A.OTHER, S.NOT_APPLICABLE, -0.02, -2.0)]
    c = QN.coverage_summary(lines, 0.9, 0.75)
    assert c.coverage_total_pct == approx(-0.02) and c.unvalued_weight_pct == approx(1.02)
    assert c.caption == "Covers 0.0% of equity; 102.0% of net assets unvalued (adjustment 0)"
    record_property("qa_result", "WARNING")
    record_property("qa_evidence", "contract §7.5b gives Valuation_Coverage_Total_Pct = -2.0% for a fund with net "
                                   "payables and no valued equity; the [0,1] property needs ONA >= 0 (F-013)")


# --------------------------------------------------------------- P-07 controls algebra
def _p07(resolve, mk):
    rng = random.Random(707)
    for k in range(G.N_DRAWS):
        p0, base = rng.uniform(1, 5000), rng.uniform(1, 5000)
        mos = rng.uniform(0, 0.6)
        s = [rng.uniform(-0.5, 0.5) for _ in range(3)]
        default = resolve(mk(p0, base, mos))
        assert default.selected_scenario_market_price == p0 and default.selected_scenario_fair_value == base, k
        assert default.target_purchase_price == approx(base * (1 - mos), rel=1e-12), k
        sh = resolve(mk(p0, base, mos, market_price_mode=QC.MODE_SHOCK, global_shock_pct=s[0],
                        sector_shock_pct=s[1], market_price_shock_pct=s[2]))
        assert sh.selected_scenario_market_price == approx(p0 * (1 + s[0]) * (1 + s[1]) * (1 + s[2]), rel=1e-12), k
        assert sh.target_purchase_price == approx(default.target_purchase_price, rel=1e-15), k   # D-023
        swapped = resolve(mk(p0, base, mos, market_price_mode=QC.MODE_SHOCK, global_shock_pct=s[2],
                             sector_shock_pct=s[0], market_price_shock_pct=s[1]))
        assert swapped.selected_scenario_market_price == approx(sh.selected_scenario_market_price, rel=1e-12), k


def test_I_PROP_07a_controls_algebra_cleanroom():
    _p07(QC.resolve, lambda p, b, m, **kw: QC.Controls(p, b, b * 0.8, b * 1.2, required_margin_of_safety_pct=m, **kw))


def test_I_PROP_07b_controls_algebra_worker():
    call_worker(WP.resolve_controls, WP.PriceControlInputs(750.0, 500.0))
    _p07(WP.resolve_controls, lambda p, b, m, **kw: WP.PriceControlInputs(
        p, b, b * 0.8, b * 1.2, required_margin_of_safety_pct=m, **kw))


# --------------------------------------------------------------- P-08 driver model ↔ clean surplus
def test_I_PROP_08_driver_bvps_equals_clean_surplus_cleanroom():
    """§3.6: with constant shares, BVPS_t from the driver balance sheet equals BV_t of §3.2."""
    rng = random.Random(808)
    Base = dataclasses.make_dataclass("B", ["advances", "iea_to_advances", "non_interest_income",
                                            "operating_expenses", "equity", "diluted_shares"])
    Drv = dataclasses.make_dataclass("D", ["advance_growth", "iea_to_advances", "nim", "non_interest_income_growth",
                                           "opex_growth", "credit_cost", "tax_rate", "payout_ratio"])
    for k in range(G.N_DRAWS):
        base = Base(rng.uniform(1e4, 3e6), rng.uniform(1.1, 1.6), rng.uniform(1e3, 5e4), rng.uniform(1e3, 5e4),
                    rng.uniform(1e4, 5e5), float(rng.randint(10**8, 8 * 10**9)))
        drv = [Drv(rng.uniform(0, 0.25), rng.uniform(1.1, 1.6), rng.uniform(0.02, 0.05), rng.uniform(0, 0.2),
                   rng.uniform(0, 0.15), rng.uniform(0, 0.02), 0.25, rng.uniform(0, 0.5)) for _ in range(rng.randint(1, 8))]
        proj = QV.project_bank(base, drv)
        bv0 = base.equity * 1e7 / base.diluted_shares
        path = QV.clean_surplus_path(bv0, [p.eps for p in proj], [p.dps for p in proj])
        assert path[1:] == approx([p.bvps for p in proj], rel=1e-9), k
        assert QV.capital_retention_check(path[1:], [p.bvps for p in proj]) == "PASS"


# --------------------------------------------------------------- P-09 equity bridge identities
def test_I_PROP_09_bridge_identities_cleanroom():
    """BV_V = BV_A + reported + stub − dividends; interim EPS equal to the accrued forecast gives
    deviation 0; with no interims the stub is the full accrual from A."""
    from datetime import date, timedelta
    rng = random.Random(909)
    A = date(2026, 3, 31)
    for k in range(G.N_DRAWS):
        fc = [(date(2027, 3, 31), rng.uniform(1, 100)), (date(2028, 3, 31), rng.uniform(1, 100))]
        V = A + timedelta(days=rng.randint(1, 730))
        q_ends = [d for d in (date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31), date(2027, 3, 31),
                              date(2027, 6, 30), date(2027, 9, 30), date(2027, 12, 31)) if d <= V]
        n = rng.randint(0, len(q_ends))
        ends = q_ends[:n]
        prev, interim = A, []
        for d in ends:                                        # interim EPS exactly on forecast
            interim.append((d, QV.accrued_forecast_eps(A, fc, prev, d)))
            prev = d
        b = QV.equity_bridge(100.0, A, fc, V, interim, [(A + timedelta(days=10), 1.5)])
        assert b.bv_estimated_at_valuation == approx(
            100.0 + b.eps_reported_after_anchor + b.eps_forecast_stub - b.dividends_paid, rel=1e-12), k
        assert b.eps_reported_after_anchor + b.eps_forecast_stub == approx(QV.accrued_forecast_eps(A, fc, A, V), rel=1e-12), k
        if ends:
            assert b.interim_eps_deviation_pct == approx(0.0, abs=1e-12), k
        else:
            assert b.interim_eps_deviation_pct is None, k


# --------------------------------------------------------------- P-10 classification invariants
def _p10(classify):
    rng = random.Random(1010)
    for k in range(G.N_DRAWS // 4):
        lines, _, _ = G.fund(rng, allow_unmatched=True, allow_mpt=True)
        for l in lines:
            st = str(classify(l))
            if QN.match_status(l) not in (None, "MATCHED"):
                assert st == "UNVALUED", (k, l.line_id)          # D-026
            if l.line_role != "POSITION":
                assert st == "CARRYING_VALUE", (k, l.line_id)


def test_I_PROP_10a_classification_invariants_cleanroom():
    _p10(QN.coverage_status)


def test_I_PROP_10b_classification_invariants_worker():
    _, _, _ = G.fund(random.Random(1))
    from tests.contract import cases as K
    call_worker(WC.coverage_status, K.MF001[0])
    _p10(WC.coverage_status)
