# Workbook Interface

How modules meet inside the one generated `.xlsx`. The definitions behind the formulas are in `financial_model_contract.md`. Table columns are in `data_schema.md`. Sheet ownership is in `ownership.toml`.

## 1. Build model

* The workbook is **generated** by `build/generate_workbook.py`. Nobody edits an `.xlsx` by hand, and the output is never committed (D-001).
* Each worker exposes one entry point: `build_sheets(ctx: WorkbookContext, data: ModelData) -> None`. 04-charts also exposes `render_charts`, which runs last.
* `ctx` (`src/common/workbook.py`) is the only way to touch the workbook. It refuses:
  * writing to a sheet the caller does not own;
  * any function outside the whitelist (`src/common/excel_contract.py`);
  * at `close()`, any reference to a `tbl_*` table or `in_*`/`out_*` name that no module defined.
* `--test-build --only <worker>` builds one worker for real and **stubs** every interface table it consumes from synthetic fixtures (`build/interface_stubs.py`). Workers develop and recalculate in isolation with it.

## 2. Interface tables and names

These are the **only** things a module may reference in another module's sheets. Anything else, such as a raw cell address on another owner's sheet, is a contract violation, and QA scans for it (W-05).

| Interface | Built by | Sheet | Consumed by | Key |
|---|---|---|---|---|
| `in_*` (18 global inputs) | 00-main | GLOBAL_ASSUMPTIONS | all | — |
| `tbl_Registry` | 01-data | MASTER_SECURITY_REGISTRY | 02, 03, 04 | Security_ID |
| `tbl_MarketPrices` | 01-data | MARKET_PRICES | 02, 03, 04 | Security_ID + Price_Date |
| `tbl_RawFinancials` | 01-data | RAW_FINANCIAL_DATA | 02, 04 | Observation_ID |
| `tbl_ValuationOutputs` | 02-valuation | VALUATION_OUTPUTS | 03, 04 | Security_ID |
| `out_<SID>_FV_Base`, `_FV_Bear`, `_FV_Bull`, `_TV_Share` | 02-valuation | VAL_* | VALUATION_OUTPUTS only | — |
| `tbl_HistoricalMetrics` | 02-valuation | HISTORICAL_METRICS | 04 | Entity_ID + Metric_ID + Fiscal_Label |
| `tbl_PeerSummary` | 04-charts | PEER_GROUPS | 02 | Peer_Group_ID + Metric_ID + Exclude_Security_ID |
| `tbl_PriceControls`, `tbl_SectorShocks` | 03-nav | SCENARIO_ANALYSIS | 03, 04 | Security_ID / Sector |
| `tbl_Holdings_MF001`, `tbl_Holdings_MF002` | 03-nav | *_HOLDINGS | 04 | Holding_Line_ID |
| `tbl_NAVSummary` | 03-nav | MF_NAV_CALCULATOR | 00-main dashboard, 04 | Plan_ID |
| `tbl_FundPlans`, `tbl_OfficialNAV`, `tbl_SchemeTotals` | 03-nav (data from 01) | MF_NAV_CALCULATOR | 04 | see schema |
| chart zones | each sheet owner | any | 04-charts | zone_id |

`tbl_ValuationOutputs` is the single seam between valuation and NAV. Each row links (green) to a VAL_* sheet's `out_*` names, or to a template engine's row. Funds never look at VAL_* sheets directly (spec `<scalability>`).

## 3. Formula rules

| ID | Rule |
|---|---|
| WI-1 | Lookups use `INDEX(tbl_X[col], MATCH(key, tbl_X[key_col], 0))`. No XLOOKUP, LET, FILTER, dynamic arrays, INDIRECT or OFFSET (D-002). |
| WI-2 | Calculated columns use structured references (`[@Col]`). Each table row has a stable ID; never refer to a row by position. `WorkbookContext.add_table` rewrites `[@Col]` to `tbl_X[[#This Row],[Col]]`, because LibreOffice 24.2 returns `#N/A` for the short form XlsxWriter emits. Formulas outside `add_table` must use the qualified form directly. |
| WI-3 | No CSE array formulas. Use a helper column instead, e.g. `Value_If_Valid` for peer medians. |
| WI-4 | A cell holds an input (blue), a same-sheet formula (black), a cross-sheet link (green), an imported value (grey) or an override (purple). QA checks that the font colour matches the content (W-07). |
| WI-5 | No typed number appears in a calc or link cell. Constants such as 1e7 come from `src/common/units.py` and are written into formulas by the generator, with a comment in the code. |
| WI-6 | A missing lookup must stay visible. A POSITION line whose Security_ID is not found returns `#N/A`; it is never wrapped to 0. `IFERROR(…,0)` is banned in calculation paths. `IFERROR(…,"MISSING")` is allowed only in display cells. |
| WI-7 | **Blank propagation.** `INDEX` of an empty cell returns **0** in Excel, which would turn an unvalued holding into a fair value of 0 (an R009 violation). Every link to a possibly blank source uses `=IF(INDEX(…)="","",INDEX(…))`. Coverage decisions read the explicit `Valuation_Coverage_Status` column, never `ISNUMBER(FV)` alone. |
| WI-8 | Percentages are decimals. Money is in INR crore or INR, per the column suffix. Conversion between them happens only through `×1e7` or `/1e7` written in the formula. |
| WI-9 | Every output that can be mistaken for another of the five value outputs carries its `OutputLabel` caption in an adjacent cell. |
| WI-10 | The original market price, model fair values and imported data are never targets of a scenario formula (R008). Scenario columns live only in `tbl_PriceControls`, `tbl_SectorShocks` and `tbl_CustomAllocation`. |

