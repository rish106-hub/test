"""Contract §7.6, §7.8 and spec manual test 4. Owner: 03-nav."""
import pytest

from src.fund_nav.custom_allocation import AllocationLine, effective_weights, validate_allocation
from src.fund_nav.overlap import overlap_by_weight
from src.fund_nav.rebalance import HypoLineInput, build_hypothetical_portfolio
from tests.contract import cases as K

pytestmark = pytest.mark.owner("03-nav")
approx = pytest.approx

ALLOC = [
    AllocationLine("H1", "Financial Services", "S90001", 0.30, 0.20),
    AllocationLine("H2", "Financial Services", "S90002", 0.30, 0.80),
    AllocationLine("H3", "Information Technology", "S90004", 0.60, 1.00),
    AllocationLine("H4", "Not applicable", None, 0.10, 1.00),   # explicit cash
]


def test_T_CUS_01_effective_weight_is_sector_times_constituent():
    w = effective_weights(ALLOC)
    assert w["S90001"] == approx(0.06)   # spec <example>: 30% x 20% = 6%
    assert w["S90002"] == approx(0.24)
    assert w["CASH"] == approx(0.10)
    assert sum(w.values()) == approx(1.0)


def test_T_CUS_02_validation_failures():
    assert validate_allocation(ALLOC) == []
    no_cash = ALLOC[:3]
    assert validate_allocation(no_cash)                  # sector weights 0.9: must declare cash
    bad_split = [AllocationLine("H1", "Financial Services", "S90001", 0.3, 0.5)] + ALLOC[2:]
    assert validate_allocation(bad_split)                # constituent sum 0.5 within sector
    dup = ALLOC + [AllocationLine("H5", "Information Technology", "S90001", 0.0, 0.0)]
    assert validate_allocation(dup)                      # duplicate Security_ID
    neg = [AllocationLine("H1", "Financial Services", "S90001", 0.3, -0.2)] + ALLOC[1:]
    assert validate_allocation(neg)


def test_T_CUS_03_custom_allocation_does_not_touch_actual_holdings():
    before = [vars(l).copy() for l in K.MF001]
    effective_weights(ALLOC)
    validate_allocation(ALLOC)
    assert [vars(l) for l in K.MF001] == before


def test_T_HYP_01_hypothetical_portfolio_hand_computed():
    lines = [HypoLineInput("S90001", 0.6, 595.0, 500.0), HypoLineInput("S90002", 0.4, 90.0, 120.0)]
    r = build_hypothetical_portfolio(1_000_000.0, lines, 0.001)
    q = {l.security_id: l.quantity for l in r.lines}
    assert q == {"S90001": 1007, "S90002": 4440}     # floor(600000 / 595.595), floor(400000 / 90.09)
    assert r.cash_remaining_inr == approx(1_000_000 - 599_165 - 599.165 - 399_600 - 399.6)
    assert r.value_market_inr == approx(1007 * 595 + 4440 * 90 + r.cash_remaining_inr)
    assert r.value_fair_inr == approx(1007 * 500 + 4440 * 120 + r.cash_remaining_inr)
    assert r.status == "PASS"


def test_T_HYP_02_overspending_fails_visibly():
    lines = [HypoLineInput("S90001", 1.0, 595.0, 500.0, quantity_override=2000)]
    assert build_hypothetical_portfolio(1_000_000.0, lines, 0.0).status == "FAIL"


def test_T_OVL_01_overlap():
    a = {l.security_id: l.weight for l in K.MF001 if l.security_id}
    b = {l.security_id: l.weight for l in K.MF002 if l.security_id}
    pct, n = overlap_by_weight(a, b)
    assert pct == approx(0.20) and n == 1
