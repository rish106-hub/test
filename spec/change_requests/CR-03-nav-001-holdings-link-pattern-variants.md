# CR-03-nav-001: Bear/Bull/Selected holdings link patterns, and an NA-safe MV_Mkt

Requested by: 03-nav            Date: 2026-10-25
Contract section: workbook_interface §3 (reference link patterns), contract §7.2-7.4

Problem:
1. `link_patterns.py` defines only the Base variants (`H_ADJ_BASE`) and says 03-nav adds Bear, Bull and Selected through a CR. They are needed for `Adj_Bear`, `Adj_Bull`, `Adj_Selected`, `Selected_Scenario_Price`, `Scenario_Fair_Value`, `Financials_As_Of`, `MV_Fair_Base_INR_Cr` and `MV_Scenario_INR_Cr`.
2. `H_MV_MKT` has two gaps that break R009/WI-6:
   * a POSITION with a blank `Quantity_Held` gives `0 x price = 0` (a silent zero value);
   * a `NO_PRICE` position (`Current_Market_Price = ""`) gives `#VALUE!`, which W-02 forbids; the contract says Methods 2 and 3 show `#N/A` for a line that is not MATCHED.
   It also marks MARKET_PASS_THROUGH positions at `q x P`, whereas contract §7.3 puts them in ONA at their disclosed value.

Proposal: adopt the formulas that 03-nav already uses in `src/fund_nav/patterns.py` (built from `blank_safe`, so WI-7/D-022 still hold), tested by `tests/fund_nav/`:
* `H_ADJ_<Case>` = `=IF(AND([@Holdings_Match_Status]="MATCHED",<equity>,<blank_safe FV_case><>""),[@Weight_Pct_of_Scheme_NAV]*(<FV_case>/[@Current_Market_Price]-1),0)`, with `Selected_Scenario_Fair_Value` for Selected.
* `H_MV_MKT` = `=IF(OR([@Line_Role]<>"POSITION",[@Valuation_Coverage_Status]="MARKET_PASS_THROUGH"),[@Market_Value_INR_Cr],IF(AND(ISNUMBER([@Quantity_Held]),ISNUMBER([@Current_Market_Price])),[@Quantity_Held]*[@Current_Market_Price]/10000000,NA()))`.
* `H_MV_FAIR_BASE`, `H_MV_SCENARIO`, `H_SELECTED_PRICE`, `H_SCENARIO_FV`, `H_FINANCIALS_AS_OF` as in `patterns.py`.

Impact on other workers: none required. 00-main may move the strings into `link_patterns.py` and extend `tests/test_common_link_patterns.py`; 03-nav then imports them instead of `patterns.py`. 05-qa's W-15 scan sees the same `blank_safe` shape either way.

Tests: `tests/fund_nav/test_sheet_matches_reference.py::test_unmatched_position_is_na_not_zero_and_fails_holdings_coverage` (UNMATCHED line gives `#N/A` in Methods 2 and 3, Method 1 unchanged) and the default-controls parity test (T-NAV-02..07 hand values).
