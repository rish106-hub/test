# Brief 00-main: Architecture and integration

**Launch:** `claude --model opus --effort xhigh "Read CLAUDE.md and spec/worker_briefs/00-main.md. You are the integration session."`

## Mission

Own the contract and assemble the workers' modules into one workbook. Accept or reject change requests, keep `MODEL_GOVERNANCE` current, and decide what ships. You own `CLAUDE.md`, `spec/**`, `src/common/**`, `build/**`, `tools/**`, `data/reference/**`, `tests/contract/**`, `tests/fixtures/**` and the sheets START_HERE, EXECUTIVE_DASHBOARD, GLOBAL_ASSUMPTIONS, METRIC_DICTIONARY, MODEL_GOVERNANCE and VALIDATION_CHECKS.

## Launch waves and gate G1 (D-028)

Prove the financial calculations on one path before multiplying models, charts and workers.

* **Wave 1: the vertical slice.** 01-data, 02-valuation, 03-nav and 05-qa start together. 02 and 03 build against synthetic fixtures and stubs until real data lands, but their real-data scope is HDFC Bank and the fund that holds it.
* **Gate G1.** It passes only when every item below has been *executed* on a production build:
  - [ ] E-01: HDFC Bank valued by the full RI path from cited data, with the equity bridge and freshness shown (§3.1a/b)
  - [ ] E-02: HDFC Bank confirmed as a holding of an actual Direct Plan Growth scheme, citing that scheme's disclosure
  - [ ] E-03: that fund's Fair NAV (M1 and M2), reconciled, with all three data-quality measures (§7.5)
  - [ ] E-04: shock, bias and absolute price applied to HDFC Bank move only the expected outputs
  - [ ] Both funds: one complete source-backed portfolio snapshot each, with `Holdings_Coverage_Status = PASS`, and every holding that lacks adequate data listed in `missing_data.csv` and on MF_COVERAGE_AUDIT
  - [ ] 05-qa's clean-room implementation agrees with the 02 and 03 reference functions on that real data
  - [ ] `tools/check_module_contract.py` accepts 01-data, 02-valuation and 03-nav; no open blocker finding
* **Wave 2, after G1:** 02 replicates to the other five banks and Max Financial, 03 covers every material holding of both funds, and 04-charts is launched. Record the G1 decision in `governance_log.csv`.

## Integration loop

For each worker branch that reports ready:

1. `git fetch` and check out the integration branch (currently `claude/financial-modeling-architecture-o2xiwz`).
2. Run `python tools/check_ownership.py <worker> <integration-branch>` on the worker branch. Reject any branch that touches files it does not own.
   Then build the worker in isolation (`python build/generate_workbook.py --test-build --only <worker>`) and run `python tools/check_module_contract.py <worker> --manifest build/out/manifest.json --run-tests`. Reject the module on any `REJECT` line (D-027): wrong or missing interface tables or columns, undeclared tables or names, references outside its `consumes`, failing contract tests, invalid CSVs, or an unfilled `MODULE.md`.
3. Merge with `--no-ff`. Merge order is 01-data → 02-valuation → 04-charts (peers) → 03-nav. Re-run 04-charts' rendering last.
4. Gate, in order. Stop at the first failure and send it back to the owner.
   * `python -m pytest --strict-impl tests/contract/<owner's files>`, then `python -m pytest`
   * `python tools/render_schema_doc.py --check` and `python tools/make_synthetic_fixtures.py --check`
   * `python build/generate_workbook.py --test-build`, then `build/recalc.py` on the output
   * `python build/generate_workbook.py` (production; fails on invalid or synthetic data)
5. Ask 05-qa to run `qa/run_validation.py` on the new build, then rebuild so VALIDATION_CHECKS shows its results.
6. Add a `governance_log.csv` row for the merge: Change_Type, the version, test status taken from QA's results.

## Contract changes

A change request in `spec/change_requests/CR-*.md` is accepted only with a hand-derived test case. On acceptance:
* edit `spec/` and `src/common/` (and `tests/contract/` / fixtures if needed);
* regenerate the schema doc and fixtures;
* add a decision row to `decisions.md`;
* tell the affected workers to merge the integration branch.

## Your own build tasks

* After 01-data's feasibility report, set `in_Valuation_Date` and `in_Price_Date` in `data/reference/global_inputs.csv`: the latest date on which prices, NAVs and holdings reconcile.
* EXECUTIVE_DASHBOARD (`build/main_sheets.py::build_dashboard`): add the selectors the spec lists in `<dashboard_controls>`, the coverage and freshness panel, and navigation links.
* README and the user operating manual (`docs/`): monthly-update workflow, reset procedure, worked examples taken from the contract test cases, and limitations.

## Release checklist (phase 7)

- [ ] W-01: production build, no unbuilt sheets, no stubs, no NotImplemented modules
- [ ] `validation_results.csv` from the latest build, with no FAIL left unanswered by a finding
- [ ] `qa/completion_criteria.md` reviewed; every unmet criterion stated plainly in the README
- [ ] Missing-data and limitations sections are current
