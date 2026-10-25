"""Python reference rows for tbl_ValuationOutputs (D-020).

The builder writes them to build/out/reference_valuation_outputs.csv beside the workbook, so
05-qa can compare the recalculated table with the reference without re-running this module.
"""
from __future__ import annotations

from datetime import date
from typing import Mapping

from src.common.enums import CheckResult as CR, CoverageStatus
from src.valuations import parameters as P
from src.valuations.bank_model import BankModelResult
from src.valuations.inputs import PRIMARY_METHOD, SECONDARY_METHODS, BankSpec

METHODOLOGY_VERSION = "02-valuation bank RI template 1.0 (contract v1.1)"


def missing_critical_inputs(spec: BankSpec) -> int:
    """Count of blank critical inputs, the same cells the sheet's 'Missing critical inputs' counts."""
    g = spec.globals
    n = sum(spec.anchor_obs.get(m) is None for m in ("COMMON_EQUITY", "DILUTED_SHARES", "BANK_NET_ADVANCES",
                                                      "BANK_NON_II", "BANK_OPEX"))
    n += spec.security_inputs.get("IEA_TO_ADV_ANCHOR") is None
    n += (g.get("in_Risk_Free_Rate") is None) + (g.get("in_Equity_Risk_Premium") is None)
    n += spec.security_inputs.get("BETA") is None
    n += spec.price is None
    n += sum(row is None for row in spec.weights.values())
    n += (spec.anchor_date is None) + (spec.valuation_date is None)
    for (case, code, t), row in spec.drivers.items():
        if P.BY_CODE[code].required and row is None:
            n += 1
    for (case, code), row in spec.terminal.items():
        if code in ("TERMINAL_ROE", "TERMINAL_GROWTH", "TERMINAL_PAYOUT") and row is None:
            n += 1
    return int(n)


def _s(x) -> str:
    """Excel's text rendering of a value in a concatenation: blank for None, integers without '.0'."""
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def data_confidence_note(result: BankModelResult, missing: int) -> str:
    flag = result.bridge.forecast_update_flag if result.bridge else ""
    return (f"Freshness: {result.freshness_status}; financials age {_s(result.financials_age_days)}d; anchor age "
            f"{_s(result.anchor_age_days)}d; forecast check: {flag}; terminal: {result.terminal_flag_base}; "
            f"missing critical inputs: {missing}")


def valued_row(spec: BankSpec, result: BankModelResult) -> dict:
    b = result.bridge
    missing = missing_critical_inputs(spec)
    return {
        "Security_ID": spec.security_id, "Valuation_Date": spec.valuation_date, "Anchor_Date": spec.anchor_date,
        "Latest_Results_Period_End": result.latest_results_period_end, "Price_Date": spec.price_date,
        "BV_Reported_At_Anchor_INR": result.bv0,
        "BV_Estimated_At_Valuation_INR": b.bv_estimated_at_valuation if b else None,
        "Interim_EPS_Deviation_Pct": b.interim_eps_deviation_pct if b else None,
        "Forecast_Update_Flag": b.forecast_update_flag if b else None,
        "Financials_Age_Days": result.financials_age_days, "Anchor_Age_Days": result.anchor_age_days,
        "Freshness_Status": result.freshness_status, "Primary_Method": PRIMARY_METHOD,
        "Secondary_Methods": ";".join(SECONDARY_METHODS),
        "FV_Base_INR": result.fair_values["Base"], "FV_Bear_INR": result.fair_values["Bear"],
        "FV_Bull_INR": result.fair_values["Bull"], "Terminal_Value_Share_Base": result.tv_share_base,
        "Terminal_Flag": result.terminal_flag_base, "Peer_Flag": result.peer.flag,
        "Valuation_Coverage_Status": result.coverage_status, "Model_Sheet": spec.sheet,
        "Methodology_Version": METHODOLOGY_VERSION, "Data_Confidence_Note": data_confidence_note(result, missing),
    }


def unvalued_row(registry_row: Mapping[str, str], globals_: Mapping[str, object], reason: str) -> dict:
    return {
        "Security_ID": registry_row["Security_ID"], "Valuation_Date": globals_.get("in_Valuation_Date"),
        "Anchor_Date": None, "Latest_Results_Period_End": None, "Price_Date": globals_.get("in_Price_Date"),
        "BV_Reported_At_Anchor_INR": None, "BV_Estimated_At_Valuation_INR": None, "Interim_EPS_Deviation_Pct": None,
        "Forecast_Update_Flag": None, "Financials_Age_Days": None, "Anchor_Age_Days": None, "Freshness_Status": None,
        "Primary_Method": "None", "Secondary_Methods": "", "FV_Base_INR": None, "FV_Bear_INR": None,
        "FV_Bull_INR": None, "Terminal_Value_Share_Base": None, "Terminal_Flag": None, "Peer_Flag": None,
        "Valuation_Coverage_Status": CoverageStatus.UNVALUED.value, "Model_Sheet": "NONE",
        "Methodology_Version": METHODOLOGY_VERSION, "Data_Confidence_Note": f"UNVALUED: {reason}",
    }


def csv_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return repr(v)
    return str(v)


__all__ = ["CR", "METHODOLOGY_VERSION", "missing_critical_inputs", "data_confidence_note", "valued_row",
           "unvalued_row", "csv_value"]
