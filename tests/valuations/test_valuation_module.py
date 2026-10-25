"""02-valuation unit tests beyond the frozen contract tests: input selection, method guard,
composite-model edge cases, assumptions file and fixtures. No LibreOffice needed."""
from __future__ import annotations

import copy
import dataclasses
from datetime import date

import pytest

from build.data_loader import load_model_data
from src.common import schema as S
from src.common.validate import validate_csv
from src.valuations import parameters as P
from src.valuations.bank_model import add_months, run_bank_model
from src.valuations.errors import MethodNotAllowedError, ValuationError
from src.valuations.expected_return import reinvested_total_return, xirr
from src.valuations.fixtures import augment_test_fixtures
from src.valuations.inputs import ObservationIndex, gather_bank_spec, model_inputs
from src.valuations.method_selection import validate_method_for_business_model
from src.valuations.reference import missing_critical_inputs
from src.valuations.rollforward import roll_forward_value
from tests.valuations import make_valuation_fixtures as FX

pytestmark = pytest.mark.owner("02-valuation")
SID = "S90001"


@pytest.fixture(scope="module")
def data():
    d = load_model_data(test_build=True)
    augment_test_fixtures(d)
    return d


def _spec(d):
    reg = {r["Security_ID"]: r for r in d.rows("security_registry")}
    return gather_bank_spec(d, reg[SID])


# ---------------------------------------------------------------- fixtures and assumptions file
def test_fixtures_are_in_sync_with_their_generator():
    assert FX.main(check=True) == 0


def test_production_assumptions_csv_is_valid_and_holds_only_data_free_defaults():
    assert validate_csv(S.ASSUMPTIONS, "data/canonical/assumptions.csv") == []
    rows = P.parse_rows(load_model_data(test_build=False).rows("assumptions"))
    assert {r.parameter for r in rows} == {"W_RI", "W_DDM", "W_JPB", "W_PEER_PB"}
    assert {(r.parameter, r.value) for r in rows if r.value} == {("W_RI", 1.0)}          # D-009
    assert all(r.scope == "GLOBAL" and r.rationale and r.source_type == "User assumption" for r in rows)


def test_fixture_augmentation_is_test_build_only_and_idempotent():
    prod = load_model_data(test_build=False)
    assert augment_test_fixtures(prod) == []
    d = load_model_data(test_build=True)
    assert set(augment_test_fixtures(d)) == {"raw_financials", "corporate_actions", "assumptions"}
    assert augment_test_fixtures(d) == []


# ---------------------------------------------------------------- observation selection
def test_superseded_and_other_basis_observations_are_never_used(data):
    idx = ObservationIndex(data.rows("raw_financials"), "E9001", "Standalone", date(2026, 10, 23))
    np25 = idx.get("NET_PROFIT_COMMON", date(2025, 3, 31), annual=True)
    restated = next(r for r in data.rows("raw_financials") if r["Supersedes_Observation_ID"])
    assert np25.observation_id == restated["Observation_ID"]                 # the restatement, not the original
    assert idx.get("COMMON_EQUITY", date(2026, 3, 31), annual=True).value == 25_000.0   # not the consolidated 31,000
    assert idx.problems == []


def test_point_in_time_excludes_observations_not_yet_known(data):
    idx = ObservationIndex(data.rows("raw_financials"), "E9001", "Standalone", date(2026, 10, 1))
    assert idx.get("EPS_DILUTED", date(2026, 9, 30), annual=False) is None   # known 2026-10-18
    assert idx.get("EPS_DILUTED", date(2026, 6, 30), annual=False).value == 15.0


def test_anchor_is_the_latest_fiscal_year_balance_sheet_on_or_before_v(data):
    spec = _spec(data)
    assert spec.anchor_date == date(2026, 3, 31)
    assert spec.fy_labels == ("FY2027", "FY2028", "FY2029", "FY2030", "FY2031", "FY2032")
    assert [o.period_end for o in spec.interims] == [date(2026, 6, 30), date(2026, 9, 30)]
    assert [d.action_id for d in spec.dividends] == ["CA-SYNTH-0003"]        # the 2025 dividend is before A
    assert spec.share_actions == []                                          # the 2019 split is before A
    assert spec.history_fy[0] == ("FY2017", date(2017, 3, 31)) and len(spec.history_fy) == 10
    assert spec.history_q[-1] == ("Q2FY2027", date(2026, 9, 30)) and len(spec.history_q) == 20


def test_assumption_resolution_prefers_the_most_specific_row():
    rows = [P.AssumptionRow(i, s, c, "NIM", p, v, "decimal", "User assumption", "", "x") for i, s, c, p, v in [
        ("a", "GLOBAL", "All", "ALL", 0.01), ("b", "S1", "All", "ALL", 0.02), ("c", "S1", "Base", "ALL", 0.03),
        ("d", "S1", "Base", "FY2028", 0.04)]]
    res = P.AssumptionResolver(rows)
    assert res.resolve("S1", "Base", "NIM", "FY2028").assumption_id == "d"
    assert res.resolve("S1", "Base", "NIM", "FY2027").assumption_id == "c"
    assert res.resolve("S1", "Bear", "NIM", "FY2027").assumption_id == "b"
    assert res.resolve("S2", "Bear", "NIM", "FY2027").assumption_id == "a"
    assert P.AssumptionResolver(rows[1:2]).resolve("S2", "Base", "NIM") is None


def test_blank_assumption_value_is_not_set():
    rows = P.parse_rows([dict(Assumption_ID="x", Scope="S1", Case="All", Parameter="BETA", Period="ALL", Value="")])
    assert rows == []


