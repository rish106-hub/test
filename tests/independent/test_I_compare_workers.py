"""I layer, part 3: differential tests. The workers' reference functions must agree with the
05-qa clean-room implementation to 1e-9 relative on the contract cases and on seeded random
inputs. A test is NOT RUN (skipped, with the reason) while the worker function is a stub.

Where the contract is ambiguous the comparison is restricted to the unambiguous region, and a
separate `..._ambiguity_` test records which reading the worker chose (result WARNING) so that
00-main can rule on the finding named in its docstring.
"""
import dataclasses
import random
from datetime import date, timedelta

import pytest

from src.common.enums import Case, FairValueMode as F, MarketPriceMode as M
from src.fund_nav import classify as WC, coverage as WCOV, custom_allocation as WCA, methods as WM
from src.fund_nav import overlap as WO, rebalance as WR
from src.peers import peer_table as WPT
from src.scenarios import pricing as WP
from src.valuations import bank_drivers as WBD, bank_ri as WRI, blend as WBL, ddm as WDDM, errors as WE
from src.valuations import insurance_sotp as WINS, justified_pb as WPB, peer_relative as WPR
from src.valuations import rollforward as WRF, terminal as WT
from tests.contract import cases as K
from tests.independent import _gen as G
from tests.independent._support import call_worker, diff_fields, same
from tests.independent.cleanroom import controls as QC, nav as QN, valuation as QV

N = G.N_DRAWS


def _assert_no_diffs(diffs: list):
    assert not diffs, f"{len(diffs)} disagreements, first 5: {diffs[:5]}"


# =========================================================================== valuation (02-valuation)
def test_I_CMP_01_residual_income():
    call_worker(WRI.residual_income_value, 100.0, [15.0], [3.0], 0.13, 0.14, 0.05)
    rng, diffs = random.Random(1), []
    for k in range(N):
        bv0, eps, dps, r, roe, _, g = G.ri_inputs(rng)
        d = diff_fields(WRI.residual_income_value(bv0, eps, dps, r, roe, g), QV.residual_income(bv0, eps, dps, r, roe, g))
        if d:
            diffs.append((k, d))
    for g in (0.12, 0.13):
        with pytest.raises(WE.TerminalGrowthError):
            WRI.residual_income_value(100.0, [15.0], [3.0], 0.12, 0.15, g)
    _assert_no_diffs(diffs)


def test_I_CMP_02_dividend_discount():
    call_worker(WDDM.dividend_discount_value, 100.0, [15.0], [3.0], 0.13, 0.14, 0.5, 0.05)
    rng, diffs = random.Random(2), []
    for k in range(N):
        bv0, eps, dps, r, roe, payout, g = G.ri_inputs(rng)
        d = diff_fields(WDDM.dividend_discount_value(bv0, eps, dps, r, roe, payout, g),
                        QV.dividend_discount(bv0, eps, dps, r, roe, payout, g))
        if d:
            diffs.append((k, d))
    _assert_no_diffs(diffs)


def test_I_CMP_03_justified_pb_gordon_grid_flag():
    call_worker(WPB.justified_pb, 0.15, 0.12, 0.05)
    rng, diffs = random.Random(3), []
    for k in range(N):
        r, roe = rng.uniform(0.05, 0.2), rng.uniform(0, 0.3)
        g = rng.uniform(-0.05, r - 1e-4)
        for w, m in ((WPB.justified_pb(roe, r, g), QV.justified_pb(roe, r, g)),
                     (WT.gordon_terminal_value(roe, r, g), QV.gordon(roe, r, g))):
            if not same(w, m):
                diffs.append((k, w, m))
        share, warn = rng.uniform(0, 1), rng.uniform(0.5, 0.9)
        if WT.terminal_flag(share, warn) != QV.terminal_flag(share, warn):
            diffs.append((k, "flag", share, warn))
    rates, growths = [0.10, 0.11, 0.12], [0.10, 0.11, 0.12, 0.05]
    fn = lambda r, g: 1 / (r - g)   # noqa: E731
    if not same(WT.sensitivity_grid(fn, rates, growths), QV.sensitivity_grid(fn, rates, growths)):
        diffs.append("grid")
    _assert_no_diffs(diffs)


