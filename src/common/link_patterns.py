"""Canonical cross-table link formulas (spec/workbook_interface.md §3).

Builders import these instead of retyping them. tests/test_common_link_patterns.py
recalculates them in LibreOffice, including the blank-propagation case (WI-7):
INDEX of an empty cell returns 0, which would silently turn an unvalued holding
into a fair value of 0.
"""
from src.common.units import INR_PER_CRORE

def _lookup(table: str, col: str, key: str = "[@Security_ID]", key_col: str = "Security_ID") -> str:
    return f"INDEX({table}[{col}],MATCH({key},{table}[{key_col}],0))"


def blank_safe(table: str, col: str, key: str = "[@Security_ID]", key_col: str = "Security_ID") -> str:
    """Value, or "" when the source cell is blank or the key is absent. Never 0 for blank."""
    look = _lookup(table, col, key, key_col)
    return f'IF(ISNA(MATCH({key},{table}[{key_col}],0)),"",IF({look}="","",{look}))'


# --- tbl_PriceControls (03-nav) <- tbl_ValuationOutputs / tbl_MarketPrices
PC_MODEL_FV = {case: "=" + blank_safe("tbl_ValuationOutputs", f"FV_{case}_INR") for case in ("Base", "Bear", "Bull")}

# --- tbl_Holdings_MF00x (03-nav) <- tbl_PriceControls
H_CURRENT_PRICE = ('=IF([@Line_Role]<>"POSITION","",'
                   + _lookup("tbl_PriceControls", "Original_Market_Price") + ")")   # absent key -> #N/A (WI-6)
H_BASE_FV = '=IF([@Line_Role]<>"POSITION","",' + blank_safe("tbl_PriceControls", "Model_FV_Base") + ")"
H_MATCH_STATUS = ('=IF([@Line_Role]<>"POSITION","",'                       # contract §7.5a
                  'IF(ISNA(MATCH([@Security_ID],tbl_PriceControls[Security_ID],0)),"UNMATCHED",'
                  'IF(' + _lookup("tbl_PriceControls", "Original_Market_Price") + '="","NO_PRICE","MATCHED")))')
H_COVERAGE_STATUS = ('=IF([@Line_Role]<>"POSITION","CARRYING_VALUE",'              # contract §7.0
                     'IF([@Holdings_Match_Status]<>"MATCHED","UNVALUED",'
                     'IF(OR([@Asset_Class]="Indian listed equity",[@Asset_Class]="Foreign listed equity"),'
                     'IF([@Base_Fair_Value]="","UNVALUED","MODEL_VALUED"),"MARKET_PASS_THROUGH")))')
_EQUITY = 'OR([@Asset_Class]="Indian listed equity",[@Asset_Class]="Foreign listed equity")'
_MARKED_AT_DISCLOSED = '[@Line_Role]<>"POSITION",[@Valuation_Coverage_Status]="MARKET_PASS_THROUGH"'
H_ADJ_BASE = ('=IF([@Valuation_Coverage_Status]="MODEL_VALUED",'
              '[@Weight_Pct_of_Scheme_NAV]*([@Base_Fair_Value]/[@Current_Market_Price]-1),0)')


def _adj(fv: str) -> str:
    return (f'=IF(AND([@Holdings_Match_Status]="MATCHED",{_EQUITY},{fv}<>""),'
            f"[@Weight_Pct_of_Scheme_NAV]*({fv}/[@Current_Market_Price]-1),0)")


# Adj_<case> = w x (FV_case / P - 1) for a MATCHED equity line with a fair value for that case, else 0 (§7.2, D-029)
H_ADJ = {"Base": H_ADJ_BASE,
         "Bear": _adj(blank_safe("tbl_PriceControls", "Model_FV_Bear")),
         "Bull": _adj(blank_safe("tbl_PriceControls", "Model_FV_Bull")),
         "Selected": _adj(blank_safe("tbl_PriceControls", "Selected_Scenario_Fair_Value"))}
H_SELECTED_PRICE = ('=IF([@Line_Role]<>"POSITION","",'                        # §6.1 rule 2: never re-shocked
                    + _lookup("tbl_PriceControls", "Selected_Scenario_Market_Price") + ")")
H_SCENARIO_FV = '=IF([@Line_Role]<>"POSITION","",' + blank_safe("tbl_PriceControls", "Selected_Scenario_Fair_Value") + ")"
H_FINANCIALS_AS_OF = ('=IF([@Valuation_Coverage_Status]<>"MODEL_VALUED","",'    # §7.5c
                      + blank_safe("tbl_ValuationOutputs", "Latest_Results_Period_End") + ")")
# Line values (§7.3, §7.4). ONA and MARKET_PASS_THROUGH lines carry their disclosed value. A position with no
# quantity or no price is #N/A, never 0 and never #VALUE! (R009, WI-6; D-029 fixes the v1.1 H_MV_MKT).
H_MV_MKT = (f"=IF(OR({_MARKED_AT_DISCLOSED}),[@Market_Value_INR_Cr],"
            "IF(AND(ISNUMBER([@Quantity_Held]),ISNUMBER([@Current_Market_Price])),"
            f"[@Quantity_Held]*[@Current_Market_Price]/{INR_PER_CRORE},NA()))")
H_MV_FAIR_BASE = ('=IF([@Valuation_Coverage_Status]="MODEL_VALUED",'          # FV := P for other lines
                  f"IF(ISNUMBER([@Quantity_Held]),[@Quantity_Held]*[@Base_Fair_Value]/{INR_PER_CRORE},NA()),"
                  "[@MV_Mkt_INR_Cr])")
H_MV_SCENARIO = (f"=IF(OR({_MARKED_AT_DISCLOSED}),[@Market_Value_INR_Cr],"
                 "IF(AND(ISNUMBER([@Quantity_Held]),ISNUMBER([@Selected_Scenario_Price])),"
                 f"[@Quantity_Held]*[@Selected_Scenario_Price]/{INR_PER_CRORE},NA()))")