# ---------------------------------------------------------------- R004 guard
@pytest.mark.parametrize("bm, method", [("Small finance bank", "FCFF DCF (WACC)"), ("Deposit-taking bank", "EV multiple"),
                                        ("Deposit-taking bank", "Peer-relative P/B"),
                                        ("Insurance holding company", "Residual Income"), ("Deposit-taking bank", "nonsense")])
def test_disallowed_primary_methods_raise(bm, method):
    with pytest.raises(MethodNotAllowedError):
        validate_method_for_business_model(bm, method)


@pytest.mark.parametrize("bm, method", [("Deposit-taking bank", "Dividend Discount"), ("Insurance holding company",
                                         "Insurance SOTP"), ("Non-financial operating company", "FCFF DCF (WACC)"),
                                        ("Deposit-taking bank", "None")])
def test_allowed_primary_methods_pass(bm, method):
    validate_method_for_business_model(bm, method)


def test_registry_fcff_for_a_bank_is_reported_not_used(data):
    d = copy.deepcopy(data)
    for r in d.rows("security_registry"):
        if r["Security_ID"] == SID:
            r["Primary_Valuation_Method"] = "FCFF DCF (WACC)"
    spec = _spec(d)
    assert spec.method_check.startswith("FAIL") and "R004" in spec.method_check
    assert run_bank_model(model_inputs(spec)).fair_values["Base"] is not None   # valued by RI regardless


# ---------------------------------------------------------------- composite model
def test_missing_input_gives_none_never_zero(data):
    spec = _spec(data)
    spec = dataclasses.replace(spec, security_inputs={**spec.security_inputs, "BETA": None})
    res = run_bank_model(model_inputs(spec))
    assert res.cost_of_equity is None and res.fair_values == {"Bear": None, "Base": None, "Bull": None}
    assert res.coverage_status == "UNVALUED" and res.tv_share_base is None
    assert missing_critical_inputs(spec) == 1


def test_fair_value_is_the_roll_forward_of_the_ri_value(data):
    spec = _spec(data)
    inp = model_inputs(spec)
    res = run_bank_model(inp)
    base = res.cases["Base"]
    expected = roll_forward_value(base.ri.value_at_anchor, inp.anchor_date, inp.valuation_date,
                                  res.cost_of_equity, inp.dividends)
    assert res.fair_values["Base"] == pytest.approx(expected, rel=1e-12)


def test_cases_are_independent_driver_sets(data):
    spec = _spec(data)
    res0 = run_bank_model(model_inputs(spec))
    drivers = dict(spec.drivers)
    row = drivers[("Bear", "NIM", 1)]
    for t in range(1, P.FORECAST_YEARS + 1):
        drivers[("Bear", "NIM", t)] = dataclasses.replace(row, value=0.03)
    res1 = run_bank_model(model_inputs(dataclasses.replace(spec, drivers=drivers)))
    assert res1.fair_values["Bear"] < res0.fair_values["Bear"]
    assert res1.fair_values["Base"] == res0.fair_values["Base"] and res1.fair_values["Bull"] == res0.fair_values["Bull"]


def test_valuation_date_beyond_the_forecast_fails_the_bridge_and_the_exit(data):
    spec = _spec(data)
    inp = dataclasses.replace(model_inputs(spec), valuation_date=date(2032, 6, 30))
    res = run_bank_model(inp)
    assert res.bridge is None and res.bridge_status.startswith("FAIL")
    assert res.freshness_status == "FAIL"                                   # anchor far older than 425 days
    assert res.cases["Base"].expected_return.status.startswith("FAIL")


def test_weights_must_sum_to_one(data):
    spec = _spec(data)
    w = dict(spec.weights)
    w["W_DDM"] = dataclasses.replace(w["W_RI"], value=0.5)
    res = run_bank_model(model_inputs(dataclasses.replace(spec, weights=w)))
    assert res.weights_status == "FAIL" and res.fair_values["Base"] is None


def test_dividend_already_paid_in_the_year_of_v_is_not_received_again(data):
    spec = _spec(data)
    res = run_bank_model(model_inputs(spec))
    base = res.cases["Base"]
    er = base.expected_return
    # FY2027 dividend at FYE_1 is net of the 11.0 paid on 2026-06-20 (ex in (A, V])
    assert er.dividends_received[0] == pytest.approx(max(0.0, base.projection[0].dps - 11.0))
    assert er.dividends_received[-1] == 0.0                                  # FYE_6 is after the exit date
    assert er.exit_date == date(2031, 10, 23)


def test_reinvested_return_equals_xirr_when_reinvesting_at_the_xirr():
    flows_d = [date(2026, 1, 1), date(2027, 1, 1), date(2028, 1, 1)]
    r = xirr([-100.0, 10.0, 110.0], flows_d)
    assert reinvested_total_return(100.0, flows_d[0], flows_d[2], [(flows_d[1], 10.0)], 110.0, r) == pytest.approx(r)


def test_add_months_matches_excel_edate():
    assert add_months(date(2026, 3, 31), 12) == date(2027, 3, 31)
    assert add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert add_months(date(2026, 10, 23), 60) == date(2031, 10, 23)


def test_bank_spec_without_financials_is_unvalued_with_every_input_missing(data):
    d = copy.deepcopy(data)
    d.tables["raw_financials"] = []
    spec = _spec(d)
    assert spec.anchor_date is None and spec.fy_ends == ()
    res = run_bank_model(model_inputs(spec))
    assert res.coverage_status == "UNVALUED" and res.freshness_status == "MISSING"
    with pytest.raises(ValuationError):
        roll_forward_value(1.0, date(2026, 3, 31), date(2026, 1, 1), 0.1)
