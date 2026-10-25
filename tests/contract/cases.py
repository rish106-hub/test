"""Shared synthetic cases for the contract tests (spec/test_plan.md).

Every number here is SYNTHETIC and hand-computed. It mirrors the CSV fixtures in
tests/fixtures/synthetic/, and test_common_fixtures.py checks that the two agree.
"""
from src.common.enums import AssetClass as A, LineRole as R, Sector as S
from src.fund_nav.model import HoldingLine

PRICE_DATE = "2026-10-23"
PORTFOLIO_DATE = "2026-09-30"

# Security fair values (INR per share). S90003 has no model; S90004 is USD-listed (FX 85).
FV = {
    "S90001": {"Base": 500.0, "Bear": 400.0, "Bull": 600.0},
    "S90002": {"Base": 120.0, "Bear": 90.0, "Bull": 150.0},
    "S90003": {"Base": None, "Bear": None, "Bull": None},
    "S90004": {"Base": 440.0 * 85, "Bear": 380.0 * 85, "Bull": 500.0 * 85},
}
PRICE = {"S90001": 750.0, "S90002": 100.0, "S90003": 100.0, "S90004": 400.0 * 85, "S90005": 250.0}


def _pos(line_id, sid, sector, q, w, asset=A.INDIAN_EQUITY):
    return HoldingLine(line_id=line_id, line_role=R.POSITION, asset_class=asset, sector=sector, weight=w,
                       market_value_inr_cr=q * PRICE[sid] / 1e7, security_id=sid, quantity=q,
                       price_inr=PRICE[sid], fv_inr=dict(FV[sid]), scenario_price_inr=PRICE[sid],
                       selected_fv_inr=FV[sid]["Base"])


def _ona(line_id, role, asset, value, w):
    return HoldingLine(line_id=line_id, line_role=role, asset_class=asset, sector=S.NOT_APPLICABLE,
                       weight=w, market_value_inr_cr=value)


# MF001: net assets 1,000 Cr. Official NAV Direct Growth 80.00, Regular Growth 72.00.
MF001 = [
    _pos("MF001-L1", "S90001", S.FINANCIAL_SERVICES, 4_000_000, 0.30),     # 300 Cr
    _pos("MF001-L2", "S90002", S.FINANCIAL_SERVICES, 20_000_000, 0.20),    # 200 Cr
    _pos("MF001-L3", "S90003", S.INDUSTRIALS, 10_000_000, 0.10),           # 100 Cr, UNVALUED
    _ona("MF001-L4", R.ONA_ASSET, A.CASH, 410.0, 0.41),
    _ona("MF001-L5", R.ONA_LIABILITY, A.OTHER, -10.0, -0.01),
]
MF001_REPORTED_NA = 1000.0
MF001_NAV = {"MF001-DIR-GR": 80.0, "MF001-REG-GR": 72.0}

# MF002: net assets 500 Cr. Official NAV Direct Growth 150.00. Holds S90002 and USD-listed S90004.
MF002 = [
    _pos("MF002-L1", "S90002", S.FINANCIAL_SERVICES, 10_000_000, 0.20),    # 100 Cr
    _pos("MF002-L2", "S90004", S.IT, 100_000, 0.68, A.FOREIGN_EQUITY),     # 340 Cr
    _ona("MF002-L3", R.ONA_ASSET, A.CASH, 60.0, 0.12),
]
MF002_REPORTED_NA = 500.0
MF002_NAV = {"MF002-DIR-GR": 150.0}
