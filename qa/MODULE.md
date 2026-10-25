# Module 05-qa: independent review

This is the delivery document required by `spec/module_contracts.toml` (D-027). 05-qa builds no workbook table, defines no name and writes no canonical CSV. It produces `build/out/validation_results.csv` for each build (schema `validation_results`) with `qa/run_validation.py`, and 00-main renders that file on VALIDATION_CHECKS.

## Inputs

All read-only. Nothing is consumed through workbook formulas, so `consumes = []`.

* **Contract and common layer:** `spec/financial_model_contract.md` §0–§10, `spec/workbook_interface.md`, `spec/test_plan.md`, `spec/decisions.md`, `src/common/` (enums, schema, units, excel_contract, link_patterns, ownership, validate), and `tests/contract/cases.py` (the hand-derived cases).
* **Generated workbook:** `build/out/Indian_Equity_Valuation_and_MF_NAV_Model.xlsx` (or a fresh test build), with its `manifest.json` and `build_report.json`. Values always come from the LibreOffice recalculation (`build/recalc.py`), never from cached values.
* **Interface tables read in the workbook:** `tbl_PriceControls`, `tbl_SectorShocks`, `tbl_Holdings_*`, `tbl_NAVSummary`, `tbl_OfficialNAV`, `tbl_SchemeTotals`, `tbl_FundPlans`, `tbl_ValuationOutputs`, `tbl_Registry`, `tbl_MarketPrices`, `tbl_CustomAllocation`, the `in_*` names (§6, §7) and the `out_*` names (§3).
* **Canonical CSVs** (E, PROV and I-REAL checks): `data/canonical/{source_log, fund_holdings, fund_scheme_totals, security_registry, market_prices}.csv`, `data/source_manifest.csv`, `data/raw/**` and `data/reference/global_inputs.csv`.
* **Workers' reference functions,** imported only to compare their results (D-020). Their bodies are not read (clean room).

## Outputs

* `build/out/validation_results.csv`: one row per executed or planned check, with `Executed`, `Result` (PASS/WARNING/FAIL/NOT RUN), `Evidence` and `Tool` (the pytest node id). Skipped, errored or unexecuted checks are `NOT RUN` with `Executed = FALSE`. A test on a known finding (xfail) is reported as FAIL and names the finding.
* `build/out/validation_run.json`: run metadata (which workbook was validated, counts, pytest exit code).
* `qa/findings/F-*.md` (index in `qa/findings/README.md`), `qa/financial_review.md`, `qa/completion_criteria.md`, `qa/provenance_audit.md`.
* No tables or names (`builds_tables = []`, `defines_names = []`, `writes_csv = []`).

## Assumptions

Each place where the contract leaves a choice open is marked `QA-READING` in `tests/independent/cleanroom/` and routed as a finding:

* Method 2/3 hold MARKET_PASS_THROUGH lines at their disclosed value; the q × P reading is also implemented (F-001).
* `Control_Status`: FAIL takes precedence over UNVALUED (F-005).
* `FV_Label`: only the prefix of the manual-bias label is compared (F-006).
* `Forecast_Update_Flag` is PASS when there are no interim results, and that case is not compared with the worker (F-007).
* The blend weight tolerance is 1e-9 (F-008).
* A fund with no equity has coverage status PASS. `Max_Financials_Age_Days` excludes undated lines. The caption uses Python `.1f` rounding (F-009).
* The comparison tolerance is 1e-9 relative (test plan W-03). It is never loosened. Disagreements are reported, not tuned away.

## Limitations

* **Workers not merged.** In this worktree every worker reference function is a stub, and the default test build has no worker sheets. 32 I-layer comparisons, 27 W checks and all E checks are therefore NOT RUN. They run as soon as 00-main merges the workers.
* **W-10 positive path unproven.** The W-10 manual tests are proven only by the round-trip proof (W-10-00), a harness self-test (W-10-01) and a negative control (W-SELF-03). Their positive path is unproven until 03-nav's formula sheets exist.
* **Bank valuation not recomputable from the workbook (F-012).** The bank valuation can't be recomputed clean-room from workbook or canonical data until 02-valuation exposes its reference inputs. Until then W-03e checks only the `out_*` ↔ `tbl_ValuationOutputs` links, W-14b is NOT RUN, and E-01 checks dates and freshness but not the full RI value.
* **Heuristic scans.** W-08b, W-19 and W-13 locate captions, date captions and missing-data notices by text near the cell. A layout that puts captions further away would be reported as FAIL, to be judged by hand.
* **Manual and data-dependent checks.** The sampled provenance audit (PROV-03), E-01…E-04, I-REAL-01 and PROV-01/02 need 01-data's real data. Historical validation (H-01) needs point-in-time data. All are NOT RUN.
* No `missing_data.csv` IDs apply: 05-qa produces no data.

## Tests

Run on 2026-10-25 in worktree branch `wave1/05-qa` against a fresh synthetic test build (`python qa/run_validation.py`, LibreOffice 24.2.7.2):

* **208 checks; 64 executed (PASS 62, WARNING 1, FAIL 1); NOT RUN 144.**
  * FAIL: W-09b (F-014). WARNING: I-PROP-06c (F-013).
  * NOT RUN: 75 contract tests (worker stubs), 32 I comparisons (stubs), 27 W checks (no worker sheets or production build), 6 E checks, 3 provenance checks, 1 historical check.
* **I layer** (`tests/independent/`): 40 clean-room reproductions of every hand-derived case (T-BNK-00…15, T-INS-01…04, T-PRC-00…12, T-NAV-01…17, T-CUS/HYP/OVL, T-PEER) all pass. 10 property tests pass on the clean-room, and their worker halves are NOT RUN. The 21 differential tests are NOT RUN.
  * Self-check (scratchpad, not committed): with clean-room adapters standing in for the workers, all 81 I tests pass, and 4 seeded mutants (RI × (1 + 1e-7), Method 2 ignoring liabilities, double-applied shock, caption format) each fail at least one test.
* **W layer** (`tests/workbook/`): W-10-00 round trip is value-identical (all cells, tables, names and formulas preserved). W-02, W-04, W-05, W-07 and W-08a pass on the test build. W-SELF-01 shows that W-04/05/06/07/15/17 each fail on a seeded violation. W-SELF-02 shows that W-03a/c, W-11, W-12, W-14a, W-16 and W-18 pass on a correct value-only workbook and fail on 4 mutants. W-SELF-03 shows that every W-10 body fails when inputs do not propagate.
* `python tools/check_module_contract.py 05-qa`: OK. `python -m pytest`: 97 passed, 142 skipped, 1 xfailed, **1 failed**. The failure is `tests/test_common_module_contracts.py::test_module_doc_templates_are_rejected_until_filled` (00-main's test). It requires every live MODULE.md to remain the TODO template, which contradicts D-027. See F-015. Every 05-qa test passes. `python tools/check_ownership.py 05-qa claude/financial-modeling-architecture-o2xiwz`: OK.
* **Re-run commands:** after each integration build, `python qa/run_validation.py --workbook build/out/Indian_Equity_Valuation_and_MF_NAV_Model.xlsx`. For an isolated worker build, `python qa/run_validation.py --only 03-nav`.
