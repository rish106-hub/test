"""Canonical cross-table link formulas (spec/workbook_interface.md §3).

Builders import these instead of retyping them. tests/test_common_link_patterns.py
recalculates them in LibreOffice, including the blank-propagation case (WI-7):
INDEX of an empty cell returns 0, which would silently turn an unvalued holding
into a fair value of 0.
"""

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
H_COVERAGE_STATUS = ('=IF([@Line_Role]<>"POSITION","CARRYING_VALUE",'
                     'IF(OR([@Asset_Class]="Indian listed equity",[@Asset_Class]="Foreign listed equity"),'
                     'IF([@Base_Fair_Value]="","UNVALUED","MODEL_VALUED"),"MARKET_PASS_THROUGH"))')
H_ADJ_BASE = ('=IF([@Valuation_Coverage_Status]="MODEL_VALUED",'
              '[@Weight_Pct_of_Scheme_NAV]*([@Base_Fair_Value]/[@Current_Market_Price]-1),0)')
H_MV_MKT = '=IF([@Line_Role]="POSITION",[@Quantity_Held]*[@Current_Market_Price]/10000000,[@Market_Value_INR_Cr])'
