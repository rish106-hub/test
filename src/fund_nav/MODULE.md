# Module 03-nav: MF NAV engine and scenario controls (src/fund_nav and src/scenarios)

Delivery document required by `spec/module_contracts.toml` (D-027).

## Inputs

All read through the workbook interface (`spec/workbook_interface.md` §2), never by cell address on another owner's sheet.

* Global names (contract §0, §6, §7): `in_Price_Date`, `in_Valuation_Date`, `in_Global_Case`, `in_Global_Price_Shock_Pct`, `in_Default_MoS`, `in_Coverage_Warn`, `in_Coverage_Fail`, `in_Recon_Tolerance_Pct`, `in_Holdings_Stale_Days`, `in_Price_Stale_Days`, `in_Financials_Stale_Days`, `in_Risk_Free_Rate`, `in_Default_TC_Pct`, `in_Hypo_Capital_INR`.
* Tables: `tbl_Registry` (Sector, Entity_ID), `tbl_MarketPrices` (Close_INR at `in_Price_Date`, FX_Date, Local_Close_Timestamp), `tbl_ValuationOutputs` (FV_Base/Bear/Bull_INR, Latest_Results_Period_End), `tbl_MissingData` (open items per security/entity).
* Canonical CSVs (built into imported grey tables, never edited): `fund_holdings.csv` (filtered by Fund_ID into the two holdings tables), `fund_plans.csv`, `fund_scheme_totals.csv`, `official_nav.csv`, `benchmark_tri.csv`. Optional user input: `data/scenarios/custom_allocation.csv` (a test build with none uses `tests/fund_nav/fixtures/custom_allocation_synthetic.csv`; a production build starts with 25 empty purple rows).

## Outputs

Interface tables (columns exactly as `src/common/schema.py`): `tbl_PriceControls`, `tbl_SectorShocks` (SCENARIO_ANALYSIS); `tbl_Holdings_MF001` (PPFAS_FLEXICAP_HOLDINGS) and `tbl_Holdings_MF002` (HDFC_MIDCAP_HOLDINGS); `tbl_FundPlans`, `tbl_OfficialNAV`, `tbl_SchemeTotals`, `tbl_NAVSummary` (MF_NAV_CALCULATOR); `tbl_CustomAllocation` (PORTFOLIO_REBALANCING); `tbl_BenchmarkTRI` (FUND_PERFORMANCE). No defined names, no CSVs written.