def test_I_CMP_04_roll_forward():
    call_worker(WRF.roll_forward_value, 100.0, date(2026, 3, 31), date(2026, 10, 25), 0.12)
    rng, diffs = random.Random(4), []
    for k in range(N):
        a = date(2026, 3, 31)
        v = a + timedelta(days=rng.randint(0, 800))
        divs = [(a + timedelta(days=rng.randint(-60, 900)), rng.uniform(0, 30)) for _ in range(rng.randint(0, 4))]
        va, r = rng.uniform(10, 3000), rng.uniform(0.08, 0.18)
        w, m = WRF.roll_forward_value(va, a, v, r, divs), QV.roll_forward(va, a, v, r, divs)
        if not same(w, m):
            diffs.append((k, w, m))
    _assert_no_diffs(diffs)


def _bridge_draw(rng):
    a = date(2026, 3, 31)
    fc = [(date(2027, 3, 31), rng.uniform(-5, 120)), (date(2028, 3, 31), rng.uniform(1, 140))]
    v = a + timedelta(days=rng.randint(0, 731))
    qs = [date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31), date(2027, 3, 31), date(2027, 6, 30),
          date(2027, 9, 30), date(2027, 12, 31), date(2028, 3, 31)]
    n = rng.randint(0, len(qs))
    interim = [(d, rng.uniform(-2, 40)) for d in qs[:n]]
    divs = [(a + timedelta(days=rng.randint(-30, 760)), rng.uniform(0, 20)) for _ in range(rng.randint(0, 3))]
    return a, fc, v, interim, divs


def test_I_CMP_05_equity_bridge():
    """Unambiguous fields always; Forecast_Update_Flag only when interims exist and the accrued
    forecast is positive (F-007)."""
    call_worker(WRF.equity_bridge, 100.0, date(2026, 3, 31), [(date(2027, 3, 31), 18.0)], date(2026, 10, 25))
    rng, diffs = random.Random(5), []
    for k in range(N):
        a, fc, v, interim, divs = _bridge_draw(rng)
        w = WRF.equity_bridge(100.0, a, fc, v, [WRF.InterimResult(d, e) for d, e in interim], divs)
        m = QV.equity_bridge(100.0, a, fc, v, interim, divs)
        rep = [d for d, _ in interim if a < d <= v]
        acc = QV.accrued_forecast_eps(a, fc, a, max(rep)) if rep else 0.0
        skip = () if (rep and acc > 0) else ("forecast_update_flag", "interim_eps_deviation_pct")
        d = diff_fields(w, m, skip=skip)
        if not rep and w.interim_eps_deviation_pct is not None:
            d["interim_eps_deviation_pct"] = (w.interim_eps_deviation_pct, None)
        if d:
            diffs.append((k, d))
    with pytest.raises(WE.ValuationError):
        WRF.equity_bridge(100.0, date(2026, 3, 31), [(date(2027, 3, 31), 18.0)], date(2027, 4, 1))
    _assert_no_diffs(diffs)


def test_I_CMP_05b_equity_bridge_ambiguity_flag_without_interims(record_property):
    """F-007: the contract gives no Forecast_Update_Flag value when no interim results exist (R = A)
    or when the accrued forecast EPS is <= 0. Records the worker's choice."""
    a, fc = date(2026, 3, 31), [(date(2027, 3, 31), 18.0), (date(2028, 3, 31), 20.0)]
    w = call_worker(WRF.equity_bridge, 100.0, a, fc, date(2026, 10, 25))
    neg = WRF.equity_bridge(100.0, a, [(date(2027, 3, 31), -4.0), (date(2028, 3, 31), 20.0)], date(2026, 10, 25),
                            [WRF.InterimResult(date(2026, 6, 30), 1.0)])
    assert w.interim_eps_deviation_pct is None
    record_property("qa_result", "WARNING")
    record_property("qa_evidence", f"no interims: flag={w.forecast_update_flag!r}; negative accrued forecast: "
                                   f"deviation={neg.interim_eps_deviation_pct!r}, flag={neg.forecast_update_flag!r} (F-007)")


