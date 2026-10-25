"""Clean-room contract §6: per-security price and fair-value controls (R007, R008, D-023, D-024).

The inputs are never mutated. Every output is a separate field, so a test can check
that a control moves only the outputs it is supposed to move.
"""
from __future__ import annotations

from dataclasses import dataclass

MODE_ORIGINAL = "Original Market Price"
MODE_SHOCK = "Market Price Shock"
MODE_ABSOLUTE = "Absolute Scenario Market Price"
FV_MODEL = "Model Base Fair Value"
FV_FUNDAMENTAL = "Fundamental Assumption Scenario"
FV_MANUAL = "Manual Fair-Value Bias"


@dataclass(frozen=True)
class Controls:
    original_market_price: float | None
    model_fv_base: float | None
    model_fv_bear: float | None = None
    model_fv_bull: float | None = None
    market_price_mode: str = MODE_ORIGINAL
    market_price_shock_pct: float = 0.0
    absolute_scenario_price: float | None = None
    fair_value_mode: str = FV_MODEL
    fundamental_case: str = "Base"
    fair_value_bias_pct: float = 0.0
    required_margin_of_safety_pct: float = 0.0
    sector_shock_pct: float = 0.0
    global_shock_pct: float = 0.0


@dataclass(frozen=True)
class Resolved:
    effective_shock_pct: float
    market_price_after_shock: float | None
    selected_scenario_market_price: float | None
    fair_value_after_bias: float | None
    fundamental_case_fv: float | None
    selected_scenario_fair_value: float | None
    implied_upside_to_fair_value: float | None
    fair_value_gap: float | None
    target_purchase_price: float | None
    fv_label: str
    control_status: str
    control_warning: str


def _mul(a, b):
    return None if a is None or b is None else a * b


def _ratio_minus_1(a, b):
    return None if a is None or b is None else a / b - 1


def fv_label(mode: str, case: str, bias: float) -> str:
    if mode == FV_MODEL:
        return "Model output (unmodified)"
    if mode == FV_FUNDAMENTAL:
        return f"Model output – fundamental case {case}"
    # QA-READING (F-006): the contract does not fix how <bias>% is formatted.
    return f"MANUALLY BIASED fair value ({bias * 100:g}%)"


def control_warning(c: Controls) -> str:
    parts = []
    shocks_set = any(s != 0 for s in (c.global_shock_pct, c.sector_shock_pct, c.market_price_shock_pct))
    if shocks_set and c.market_price_mode != MODE_SHOCK:
        parts.append(f"Price shocks set but ignored (mode: {c.market_price_mode})")
    if c.absolute_scenario_price is not None and c.market_price_mode != MODE_ABSOLUTE:
        parts.append(f"Absolute price set but ignored (mode: {c.market_price_mode})")
    if c.fair_value_bias_pct != 0 and c.fair_value_mode != FV_MANUAL:
        parts.append(f"Fair-value bias set but ignored (mode: {c.fair_value_mode})")
    return "; ".join(parts)


def resolve(c: Controls) -> Resolved:
    eff = (1 + c.global_shock_pct) * (1 + c.sector_shock_pct) * (1 + c.market_price_shock_pct) - 1
    p0 = c.original_market_price
    after = _mul(p0, 1 + eff)                                   # always from P_0 (D-024 rule 1)
    status = "OK"
    if c.market_price_mode == MODE_ORIGINAL:
        sel_p = p0
    elif c.market_price_mode == MODE_SHOCK:
        sel_p = after
    elif c.market_price_mode == MODE_ABSOLUTE:
        sel_p = c.absolute_scenario_price                        # overrides every shock
        if sel_p is None:
            status = "FAIL: Absolute Scenario Market Price mode with a blank price"   # D-014
    else:
        raise ValueError(f"unknown market price mode {c.market_price_mode!r}")

    case_fv = {"Base": c.model_fv_base, "Bear": c.model_fv_bear, "Bull": c.model_fv_bull}
    fv_bias = _mul(c.model_fv_base, 1 + c.fair_value_bias_pct)
    fund_fv = case_fv[c.fundamental_case]
    sel_fv = {FV_MODEL: c.model_fv_base, FV_FUNDAMENTAL: fund_fv, FV_MANUAL: fv_bias}[c.fair_value_mode]
    if c.model_fv_base is None and status == "OK":
        # QA-READING (F-005): a blank Model_FV_Base means unvalued (§6.3). When the absolute
        # price is also missing, the FAIL above is kept because it is the more severe state.
        status = "UNVALUED"
    if c.model_fv_base is None:          # every fair-value output of an unvalued security is blank
        fv_bias = fund_fv = sel_fv = None
    return Resolved(
        effective_shock_pct=eff,
        market_price_after_shock=after,
        selected_scenario_market_price=sel_p,
        fair_value_after_bias=fv_bias,
        fundamental_case_fv=fund_fv,
        selected_scenario_fair_value=sel_fv,
        implied_upside_to_fair_value=_ratio_minus_1(sel_fv, sel_p),
        fair_value_gap=_ratio_minus_1(fv_bias, p0),
        target_purchase_price=_mul(sel_fv, 1 - c.required_margin_of_safety_pct),   # D-023
        fv_label=fv_label(c.fair_value_mode, c.fundamental_case, c.fair_value_bias_pct),
        control_status=status,
        control_warning=control_warning(c),
    )


def from_worker_inputs(inp) -> Controls:
    """Build Controls from any object with the PriceControlInputs attribute names."""
    return Controls(**{f: (str(v) if f in ("market_price_mode", "fair_value_mode", "fundamental_case") else v)
                       for f, v in vars(inp).items()})
