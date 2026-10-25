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
    target_purchase_price: float | None            # Selected_Scenario_Fair_Value x (1 - MoS); the only TPP (D-023)
    fv_label: str
    control_status: str                            # "OK" | "UNVALUED" | "FAIL: <reason>"
    control_warning: str = ""                      # §6.2: inputs set but ignored by the selected mode; "" if none


def bias_text(bias_pct: float) -> str:
    """Excel: ROUND(bias*100,2) concatenated into text ("-10", "5.5")."""
    return f"{round(bias_pct * 100, 2):g}"


def fv_label(mode: FairValueMode, case: Case, bias_pct: float) -> str:
    if mode == FairValueMode.MODEL_BASE:
        return "Model output (unmodified)"
    if mode == FairValueMode.FUNDAMENTAL:
        return f"Model output \u2013 fundamental case {Case(case).value}"
    return f"MANUALLY BIASED fair value ({bias_text(bias_pct)}%)"


def control_warning(global_shock_pct: float, sector_shock_pct: float, security_shock_pct: float,
                    market_mode: MarketPriceMode, absolute_price: float | None,
                    fv_mode: FairValueMode, bias_pct: float) -> str:
    """Contract section 6.2 (D-029): inputs that are set but have no effect under the selected modes.

    Each of the three shock inputs is tested, so shocks that cancel to a net zero are still disclosed.
    """
    parts = []
    if (global_shock_pct != 0 or sector_shock_pct != 0 or security_shock_pct != 0) and market_mode != MarketPriceMode.SHOCK:
        parts.append(f"Price shocks set but ignored (mode: {market_mode.value})")
    if absolute_price is not None and market_mode != MarketPriceMode.ABSOLUTE:
        parts.append(f"Absolute price set but ignored (mode: {market_mode.value})")
    if bias_pct != 0 and fv_mode != FairValueMode.MANUAL_BIAS:
        parts.append(f"Fair-value bias set but ignored (mode: {fv_mode.value})")
    return "; ".join(parts)


def resolve_controls(inp: PriceControlInputs) -> PriceControlOutputs:
    """Resolve one security's controls. Never mutates or replaces the inputs (R008)."""
    mode, fv_mode = MarketPriceMode(inp.market_price_mode), FairValueMode(inp.fair_value_mode)
    case = Case(inp.fundamental_case)
    p0, fv_base = inp.original_market_price, inp.model_fv_base

    # Section 6.1: shocks compound once, from the original price.
    effective = (1 + inp.global_shock_pct) * (1 + inp.sector_shock_pct) * (1 + inp.market_price_shock_pct) - 1
    after_shock = None if p0 is None else p0 * (1 + effective)

    if mode == MarketPriceMode.ORIGINAL:
        sel_price = p0
    elif mode == MarketPriceMode.SHOCK:
        sel_price = after_shock
    else:                                          # Absolute: blank is a visible failure, no fallback (D-014)
        sel_price = inp.absolute_scenario_price

    fv_after_bias = None if fv_base is None else fv_base * (1 + inp.fair_value_bias_pct)
    case_fv = {Case.BASE: fv_base, Case.BEAR: inp.model_fv_bear, Case.BULL: inp.model_fv_bull}[case]
    if fv_mode == FairValueMode.MODEL_BASE:
        sel_fv = fv_base
    elif fv_mode == FairValueMode.FUNDAMENTAL:
        sel_fv = case_fv
    else:
        sel_fv = fv_after_bias

    upside = None if sel_fv is None or sel_price is None else sel_fv / sel_price - 1
    gap = None if fv_after_bias is None or p0 is None else fv_after_bias / p0 - 1
    tpp = None if sel_fv is None else sel_fv * (1 - inp.required_margin_of_safety_pct)

    if sel_price is None:
        status = ("FAIL: absolute scenario price missing" if mode == MarketPriceMode.ABSOLUTE
                  else "FAIL: no market price at the price date")
    elif sel_fv is None:
        status = "UNVALUED"
    else:
        status = "OK"

    return PriceControlOutputs(
        effective_shock_pct=effective, market_price_after_shock=after_shock,
        selected_scenario_market_price=sel_price, fair_value_after_bias=fv_after_bias,
        fundamental_case_fv=case_fv, selected_scenario_fair_value=sel_fv,
        implied_upside_to_fair_value=upside, fair_value_gap=gap, target_purchase_price=tpp,
        fv_label=fv_label(fv_mode, case, inp.fair_value_bias_pct), control_status=status,
        control_warning=control_warning(inp.global_shock_pct, inp.sector_shock_pct, inp.market_price_shock_pct, mode,
                                        inp.absolute_scenario_price, fv_mode, inp.fair_value_bias_pct))
