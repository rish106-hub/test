# Brief 01-data: Data and source audit

**Launch:** `claude --worktree 01-data --model sonnet --effort high "Read CLAUDE.md and spec/worker_briefs/01-data.md, then execute the brief."`

## Mission

Phase 1 of the spec (`<implementation_sequence>`). Find out what data can actually be obtained, obtain it from primary sources, and produce source-backed canonical tables. Every other worker builds on what you deliver. **Nothing you write may be estimated, remembered or invented (R001).** If you cannot retrieve a value, leave it blank and record it in `missing_data.csv`.

## You own

`src/ingestion/**`, `data/raw/**`, `data/canonical/**` (except `assumptions.csv`, `peer_*.csv` and `governance_log.csv`), `data/source_manifest.csv`, `tests/ingestion/**`, `reports/data/**`, and the sheets MASTER_SECURITY_REGISTRY, RAW_FINANCIAL_DATA, MARKET_PRICES, SECTOR_CLASSIFICATION, SOURCE_LOG, MISSING_DATA and DATA_FEASIBILITY.

You may read everything else but not edit it. Run `python tools/check_ownership.py 01-data <integration-branch>` before every push.

## Read first

`CLAUDE.md` → `spec/data_schema.md` (your output format) → `spec/financial_model_contract.md` §0 (units) → `src/common/schema.py`, `validate.py`, `units.py`.

## Work, in priority order

The critical path is the phase-3 end-to-end test: HDFC Bank → an actual holding → a fund's estimated NAV. Do items 1–5 first.

1. **Feasibility inventory** (`dataset_inventory.csv` + `reports/data/feasibility_report.md`). For every dataset below, actually try the retrieval from this environment and record the outcome: method, history available, latest date, licensing constraints, and what failed (HTTP status, proxy refusal, terms of use). Do not assume a paid API exists.
   * Each of the 7 companies: ~10 annual reports, ~20 quarterly results, investor presentations. For Max Financial, also the Axis Max Life EV, VNB, APE, solvency and stake.
   * Both schemes (MF001 Parag Parikh Flexi Cap, MF002 HDFC Mid Cap; **Direct Plan Growth**): latest and prior monthly portfolio disclosures (AMC website, AMFI), factsheet (TER, benchmark, AUM, manager), NAV history (AMFI), and the benchmark TRI (index provider).
   * Prices on one common date for every registry security (NSE/BSE bhavcopy). Foreign closes and the RBI reference FX rate for foreign holdings.
   * The RBI/CCIL 10-year G-sec yield (for `in_Risk_Free_Rate`). Corporate actions (exchange filings). Peer-bank data for the peer groups in `data/reference/peer_groups_seed.csv`.
2. **Registry**. Give C001–C007 a Security_ID, ISIN and ticker from exchange sources (`data/reference/initial_scope.csv` has their classification). Then add **every** line of both funds' latest disclosures. Match by ISIN, never by name (`match_security`). New securities get `next_security_id`. Sector, ownership type, business model and asset class are separate fields (spec `<classification_rule>`): Indian Bank is `Financial Services` + `Government-owned (PSU)`.
3. **Holdings import** (`parse_disclosure`, `diff_portfolios`). One parser per AMC format. Convert lakh to crore and keep the raw value and unit. Give each line a `Line_Role`: securities are `POSITION`; TREPS, cash, receivables and net current assets are `ONA_*`, with liabilities negative. Write `fund_scheme_totals.csv` with the reported net assets. Check that weights sum to 1 ± `in_Weight_Sum_Tol`. **Never move a holding from one fund to another.** Add a test with a small real-format sample under `tests/ingestion/`.
4. **Official NAV** (`parse_amfi_nav`). Load NAV history for both Direct Growth plans, and the Regular Growth plans if available, keyed by AMFI scheme code (`fund_plans.csv`).
5. **Market prices**. Choose one price date (propose it in your report; 00-main sets `in_Price_Date`). Record `Close_LCY`, `FX_Rate_to_INR`, `Close_INR` and the local close timestamp.
6. **Raw financials** for HDFC Bank first, then the other banks, then Max Financial. Use the `metric_dictionary` Metric_IDs. Record one accounting basis per company (state which). Mark restatements with `Supersedes_Observation_ID`. Set `Known_As_Of` to the publication date. Every value gets a `source_log` row with document, page/table and URL.
7. **Corporate actions** for every registry security over the history window.
8. **`missing_data.csv`** for every gap. Name the affected outputs, e.g. "AU SFB Q1FY2022 NIM missing → chart B001 has 19 observations".
9. **Sheet builder** `src/ingestion/sheets.py::build_sheets`: build your seven sheets from the canonical CSVs with `ctx.add_table` and `TableColumn(role="imported")`. Imported cells are grey.

## Rules

* Source tier 1 or 2 (spec `<source_priority>`) for financials, holdings and NAVs. Tier 3 only for prices and peer multiples, and label it so.
* Every data row → `Source_ID` → `source_log` → `Source_Doc_ID` → `source_manifest`, with a SHA256 of the retrieved file. Commit raw files under `data/raw/<entity>/` when licensing allows; otherwise keep only the URL and hash.
* Canonical CSVs are append-only. A revision is a new row, never an edit.
* `validate_csv(table, path)` (production mode) must return `[]` for every CSV you write.

## Done when

- [ ] `python -m pytest tests/contract/test_ingestion_contract.py tests/ingestion --strict-impl` passes
- [ ] Every canonical CSV you own validates in production mode
- [ ] `reports/data/feasibility_report.md` lists every dataset as available / partial / unavailable, with evidence
- [ ] Both funds' latest holdings imported, with reconciliation status reported in the feasibility report
- [ ] HDFC Bank raw financials complete enough for contract §3.6, or the gaps are listed with their impact
- [ ] `python build/generate_workbook.py` builds your sheets (other modules may still be unbuilt)
- [ ] `python tools/check_ownership.py 01-data <base>` is clean

Push your worktree branch and tell 00-main what landed and what is missing.
