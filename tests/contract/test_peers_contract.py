"""Contract §9. Owner: 04-charts."""
import pytest

from src.peers.peer_table import peer_statistic

pytestmark = pytest.mark.owner("04-charts")

MEMBERS = [{"Security_ID": s, "Included": inc} for s, inc in
           [("P1", True), ("P2", True), ("P3", True), ("P4", False), ("P5", True), ("SUBJ", True)]]
PB = {"P1": {"Value": 2.0, "Is_Meaningful": True}, "P2": {"Value": 3.0, "Is_Meaningful": True},
      "P3": {"Value": 4.0, "Is_Meaningful": True}, "P4": {"Value": 99.0, "Is_Meaningful": True},
      "P5": {"Value": 50.0, "Is_Meaningful": False}, "SUBJ": {"Value": 10.0, "Is_Meaningful": True}}


def test_T_PEER_01_median_excludes_excluded_nm_and_subject():
    s = peer_statistic(MEMBERS, PB, exclude_security_id="SUBJ")
    assert s.median == pytest.approx(3.0)
    assert s.n_valid == 3 and s.n_excluded == 3
    assert (s.min, s.max) == (2.0, 4.0)


def test_T_PEER_02_no_valid_peers_is_blank_not_zero():
    s = peer_statistic(MEMBERS[3:5], PB)
    assert s.median is None and s.n_valid == 0


def test_T_PEER_03_missing_value_is_excluded():
    pb = dict(PB, P3={"Value": None, "Is_Meaningful": True})
    s = peer_statistic(MEMBERS, pb, exclude_security_id="SUBJ")
    assert s.median == pytest.approx(2.5) and s.n_valid == 2
