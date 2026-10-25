"""Seeded random generators for property and differential tests (no hypothesis dependency).

Every generator is deterministic for a given seed, so a failure is reproducible from the
seed printed in the assertion message.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from src.common.enums import AssetClass as A, LineRole as R, Sector as S
from src.fund_nav.model import HoldingLine

SECTORS = [S.FINANCIAL_SERVICES, S.IT, S.INDUSTRIALS, S.HEALTHCARE, S.ENERGY]
N_DRAWS = 400


def steady_state(rng: random.Random):
    """(bv0, eps, dps, r, roe, payout, g) with g = ROE × (1 − payout) < r."""
    while True:
        r = rng.uniform(0.08, 0.18)
        roe = rng.uniform(0.04, 0.25)
        payout = rng.uniform(0.05, 0.95)
        g = roe * (1 - payout)
        if g < r - 0.005:
            break
    n = rng.randint(1, 10)
    bv0 = rng.uniform(10, 1500)
    bv, eps, dps = bv0, [], []
    for _ in range(n):
        e = roe * bv
        eps.append(e); dps.append(e * payout); bv += e - e * payout
    return bv0, eps, dps, r, roe, payout, g


def ri_inputs(rng: random.Random):
    n = rng.randint(1, 10)
    bv0 = rng.uniform(10, 1500)
    eps = [bv0 * rng.uniform(-0.05, 0.3) for _ in range(n)]
    dps = [max(0.0, e * rng.uniform(0, 0.8)) for e in eps]
    r = rng.uniform(0.08, 0.18)
    g = rng.uniform(-0.02, r - 0.005)
    return bv0, eps, dps, r, rng.uniform(0.0, 0.3), rng.uniform(0.05, 0.95), g


def fund(rng: random.Random, *, consistent_weights: bool = False, unvalued_share: float = 0.25,
         allow_unmatched: bool = False, allow_mpt: bool = False):
    """(lines, official_nav, reported_net_assets_inr_cr) for a random scheme.

    consistent_weights: weights = q × P / NA_mkt exactly (Method 1 then equals Method 2).
    """
    n_pos = rng.randint(1, 12)
    lines, mv = [], []
    for i in range(n_pos):
        price = rng.uniform(5, 5000)
        q = float(rng.randint(1_000, 5_000_000))
        foreign = rng.random() < 0.15
        unvalued = rng.random() < unvalued_share
        mpt = allow_mpt and rng.random() < 0.2
        fv = None if unvalued else price * rng.uniform(0.4, 1.8)
        fvs = None if fv is None else {"Base": fv, "Bear": fv * rng.uniform(0.6, 1.0), "Bull": fv * rng.uniform(1.0, 1.5)}
        asset = A.DEBT if mpt else (A.FOREIGN_EQUITY if foreign else A.INDIAN_EQUITY)
        sid = f"S9{i:04d}"
        if allow_unmatched and rng.random() < 0.15:
            sid = None
        p = price
        if allow_unmatched and sid and rng.random() < 0.1:
            p = None
        mv_i = q * price / 1e7
        mv.append(mv_i)
        lines.append(HoldingLine(line_id=f"L{i + 1}", line_role=R.POSITION, asset_class=asset,
                                 sector=rng.choice(SECTORS), weight=0.0, market_value_inr_cr=mv_i,
                                 security_id=sid, quantity=q, price_inr=p,
                                 fv_inr=(fvs or {"Base": None, "Bear": None, "Bull": None}),
                                 scenario_price_inr=p, selected_fv_inr=(None if fvs is None else fvs["Base"]),
                                 financials_as_of=date(2026, 9, 30) - timedelta(days=rng.randint(0, 400))
                                 if rng.random() > 0.1 else None))
    cash = rng.uniform(0, 0.3) * sum(mv) + 1.0
    pay = -rng.uniform(0, 0.02) * sum(mv)
    lines.append(HoldingLine(line_id=f"L{n_pos + 1}", line_role=R.ONA_ASSET, asset_class=A.CASH,
                             sector=S.NOT_APPLICABLE, weight=0.0, market_value_inr_cr=cash))
    lines.append(HoldingLine(line_id=f"L{n_pos + 2}", line_role=R.ONA_LIABILITY, asset_class=A.OTHER,
                             sector=S.NOT_APPLICABLE, weight=0.0, market_value_inr_cr=pay))
    na = sum(l.market_value_inr_cr for l in lines)
    out = []
    for l in lines:
        w = l.market_value_inr_cr / na
        if not consistent_weights and l.line_role == R.POSITION:
            w *= rng.uniform(0.9, 1.1)      # disclosed weights drift from q × P / NA (diagnostic D2)
        out.append(_replace(l, weight=w))
    return out, rng.uniform(10, 500), na * rng.choice([1.0, 1.0, 1.0, rng.uniform(0.98, 1.02)])


def _replace(line, **kw):
    import dataclasses
    return dataclasses.replace(line, **kw)
