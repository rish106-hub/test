# Brief 03-nav: Mutual-fund NAV engine and scenario controls

**Launch:** `claude --worktree 03-nav --model sonnet --effort high "Read CLAUDE.md and spec/worker_briefs/03-nav.md, then execute the brief."`

## Mission

Build the per-security price and fair-value controls (contract §6) and the fund engine (contract §7): holdings tables, the four NAV methods, coverage, reconciliation, diagnostics, sector analysis, sensitivity, the hypothetical portfolio and fund performance. Official NAV, Fair NAV, Scenario Market NAV and Hypothetical Portfolio Value must never be confused (R006, R011).

## You own

`src/scenarios/**`, `src/fund_nav/**`, `tests/fund_nav/**`, `tests/scenarios/**`, `data/scenarios/**`, `reports/nav/**`, and the sheets SCENARIO_ANALYSIS, PPFAS_FLEXICAP_HOLDINGS, HDFC_MIDCAP_HOLDINGS, MF_NAV_CALCULATOR, MF_SCENARIO_BUILDER, MF_SECTOR_ANALYSIS, MF_NAV_SENSITIVITY, MF_COVERAGE_AUDIT, PORTFOLIO_REBALANCING and FUND_PERFORMANCE.

## Read first

`spec/financial_model_contract.md` §0, §1, §6, §7 → `spec/workbook_interface.md` (especially WI-6, WI-7 and the link patterns) → `tests/contract/test_pricing_contract.py`, `test_nav_contract.py`, `test_allocation_contract.py`, `test_performance_contract.py`, `tests/contract/cases.py` → `src/scenarios/pricing.py`, `src/fund_nav/*.py`.

## Work

**Wave 1 scope (D-028):** all of the engine on fixtures, and on real data the fund that holds HDFC Bank, with both funds' snapshots imported and their data-quality measures shown, until gate G1 passes (`spec/worker_briefs/00-main.md`).

1. **Reference functions.** Implement the stubs. These must pass: `python -m pytest tests/contract/test_pricing_contract.py tests/contract/test_nav_contract.py tests/contract/test_allocation_contract.py tests/contract/test_performance_contract.py --strict-impl`.
2. **SCENARIO_ANALYSIS.** Build `tbl_SectorShocks` with one row per `Sector`, default 0, in blue. Build `tbl_PriceControls` with one row per registry security and the columns of `schema.PRICE_CONTROLS`, in this order:
   * links (green), using `link_patterns.PC_MODEL_FV` and a price link;
   * inputs with data validation (dropdowns of the exact `MarketPriceMode` / `FairValueMode` / `Case` strings; decimal bounds), blue or purple;
   * outputs (black), exactly as in §6, including the single `Target_Purchase_Price` (D-023) and `Control_Warning` (§6.2). Shock inputs are read only in `Effective_Shock_Pct` (§6.1, W-17);
   * `Reset_*` columns holding the defaults, plus a `Controls_At_Default` check.
   If you need Bear/Bull/Selected variants of the link patterns, file a change request.
3. **Holdings sheets.** `tbl_Holdings_MF001` and `tbl_Holdings_MF002` come from `fund_holdings.csv`, filtered by Fund_ID. The CSV columns are imported (grey); the link and calc columns of `schema.FUND_HOLDINGS` use `link_patterns.H_*` and their Bear/Bull/Selected equivalents. The two funds' holdings are built by the same function and never share rows.
4. **MF_NAV_CALCULATOR.** Build `tbl_FundPlans`, `tbl_OfficialNAV`, `tbl_SchemeTotals` and `tbl_NAVSummary` (one row per plan, the columns of `schema.NAV_SUMMARY`). It holds: Method 1 Base/Bear/Bull/Selected (headline, D-019), Method 2 (ratio form, D-004), Method 3, reconciliation (§7.3), the **three separate data-quality measures** (§7.5a holdings coverage using `link_patterns.H_MATCH_STATUS`, §7.5b valuation coverage with its generated caption, §7.5c freshness), and D1–D4 (§7.7). Every value sits next to its `OutputLabel` caption (WI-9).
5. **MF_SCENARIO_BUILDER**: Scenario NAV under the current controls, plus a uniform market-move table (−30% … +30%) computed by formula without touching the inputs, labelled as such. **MF_NAV_SENSITIVITY**: ΔNAV for a ±10% FV change by sector and for the top-10 holdings. **MF_SECTOR_ANALYSIS**: sector weights per fund, contribution to the fair-NAV difference (it must sum to the total), coverage by sector, and a comparison of the two funds. **MF_COVERAGE_AUDIT**: every UNVALUED line with weight and value, every line that is not `MATCHED` (§7.5a) with its reason, every valued line on stale financials (§7.5c), plus the holdings-date, price-date and FX-timestamp warnings. All of these must update when any control changes (spec manual test 8).
6. **PORTFOLIO_REBALANCING**: `tbl_CustomAllocation` (purple inputs, validated per §7.6) and Method 4 outputs, captioned `OutputLabel.HYPOTHETICAL_PORTFOLIO`. No actual-holdings formula may reference this sheet.
7. **FUND_PERFORMANCE**: §7.9 metrics from `tbl_OfficialNAV` history and `tbl_BenchmarkTRI`. Use the stated benchmark (TRI); show n and the window for each metric; leave a cell blank rather than computing it from too short a history. Overlap (§7.8) between the funds goes here too. Label any return derived from current holdings as a static-portfolio scenario.
8. **Chart zones**: reserve zones for the spec's sector, concentration and NAV charts on your sheets, naming the chart in `purpose`.
9. **Self-check**: `tests/fund_nav/test_sheet_matches_reference.py` builds `--test-build --only 03-nav` (interfaces stubbed from the same fixtures as `cases.py`), recalculates, and asserts that the workbook's NAVs equal T-NAV-02…07 and the Python reference.

## Rules

* R008: never write a formula into an original price, a model fair value or an imported column.
* R009 / WI-7: an unvalued holding is visible everywhere and is never 0. A POSITION with no price-control row shows `#N/A`.
* Do not use `IFERROR(…,0)` in a calculation path.

## Done when

- [ ] `python tools/check_module_contract.py 03-nav --manifest build/out/manifest.json --run-tests` prints no REJECT, and `src/fund_nav/MODULE.md` is filled in
- [ ] The contract tests above pass under `--strict-impl`
- [ ] The isolated test build recalculates to T-NAV values; the default-controls identity holds (W-11)
- [ ] The production build (after 01 and 02 land) gives a Fair NAV with the coverage caption for both Direct Growth plans
- [ ] Ownership check clean