Private tables (`tbl_Nav_*`): `PriceDefaults` and `ControlsStatus` (the `Reset_*` defaults, `At_Default`, `Controls_At_Default`; SCENARIO_ANALYSIS), `PlanCalc` (per-plan sums over the plan's fund holdings), `Audit_<fund>` and `Audit<List>_<fund>` (MF_COVERAGE_AUDIT), `Sector_<fund>`, `SectorCompare`, `SensSector_<fund>`, `SensTop10_<fund>`, `AllocCheck`, `Hypo`, `HypoSector`, `Overlap`, `Perf`, `Hist_<plan>`.

Sheets: SCENARIO_ANALYSIS, PPFAS_FLEXICAP_HOLDINGS, HDFC_MIDCAP_HOLDINGS, MF_NAV_CALCULATOR, MF_SCENARIO_BUILDER, MF_SECTOR_ANALYSIS, MF_NAV_SENSITIVITY, MF_COVERAGE_AUDIT, PORTFOLIO_REBALANCING, FUND_PERFORMANCE. Units: INR crore for aggregates, INR for per-unit and per-share values, decimals for percentages.

Headline: Method 1 Base/Bear/Bull/Selected (D-019), Method 2 ratio form (D-004), Method 3 Scenario Market NAV, reconciliation, the three data-quality measures kept in separate columns (holdings coverage, valuation coverage with its generated caption, freshness), and D1-D4. Each value in the MF_NAV_CALCULATOR statement block sits next to its `OutputLabel`. Chart zones are reserved for the sector, concentration, NAV, coverage and hypothetical-allocation charts (`NAV_COMPARE`, `NAV_COVERAGE_FRESHNESS`, `MF001_SECTOR_ALLOC`, `MF002_SECTOR_ALLOC`, `MF_SECTOR_COMPARE`, `MF001_TOP10`, `MF002_TOP10`, `SCENARIO_NAV_GRID`, `SCENARIO_NAV_COMPARE`, `AUDIT_COVERAGE_BY_SECTOR`, `HYPO_SECTOR_WEIGHTS`, `PERF_NAV_HISTORY`).

## Assumptions

* `Fundamental_Case` and `Required_Margin_of_Safety_Pct` default to formulas (`=in_Global_Case`, `=in_Default_MoS`) per contract §6; overtyping one makes it a per-security override. The cell font stays green. The same two formulas are the Reset values.
* `Control_Warning` tests the net `Effective_Shock_Pct` (rounded to 10 places) rather than the three raw shocks, so that the shocks are read in exactly one column (§6.1 rule 2). See CR-03-nav-002.
* MARKET_PASS_THROUGH positions are carried at their disclosed value (they are part of ONA in §7.3), so a price shock does not move them in Method 3.
* `Holdings_Coverage_Status` is PASS only when the reconciliation passes and no POSITION line is unmatched (a zero-weight unmatched line therefore also fails, which is stricter than `Holdings_Match_Pct = 1`).
* An empty holdings table gives `#N/A` Fair NAVs and status `MISSING`; an unmatched or unpriced position gives `#N/A` in Methods 2 and 3 (WI-6) and `UNVALUED` with adjustment 0 in Method 1.
* Performance windows are 365 x k days (k = 1, 3, 5, 10) back from the NAV date used; the base observation is the last NAV on or before the window start; the benchmark is the plan's stated benchmark and only rows with `Is_TRI = TRUE` are used; MAR defaults to `in_Risk_Free_Rate` (overtype to change); Sharpe/Sortino/downside stay blank while it is blank. A benchmark series that stops before the NAV date gives no benchmark return.
* The sensitivity step (10%) and the uniform market-move grid points are blue inputs; the `Reset_Global_Price_Shock_Pct` is the constant 0.
* Hypothetical portfolio (Method 4) needs `in_Hypo_Capital_INR` and `in_Default_TC_Pct`; while either is blank its outputs are blank and the status is `MISSING INPUT` (no default is invented).
* `tbl_Holdings_*` formulas use `src/fund_nav/patterns.py` variants of the canonical link patterns until CR-03-nav-001 is accepted.

## Limitations

* No real data: all numbers so far come from synthetic fixtures (`SYNTHETIC TEST FIXTURE`). The production build needs 01-data (holdings, NAVs, scheme totals, prices, benchmark TRI) and 02-valuation (`tbl_ValuationOutputs`); an isolated production build cannot resolve those tables and was NOT RUN.
* Two holdings sheets only (MF001, MF002); a third fund needs a new entry in `xl.FUND_SHEETS` and a sheet in `ownership.toml`.
* Overlap and the sector comparison cover the first two funds. "Allow optional user-entered direct holdings and other funds" (spec overlap) is not built.
* The audit lists, the top-10 table and the 25-row allocation are sized at build time; a list always has one row per holdings line, so nothing is truncated, but new lines need a rebuild.
* `FUND_PERFORMANCE` helper tables (`tbl_Nav_Hist_<plan>`) use O(n^2) MAXIFS over the NAV history; recalculation of ten years of daily NAV for three plans has not been timed. Expense ratio, turnover, fund size and manager tenure (spec required metrics) are not in the data schema and are not shown.
* Method 2 units-based form (`units_based_nav`) exists as a reference function only; the schema has no plan-level units column.
* Foreign-line D4 shows the FX date gap and the stated local close timestamp (or "not stated"); there is no time-of-day comparison.
* The empty-data state shows `#N/A` in audit-index helper rows until holdings exist.
* Charts: only zones are reserved here (04-charts draws).

## Tests

Run 2026-10-25 in the 03-nav worktree.

* Contract tests (`tests/contract/test_pricing_contract.py`, `test_nav_contract.py`, `test_allocation_contract.py`, `test_performance_contract.py`) under `--strict-impl`: 44 passed, 0 failed, 0 skipped.
* `tests/scenarios/test_pricing_extra.py`: missing price, warning order and text, bias text, absolute price ignored in Original mode.
* `tests/fund_nav/test_sheet_matches_reference.py` (LibreOffice recalculation of the isolated build; marker `workbook`): every `tbl_NAVSummary` and `tbl_PriceControls` value equals `reference_run.py` (reference functions) for default controls, for absolute/shock controls (T-NAV-07 = 73.44), for bias plus global and sector shocks applied once, and for an unmatched position (`#N/A`, Method 1 unchanged).
* `tests/fund_nav/test_other_sheets.py` (same harness): Method 4 equals `build_hypothetical_portfolio` and overspend gives FAIL; an invalid allocation is reported; unvalued lines are listed on MF_COVERAGE_AUDIT and coverage equals the reference when a fair value is removed; sector contributions sum to the total; overlap = 0.2 / 1 security (T-OVL-01); the uniform grid equals Method 3 when every security carries the same shock; performance windows equal `performance.window_metrics` and short history is blank.
* Isolated build: `python build/generate_workbook.py --test-build --only 03-nav`, recalculated by `build/recalc.py`; no `#REF!`, `#NAME?`, `#DIV/0!` or `#VALUE!` in any 03-nav sheet.
* `python -m pytest` (whole repo, includes the `workbook` tests): 90 passed, 31 skipped (other owners' contract tests), 2 failed. Both failures are outside 03-nav and expected until integration: `test_test_build_and_isolated_builds_succeed` (a full test build cannot resolve `tbl_Registry`, `tbl_MarketPrices`, `tbl_ValuationOutputs`, `tbl_MissingData` until 01-data and 02-valuation are merged) and `test_module_doc_templates_are_rejected_until_filled` (it asserts that an unfilled MODULE.md template is rejected, so it fails once a module doc is filled in).
* NOT RUN: production build (depends on 01-data and 02-valuation); timing of a ten-year NAV history.
