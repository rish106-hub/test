# 05-qa findings

Each finding gives its severity (blocker/major/minor), owner, reproduction, expected vs actual, and contract section.
00-main routes them. None is a blocker yet, because the affected modules are not merged.

| ID | Severity | Owner | Title |
|---|---|---|---|
| [F-001](F-001.md) | major | 00-main (contract); affects 03-nav | Method 2/3: basis for MARKET_PASS_THROUGH positions and behaviour for unmarkable lines |
| [F-002](F-002.md) | major | 00-main (contract and link_patterns); affects 03-nav | Coverage status: which source, and is it per case? |
| [F-003](F-003.md) | minor | 00-main | 'Shock inputs read in exactly one place' conflicts with Control_Warning and Controls_At_Default |
| [F-004](F-004.md) | major | 00-main (schema, module contract, 03-nav brief) | Reset_* columns and Controls_At_Default have no legal home; W-11 cannot pass as specified |
| [F-005](F-005.md) | minor | 00-main | Control_Status vocabulary and precedence are not fully defined |
| [F-006](F-006.md) | minor | 00-main | FV_Label strings are not exactly specified |
| [F-007](F-007.md) | minor | 00-main | Equity bridge: undefined cases |
| [F-008](F-008.md) | minor | 00-main | Blend weight sum tolerance is unspecified |
| [F-009](F-009.md) | minor | 00-main | Coverage caption rounding and coverage/freshness edge cases |
| [F-010](F-010.md) | minor | 00-main | Threshold descriptions contradict the contract's reference dates |
| [F-011](F-011.md) | major | 00-main (build/main_sheets.py::build_dashboard) | EXECUTIVE_DASHBOARD lacks unvalued count/weight and the NAV-date warning required by W-12 |
| [F-012](F-012.md) | major | 00-main (contract/module contracts); affects 02-valuation | QA cannot recompute the bank valuation from the workbook or the data: no reference-input interface |
| [F-013](F-013.md) | minor | 00-main | Valuation_Coverage_Total_Pct can be negative and unvalued weight above 100% |
| [F-014](F-014.md) | minor | 00-main (build/main_sheets.py::_validation_checks) | Test-build watermark missing on VALIDATION_CHECKS |