def test_I_CMP_06_bank_driver_projection():
    call_worker(WBD.project_bank, WBD.BankBaseYear(1000.0, 1.5, 20.0, 40.0, 200.0, 1e8),
                [WBD.BankDriverYear(0.1, 1.5, 0.04, 0.1, 0.05, 0.01, 0.25, 0.2)])
    rng, diffs = random.Random(6), []
    for k in range(N):
        base = WBD.BankBaseYear(rng.uniform(1e4, 3e6), rng.uniform(1.1, 1.6), rng.uniform(1e3, 5e4),
                                rng.uniform(1e3, 5e4), rng.uniform(1e4, 5e5), float(rng.randint(10**8, 8 * 10**9)))
        drv = [WBD.BankDriverYear(rng.uniform(-0.05, 0.3), rng.uniform(1.1, 1.6), rng.uniform(0.02, 0.05),
                                  rng.uniform(-0.1, 0.3), rng.uniform(-0.05, 0.2), rng.uniform(0, 0.03),
                                  rng.uniform(0.2, 0.35), rng.uniform(0, 0.6),
                                  float(rng.randint(10**8, 8 * 10**9)) if rng.random() < 0.3 else None)
               for _ in range(rng.randint(1, 10))]
        for t, (w, m) in enumerate(zip(WBD.project_bank(base, drv), QV.project_bank(base, drv))):
            d = diff_fields(w, m)
            if d:
                diffs.append((k, t, d))
    _assert_no_diffs(diffs)


def test_I_CMP_07_insurance_sotp():
    a = WINS.SOTPInputs(20_000.0, 0.8, 500.0, 300.0, 0.0, 345_000_000, 0.1, 2_000.0, 15.0)
    call_worker(WINS.sotp_value_per_share, a)
    rng, diffs = random.Random(7), []
    for k in range(N):
        method_a = rng.random() < 0.5
        kw = dict(embedded_value=rng.uniform(1e3, 1e5), stake_pct=rng.uniform(0.3, 1), parent_cash=rng.uniform(0, 2e3),
                  parent_debt=rng.uniform(0, 2e3), other_parent_net_assets=rng.uniform(-500, 500),
                  diluted_parent_shares=float(rng.randint(10**8, 10**9)), holdco_discount_pct=rng.uniform(0, 0.3))
        if method_a:
            vnb, mult, pev = rng.uniform(100, 5e3), rng.uniform(5, 25), None
        else:
            vnb, mult, pev = None, None, rng.uniform(0.8, 4)
        w = WINS.sotp_value_per_share(WINS.SOTPInputs(**kw, vnb=vnb, vnb_multiple=mult, target_p_ev=pev))
        m = QV.sotp_per_share(kw["embedded_value"], kw["stake_pct"], kw["parent_cash"], kw["parent_debt"],
                              kw["other_parent_net_assets"], kw["diluted_parent_shares"], kw["holdco_discount_pct"],
                              vnb, mult, pev)
        if not same(w, m):
            diffs.append((k, w, m))
    _assert_no_diffs(diffs)


