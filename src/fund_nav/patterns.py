"""Holdings-table formulas that extend src/common/link_patterns.py (Bear / Bull / Selected variants, WI-7).

CR-03-nav-001 proposes moving these next to the canonical patterns. Until it is accepted they live here
and are built from the same parts (`blank_safe`), so the blank-propagation rule (D-022) still holds.
Columns the canonical patterns already define (H_CURRENT_PRICE, H_BASE_FV, H_MATCH_STATUS,
H_COVERAGE_STATUS, H_ADJ_BASE) are used unchanged.
"""
from __future__ import annotations

from src.common import link_patterns as L
from src.common.units import INR_PER_CRORE

PC = "tbl_PriceControls"
_EQUITY = 'OR([@Asset_Class]="Indian listed equity",[@Asset_Class]="Foreign listed equity")'
_POSITION = '[@Line_Role]="POSITION"'


def selected_price() -> str:
    """Selected_Scenario_Price: the scenario price, never re-derived from a shock (contract 6.1 rule 2).
    A POSITION whose Security_ID has no price-control row stays #N/A (WI-6)."""
    return ('=IF([@Line_Role]<>"POSITION","",'
            f'INDEX({PC}[Selected_Scenario_Market_Price],MATCH([@Security_ID],{PC}[Security_ID],0)))')


def selected_fair_value() -> str:
    return '=IF([@Line_Role]<>"POSITION","",' + L.blank_safe(PC, "Selected_Scenario_Fair_Value") + ")"


def financials_as_of() -> str:
    """Latest_Results_Period_End of the issuer, for MODEL_VALUED lines only; blank stays blank (7.5c)."""
    return ('=IF([@Valuation_Coverage_Status]<>"MODEL_VALUED","",'
            + L.blank_safe("tbl_ValuationOutputs", "Latest_Results_Period_End") + ")")


def adj(case: str) -> str:
    """Adj_<case> = w x (FV_case / P - 1) for a MATCHED equity line with a valid FV for that case, else 0 (7.2).
    Base uses the canonical H_ADJ_BASE."""
    if case == "Base":
        return L.H_ADJ_BASE
    fv = L.blank_safe(PC, "Selected_Scenario_Fair_Value" if case == "Selected" else f"Model_FV_{case}")
    return (f'=IF(AND([@Holdings_Match_Status]="MATCHED",{_EQUITY},{fv}<>""),'
            f"[@Weight_Pct_of_Scheme_NAV]*({fv}/[@Current_Market_Price]-1),0)")


def mv_mkt() -> str:
    """q x P / 1e7 for marked positions; the disclosed value for ONA and MARKET_PASS_THROUGH lines (7.3).
    A position with no quantity or no price is #N/A, never 0 (this differs from L.H_MV_MKT, which gives 0
    for a blank quantity and #VALUE! for a blank price; see CR-03-nav-001)."""
    return (f'=IF(OR([@Line_Role]<>"POSITION",[@Valuation_Coverage_Status]="MARKET_PASS_THROUGH"),'
            "[@Market_Value_INR_Cr],"
            "IF(AND(ISNUMBER([@Quantity_Held]),ISNUMBER([@Current_Market_Price])),"
            f"[@Quantity_Held]*[@Current_Market_Price]/{INR_PER_CRORE},NA()))")


def mv_fair_base() -> str:
    """Fair value of the line at Base: q x FV / 1e7 when MODEL_VALUED, else equal to MV_Mkt (FV := P)."""
    return ('=IF([@Valuation_Coverage_Status]="MODEL_VALUED",'
            f"IF(ISNUMBER([@Quantity_Held]),[@Quantity_Held]*[@Base_Fair_Value]/{INR_PER_CRORE},NA()),"
            "[@MV_Mkt_INR_Cr])")


def mv_scenario() -> str:
    """Line value at the selected scenario price (7.4); pass-through and ONA lines keep their disclosed value."""
    return (f'=IF(OR([@Line_Role]<>"POSITION",[@Valuation_Coverage_Status]="MARKET_PASS_THROUGH"),'
            "[@Market_Value_INR_Cr],"
            "IF(AND(ISNUMBER([@Quantity_Held]),ISNUMBER([@Selected_Scenario_Price])),"
            f"[@Quantity_Held]*[@Selected_Scenario_Price]/{INR_PER_CRORE},NA()))")
