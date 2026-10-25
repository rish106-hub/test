"""Contract §4. Owner: 02-valuation."""
import dataclasses

import pytest

from src.valuations.errors import DoubleCountingError
from src.valuations.insurance_sotp import SOTPInputs, appraisal_value, sotp_value_per_share

pytestmark = pytest.mark.owner("02-valuation")

# SYNTHETIC: EV 20,000 Cr, VNB 2,000 Cr x 15, stake 80%, holdco discount 10%,
# parent cash 500, debt 300, 34.5 crore diluted shares.
A = SOTPInputs(embedded_value=20_000.0, stake_pct=0.80, parent_cash=500.0, parent_debt=300.0,
               other_parent_net_assets=0.0, diluted_parent_shares=345_000_000, holdco_discount_pct=0.10,
               vnb=2_000.0, vnb_multiple=15.0)


def test_T_INS_01_method_a_hand_computed():
    assert appraisal_value(A) == pytest.approx(50_000.0)
    # 0.8 x 50,000 x 0.9 + 500 - 300 = 36,200 Cr -> x 1e7 / 3.45e8 = 1,049.2754 INR
    assert sotp_value_per_share(A) == pytest.approx(1049.27536231884)


def test_T_INS_02_method_b():
    b = dataclasses.replace(A, vnb=None, vnb_multiple=None, target_p_ev=2.0)
    assert appraisal_value(b) == pytest.approx(40_000.0)
    assert sotp_value_per_share(b) == pytest.approx((0.8 * 40_000 * 0.9 + 200) * 1e7 / 345_000_000)


def test_T_INS_03_both_methods_is_double_counting():
    with pytest.raises(DoubleCountingError):
        appraisal_value(dataclasses.replace(A, target_p_ev=2.0))


def test_T_INS_04_neither_method_is_rejected():
    with pytest.raises(DoubleCountingError):
        appraisal_value(dataclasses.replace(A, vnb=None, vnb_multiple=None))