def test_I_CMP_08_blend_and_peer_relative():
    call_worker(WBL.blend_fair_value, {"RI": 1.0}, {"RI": 1.0})
    rng, diffs = random.Random(8), []
    for k in range(N):
        ms = ["RI", "DDM", "PB", "PEER"][: rng.randint(1, 4)]
        raw = [rng.random() for _ in ms]
        weights = {m: x / sum(raw) for m, x in zip(ms, raw)}
        if rng.random() < 0.3:
            weights[ms[0]] = 0.0
            rest = sum(v for kk, v in weights.items() if kk != ms[0]) or 1.0
            weights = {kk: (0.0 if kk == ms[0] else v / rest) for kk, v in weights.items()}
            if sum(weights.values()) == 0:
                continue
        values = {m: (None if rng.random() < 0.15 else rng.uniform(10, 2000)) for m in ms}
        if abs(sum(weights.values()) - 1) > 1e-12:
            continue
        if not same(WBL.blend_fair_value(values, weights), QV.blend(values, weights)):
            diffs.append((k, values, weights))
        mult, metric, n = (None if rng.random() < 0.1 else rng.uniform(0.5, 5)), rng.uniform(10, 900), rng.randint(0, 8)
        w, m = WPR.peer_relative_value(mult, metric, n), QV.peer_relative(mult, metric, n)
        if not (same(w.value, m.value) and str(w.flag) == m.flag):
            diffs.append((k, "peer", mult, n, w, m))
    _assert_no_diffs(diffs)


# =========================================================================== controls (03-nav)
MODES = [M.ORIGINAL, M.SHOCK, M.ABSOLUTE]
FVMODES = [F.MODEL_BASE, F.FUNDAMENTAL, F.MANUAL_BIAS]


def _controls_draw(rng, ambiguous: bool):
    def maybe(x, p=0.5):
        return x if rng.random() < p else 0.0
    base = None if rng.random() < 0.15 else rng.uniform(1, 5000)
    inp = WP.PriceControlInputs(
        original_market_price=(None if ambiguous and rng.random() < 0.5 else rng.uniform(1, 5000)),
        model_fv_base=base,
        model_fv_bear=None if base is None else base * rng.uniform(0.5, 1),
        model_fv_bull=None if base is None else base * rng.uniform(1, 1.6),
        market_price_mode=rng.choice(MODES), market_price_shock_pct=maybe(rng.uniform(-0.6, 0.6)),
        absolute_scenario_price=(rng.uniform(1, 5000) if rng.random() < 0.5 else None),
        fair_value_mode=rng.choice(FVMODES), fundamental_case=rng.choice(list(Case)),
        fair_value_bias_pct=maybe(rng.uniform(-0.6, 0.6)), required_margin_of_safety_pct=rng.uniform(0, 0.6),
        sector_shock_pct=maybe(rng.uniform(-0.3, 0.3)), global_shock_pct=maybe(rng.uniform(-0.3, 0.3)))
    is_ambiguous = (inp.original_market_price is None or
                    (base is None and inp.market_price_mode == M.ABSOLUTE and inp.absolute_scenario_price is None))
    return inp, is_ambiguous


def _label_ok(worker_label: str, mine: str, mode) -> bool:
    if mode == F.MANUAL_BIAS:      # F-006: number format of "<bias>%" is not fixed by the contract
        return worker_label.startswith("MANUALLY BIASED fair value (") and worker_label.endswith("%)")
    return worker_label == mine


def _status_ok(w: str, m: str) -> bool:
    return w.startswith("FAIL") if m.startswith("FAIL") else w == m


def test_I_CMP_10_resolve_controls():
    call_worker(WP.resolve_controls, WP.PriceControlInputs(750.0, 500.0))
    rng, diffs, n = random.Random(10), [], 0
    while n < N:
        inp, amb = _controls_draw(rng, ambiguous=False)
        if amb:
            continue
        n += 1
        w, m = WP.resolve_controls(inp), QC.resolve(QC.from_worker_inputs(inp))
        d = diff_fields(w, m, skip=("fv_label", "control_status"))
        if not _label_ok(w.fv_label, m.fv_label, inp.fair_value_mode):
            d["fv_label"] = (w.fv_label, m.fv_label)
        if not _status_ok(w.control_status, m.control_status):
            d["control_status"] = (w.control_status, m.control_status)
        if d:
            diffs.append((n, inp, d))
    _assert_no_diffs(diffs)


