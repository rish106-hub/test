"""The validation runner never reports a check that did not run as PASS (CLAUDE.md, test plan)."""
from qa.run_validation import check_id, classify


def _e(setup="passed", call=None, xfail=None, props=None, setup_text=""):
    ph = {"setup": {"outcome": setup, "text": setup_text, "wasxfail": None}}
    if call:
        ph["call"] = {"outcome": call, "text": "E   assert 1 == 2", "wasxfail": xfail}
    return {"phases": ph, "props": props or {}}


def test_QA_RUN_01_result_mapping():
    assert classify(_e(call="passed"))[:2] == ("PASS", True)
    assert classify(_e(call="passed", props={"qa_result": "WARNING"}))[:2] == ("WARNING", True)
    assert classify(_e(call="failed"))[:2] == ("FAIL", True)
    assert classify(_e(call="skipped"))[:2] == ("NOT RUN", False)
    assert classify(_e(setup="skipped", setup_text="Skipped: NOT RUN: no soffice"))[:2] == ("NOT RUN", False)
    assert classify(_e(setup="failed"))[:2] == ("NOT RUN", False)                  # errored is never PASS
    assert classify(_e())[:2] == ("NOT RUN", False)                                # no call phase
    assert classify(_e(call="skipped", xfail="known finding F-1"))[:2] == ("FAIL", True)
    assert classify(_e(call="passed", xfail="known finding F-1"))[:2] == ("PASS", True)


def test_QA_RUN_02_check_ids():
    assert check_id("test_T_NAV_02_method1_mf001[Base-75.2]", "Base-75.2") == "T-NAV-02[Base-75.2]"
    assert check_id("test_W_10a_manual_test_1_market_shock", None) == "W-10a"
    assert check_id("test_I_PROP_06c_total_coverage", None) == "I-PROP-06c"
    assert check_id("test_W_02_no_error_values", None) == "W-02"
    assert check_id("test_PROV_01_every_source_id", None) == "PROV-01"
    assert check_id("test_E_04_hdfc[manual_1_shock]", "manual_1_shock") == "E-04[manual_1_shock]"
