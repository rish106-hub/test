"""Reference implementation of contract §6 (R007, R008).

The Excel columns of tbl_PriceControls on SCENARIO_ANALYSIS must reproduce
resolve_controls() exactly; tests/contract/test_pricing_contract.py pins the
behaviour and the QA harness compares the two.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.common.enums import Case, FairValueMode, MarketPriceMode


@dataclass(frozen=True)
class PriceControlInputs:
    original_market_price: float | None
    model_fv_base: float | None
    model_fv_bear: float | None = None
    model_fv_bull: float | None = None
    market_price_mode: MarketPriceMode = MarketPriceMode.ORIGINAL
    market_price_shock_pct: float = 0.0
    absolute_scenario_price: float | None = None
    fair_value_mode: FairValueMode = FairValueMode.MODEL_BASE
    fundamental_case: Case = Case.BASE
    fair_value_bias_pct: float = 0.0
    required_margin_of_safety_pct: float = 0.0
    sector_shock_pct: float = 0.0   # tbl_SectorShocks for this security's sector
    global_shock_pct: float = 0.0   # in_Global_Price_Shock_Pct


@dataclass(frozen=True)
class PriceControlOutputs:
    effective_shock_pct: float
    market_price_after_shock: float | None
    selected_scenario_market_price: float | None   # None <=> Excel #N/A, control_status FAIL
    fair_value_after_bias: float | None
    fundamental_case_fv: float | None
    selected_scenario_fair_value: float | None     # None for an unvalued security
    implied_upside_to_fair_value: float | None
    fair_value_gap: float | None
    target_purchase_price_base: float | None
    target_purchase_price_selected: float | None
    fv_label: str
    control_status: str                            # "OK" | "UNVALUED" | "FAIL: <reason>"


def resolve_controls(inp: PriceControlInputs) -> PriceControlOutputs:
    """Resolve one security's controls. Never mutates or replaces the inputs (R008)."""
    raise NotImplementedError("03-nav: implement contract §6")