def test_I_CMP_10b_resolve_controls_ambiguity_status_precedence(record_property):
    """F-005: Control_Status when the original price is blank, or when an unvalued security is in
    Absolute mode with a blank price. Records the worker's choice; price/FV values must still agree."""
    call_worker(WP.resolve_controls, WP.PriceControlInputs(750.0, 500.0))
    rng, seen, diffs, n = random.Random(11), {}, [], 0
    while n < N // 4:
        inp, amb = _controls_draw(rng, ambiguous=True)
        if not amb:
            continue
        n += 1
        w, m = WP.resolve_controls(inp), QC.resolve(QC.from_worker_inputs(inp))
        key = ("P0 blank" if inp.original_market_price is None else "unvalued+absolute blank", str(inp.market_price_mode))
        seen.setdefault(key, set()).add(w.control_status)
        d = diff_fields(w, m, skip=("fv_label", "control_status"))
        if d:
            diffs.append((n, d))
    _assert_no_diffs(diffs)
    record_property("qa_result", "WARNING")
    record_property("qa_evidence", f"worker Control_Status in ambiguous cases: { {k: sorted(v) for k, v in seen.items()} } (F-005)")


# =========================================================================== NAV engine (03-nav)
def test_I_CMP_11_classification_and_match_status():
    call_worker(WC.coverage_status, K.MF001[0])
    rng, diffs = random.Random(12), []
    for k in range(N // 2):
        lines, _, _ = G.fund(rng, allow_unmatched=True, allow_mpt=True)
        for l in lines:
            for case in ("Base", "Bear", "Bull", "Selected"):
                if not same(WC.coverage_status(l, case), QN.coverage_status(l, case)):
                    diffs.append((k, l.line_id, case, WC.coverage_status(l, case), QN.coverage_status(l, case)))
            if not same(WCOV.match_status(l), QN.match_status(l)):
                diffs.append((k, l.line_id, "match", WCOV.match_status(l), QN.match_status(l)))
    _assert_no_diffs(diffs)


def _nav_compare(fn_w, fn_m, *, seed, mpt=False, unmatched=False, cases=("Base", "Bear", "Bull", "Selected"),
                 scen=False, fields=("nav", "sum_adjustment", "na_market_inr_cr", "na_numerator_inr_cr")):
    rng, diffs = random.Random(seed), []
    for k in range(N):
        lines, nav, _ = G.fund(rng, allow_mpt=mpt, allow_unmatched=unmatched)
        if scen:
            lines = [dataclasses.replace(l, scenario_price_inr=l.price_inr * rng.uniform(0.5, 1.5))
                     if l.price_inr is not None else l for l in lines]
            pairs = [(fn_w(nav, lines), fn_m(nav, lines))]
        else:
            pairs = [(fn_w(nav, lines, c), fn_m(nav, lines, c)) for c in cases]
        for w, m in pairs:
            d = {f: (getattr(w, f), getattr(m, f)) for f in fields
                 if getattr(m, f) is not None and not same(getattr(w, f), getattr(m, f))}
            if d:
                diffs.append((k, d))
    return diffs


def test_I_CMP_12_method1_weighted_adjustment():
    call_worker(WM.weighted_adjustment_nav, 80.0, K.MF001, "Base")
    rng, diffs = random.Random(13), []
    for k in range(N):
        lines, nav, _ = G.fund(rng, allow_mpt=True, allow_unmatched=True)
        for c in ("Base", "Bear", "Bull", "Selected"):
            w, m = WM.weighted_adjustment_nav(nav, lines, c), QN.weighted_adjustment_nav(nav, lines, c)
            d = diff_fields(w, m, fields=["nav", "sum_adjustment", "adjustment_by_line", "adjustment_by_sector"])
            if d:
                diffs.append((k, c, d))
    _assert_no_diffs(diffs)


def test_I_CMP_13_method2_quantity_based():
    call_worker(WM.quantity_based_nav, 80.0, K.MF001, "Base")
    _assert_no_diffs(_nav_compare(WM.quantity_based_nav, QN.quantity_based_nav, seed=14))


def test_I_CMP_13b_method2_ambiguity_market_pass_through_basis(record_property):
    """F-001: are MARKET_PASS_THROUGH positions in NA at their disclosed value (contract §7.3 text)
    or at q × P (link_patterns.H_MV_MKT)? Passes if the worker matches one reading consistently."""
    call_worker(WM.quantity_based_nav, 80.0, K.MF001, "Base")
    rng, hits = random.Random(15), {"disclosed": 0, "market": 0, "neither": 0}
    for _ in range(N // 2):
        lines, nav, _ = G.fund(rng, allow_mpt=True)
        lines = [dataclasses.replace(l, market_value_inr_cr=l.market_value_inr_cr * 1.03)
                 if str(l.asset_class) == "Debt securities" else l for l in lines]    # disclosed ≠ q × P
        if not any(str(l.asset_class) == "Debt securities" for l in lines):
            continue
        w = WM.quantity_based_nav(nav, lines, "Base").nav
        if same(w, QN.quantity_based_nav(nav, lines, "Base", mpt_basis="disclosed").nav):
            hits["disclosed"] += 1
        elif same(w, QN.quantity_based_nav(nav, lines, "Base", mpt_basis="market").nav):
            hits["market"] += 1
        else:
            hits["neither"] += 1
    record_property("qa_result", "WARNING")
    record_property("qa_evidence", f"worker Method 2 basis for MARKET_PASS_THROUGH positions: {hits} (F-001)")
    assert hits["neither"] == 0 and min(hits["disclosed"], hits["market"]) == 0, hits


def test_I_CMP_13c_method2_ambiguity_unmarkable_lines(record_property):
    """F-001: the contract says Method 2/3 show #N/A for a POSITION that is not MATCHED, but
    NavResult.nav is typed float. Records what the worker returns."""
    lines = [dataclasses.replace(l, price_inr=None) if l.line_id == "MF001-L3" else l for l in K.MF001]
    try:
        r = call_worker(WM.quantity_based_nav, 80.0, lines, "Base")
        outcome = f"returned nav={r.nav!r}"
        ok = r.nav is None
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001 - recording the behaviour is the point
        outcome, ok = f"raised {type(exc).__name__}: {exc}", True
    record_property("qa_result", "WARNING")
    record_property("qa_evidence", f"Method 2 with an unpriced POSITION: {outcome} (F-001)")
    assert ok, f"an unmarkable line must not produce a number: {outcome}"


def test_I_CMP_14_method3_scenario_market_nav():
    call_worker(WM.scenario_market_nav, 80.0, K.MF001)
    _assert_no_diffs(_nav_compare(WM.scenario_market_nav, QN.scenario_market_nav, seed=16, scen=True))


def test_I_CMP_15_reconciliation_and_holdings_coverage():
    call_worker(WM.reconcile_net_assets, K.MF001, 1000.0, 0.005)
    rng, diffs = random.Random(17), []
    for k in range(N):
        lines, _, reported = G.fund(rng, allow_unmatched=True, allow_mpt=True)
        d = diff_fields(WM.reconcile_net_assets(lines, reported, 0.005), QN.reconcile(lines, reported, 0.005))
        d.update(diff_fields(WCOV.holdings_coverage(lines, reported, 0.005), QN.holdings_coverage(lines, reported, 0.005)))
        if d:
            diffs.append((k, d))
    _assert_no_diffs(diffs)


def test_I_CMP_16_valuation_coverage_and_caption():
    call_worker(WCOV.coverage_summary, K.MF001, 0.9, 0.75)
    rng, diffs = random.Random(18), []
    for k in range(N):
        lines, _, _ = G.fund(rng, unvalued_share=rng.uniform(0, 0.8), allow_unmatched=True, allow_mpt=True)
        for c in ("Base", "Bear", "Bull"):
            d = diff_fields(WCOV.coverage_summary(lines, 0.9, 0.75, c), QN.coverage_summary(lines, 0.9, 0.75, c))
            if d:
                diffs.append((k, c, d))
    _assert_no_diffs(diffs)


def test_I_CMP_17_freshness():
    V = date(2026, 10, 23)
    call_worker(WCOV.freshness_summary, K.MF001, date(2026, 9, 30), V, V, 45, 135, 3)
    rng, diffs = random.Random(19), []
    for k in range(N):
        lines, _, _ = G.fund(rng)
        pd, nd = V - timedelta(days=rng.randint(0, 90)), V - timedelta(days=rng.randint(0, 10))
        w = WCOV.freshness_summary(lines, pd, nd, V, 45, 135, 3)
        m = QN.freshness_summary(lines, pd, nd, V, 45, 135, 3)
        d = diff_fields(w, m)
        if d:
            diffs.append((k, d))
    _assert_no_diffs(diffs)


def test_I_CMP_18_allocation_hypothetical_overlap():
    AL = WCA.AllocationLine
    alloc = [AL("H1", "Financial Services", "S90001", 0.30, 0.20), AL("H2", "Financial Services", "S90002", 0.30, 0.80),
             AL("H3", "Information Technology", "S90004", 0.60, 1.00), AL("H4", "Not applicable", None, 0.10, 1.00)]
    call_worker(WCA.effective_weights, alloc)
    assert same(WCA.effective_weights(alloc), QN.effective_weights(alloc))
    assert bool(WCA.validate_allocation(alloc)) == bool(QN.validate_allocation(alloc))
    rng, diffs = random.Random(20), []
    for k in range(N):
        lines = [WR.HypoLineInput(f"S{i}", rng.uniform(0, 0.4), rng.uniform(10, 4000),
                                  None if rng.random() < 0.2 else rng.uniform(10, 4000),
                                  rng.uniform(10, 4000) if rng.random() < 0.2 else None,
                                  float(rng.randint(0, 3000)) if rng.random() < 0.1 else None) for i in range(rng.randint(1, 6))]
        cap, tc = rng.uniform(1e5, 1e8), rng.uniform(0, 0.005)
        w, m = WR.build_hypothetical_portfolio(cap, lines, tc), QN.build_hypothetical_portfolio(cap, lines, tc)
        d = diff_fields(w, m, skip=("lines",))
        for lw, lm in zip(w.lines, m.lines):
            d.update({f"line {lm.security_id}": dd for dd in [diff_fields(lw, lm)] if dd})
        if d:
            diffs.append((k, d))
        a = {f"S{i}": rng.random() for i in range(8) if rng.random() < 0.6}
        b = {f"S{i}": rng.random() for i in range(8) if rng.random() < 0.6}
        if not same(WO.overlap_by_weight(a, b), QN.overlap_by_weight(a, b)):
            diffs.append((k, "overlap"))
    _assert_no_diffs(diffs)


def test_I_CMP_19_peer_statistic():
    members = [{"Security_ID": "P1", "Included": True}]
    call_worker(WPT.peer_statistic, members, {"P1": {"Value": 1.0, "Is_Meaningful": True}})
    rng, diffs = random.Random(21), []
    for k in range(N):
        n = rng.randint(0, 9)
        members = [{"Security_ID": f"P{i}", "Included": rng.random() < 0.8} for i in range(n)]
        metric = {f"P{i}": {"Value": None if rng.random() < 0.15 else rng.uniform(0.3, 6),
                            "Is_Meaningful": rng.random() < 0.85} for i in range(n)}
        subj = f"P{rng.randint(0, n)}" if rng.random() < 0.5 else None
        d = diff_fields(WPT.peer_statistic(members, metric, exclude_security_id=subj),
                        QV.peer_statistic(members, metric, subj))
        if d:
            diffs.append((k, d))
    _assert_no_diffs(diffs)
