"""spec <unique_identifier_rule>, <monthly_update_workflow>. Owner: 01-data."""
import pytest

from src.ingestion.holdings_import import diff_portfolios
from src.ingestion.registry import match_security, next_security_id

pytestmark = pytest.mark.owner("01-data")

REG = [{"Security_ID": "S00001", "ISIN": "INE000A01001", "Exchange_Ticker": "AAA", "Company_Name": "Same Name Ltd"},
       {"Security_ID": "S00002", "ISIN": "INE000B01002", "Exchange_Ticker": "BBB", "Company_Name": "Same Name Ltd"},
       {"Security_ID": "S00007", "ISIN": "", "Exchange_Ticker": "CCC", "Company_Name": "Other"}]


def test_T_ING_01_match_by_isin_never_by_name():
    assert match_security("INE000B01002", None, REG) == "S00002"
    assert match_security(None, "CCC", REG) == "S00007"
    assert match_security("INE999Z01009", None, REG) is None


def test_T_ING_02_ids_are_never_reused():
    assert next_security_id(REG) == "S00008"


def test_T_ING_03_monthly_diff():
    prev = [{"Security_ID": "S00001", "ISIN": "INE000A01001", "Weight_Pct_of_Scheme_NAV": "0.6", "Line_Role": "POSITION"},
            {"Security_ID": "S00002", "ISIN": "INE000B01002", "Weight_Pct_of_Scheme_NAV": "0.4", "Line_Role": "POSITION"}]
    cur = [{"Security_ID": "S00001", "ISIN": "INE000A01001", "Weight_Pct_of_Scheme_NAV": "0.5", "Line_Role": "POSITION"},
           {"Security_ID": "", "ISIN": "INE555N01005", "Weight_Pct_of_Scheme_NAV": "0.45", "Line_Role": "POSITION"},
           {"Security_ID": "", "ISIN": "", "Weight_Pct_of_Scheme_NAV": "0.05", "Line_Role": "ONA_ASSET"}]
    d = diff_portfolios(prev, cur, tolerance=0.005)
    assert d.removed == ("S00002",)
    assert d.unmatched_isins == ("INE555N01005",)
    assert d.weight_sum == pytest.approx(1.0) and d.weight_sum_status == "PASS"