### Reference link patterns (import from `src/common/link_patterns.py`; do not retype)

| Constant | Where | Behaviour (verified in LibreOffice by `tests/test_common_link_patterns.py`) |
|---|---|---|
| `blank_safe(table, col)` | any link to a possibly blank source | the source value, or `""` when the source is blank or the key is absent. Never 0 (WI-7) |
| `PC_MODEL_FV[case]` | `tbl_PriceControls[Model_FV_Base/Bear/Bull]` | blank-safe link to `tbl_ValuationOutputs[FV_<case>_INR]` |
| `H_CURRENT_PRICE` | holdings `Current_Market_Price` | `""` for ONA lines; `#N/A` for a POSITION whose Security_ID has no price-control row (WI-6) |
| `H_BASE_FV` | holdings `Base_Fair_Value` | blank-safe link to `tbl_PriceControls[Model_FV_Base]` |
| `H_COVERAGE_STATUS` | holdings `Valuation_Coverage_Status` | contract §7.0 classification |
| `H_ADJ_BASE` | holdings `Adj_Base` | contract §7.2 `w × (FV/P − 1)` for MODEL_VALUED lines, else 0 |
| `H_MV_MKT` | holdings `MV_Mkt_INR_Cr` | `q × P / 1e7` for positions, disclosed value for ONA lines |

The Bear, Bull and Selected variants follow the same shape. 03-nav adds them to `link_patterns.py` through a change request, so they live next to the others and are tested the same way.

Valuation outputs → model sheet (02-valuation, inside `tbl_ValuationOutputs`): `FV_Base_INR = out_S00001_FV_Base`, a green link to the VAL_* sheet's named output.

## 4. Chart zones (D-017)

Sheet owners reserve space with `ctx.reserve_chart_zone(owner, zone_id, sheet, anchor, purpose)`. 04-charts is the only module that creates charts, and it places each one in a reserved zone. A sheet owner that wants a chart reserves the zone and lists the chart ID from the spec catalogue (G/V/B/peer/sector/NAV charts) in the zone's `purpose`. 04-charts renders a visible missing-data notice instead of a chart when the zone's series has fewer than `min_observations` points.

Zone naming: `<SHEET-SHORT>_<CHARTID>`, e.g. `VAL_HDFC_BANK_V002`, `MF001_SECTOR_ALLOC`, `DASH_NAV_COMPARE`.

## 5. Sheet ownership summary

| Owner | Sheets |
|---|---|
| 00-main | START_HERE, EXECUTIVE_DASHBOARD, GLOBAL_ASSUMPTIONS, METRIC_DICTIONARY, MODEL_GOVERNANCE, VALIDATION_CHECKS |
| 01-data | MASTER_SECURITY_REGISTRY, RAW_FINANCIAL_DATA, MARKET_PRICES, SECTOR_CLASSIFICATION, SOURCE_LOG, MISSING_DATA, DATA_FEASIBILITY |
| 02-valuation | VAL_* (7 named + template-generated), VALUATION_ASSUMPTIONS, VALUATION_OUTPUTS, HISTORICAL_METRICS |
| 03-nav | SCENARIO_ANALYSIS, PPFAS_FLEXICAP_HOLDINGS, HDFC_MIDCAP_HOLDINGS, MF_NAV_CALCULATOR, MF_SCENARIO_BUILDER, MF_SECTOR_ANALYSIS, MF_NAV_SENSITIVITY, MF_COVERAGE_AUDIT, PORTFOLIO_REBALANCING, FUND_PERFORMANCE |
| 04-charts | PEER_GROUPS (+ every chart, via zones) |
| 05-qa | none. Writes `build/out/validation_results.csv`, which 00-main renders on VALIDATION_CHECKS |

Five sheets are additions to the v3 spec list: DATA_FEASIBILITY, VALUATION_ASSUMPTIONS, VALUATION_OUTPUTS, FUND_PERFORMANCE and VALIDATION_CHECKS. They hold deliverables the spec requires but did not give a sheet (D-012).
