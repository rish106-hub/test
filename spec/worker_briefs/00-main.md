# Brief 00-main: Architecture and integration

**Launch:** `claude --model opus --effort xhigh "Read CLAUDE.md and spec/worker_briefs/00-main.md. You are the integration session."`

## Mission

Own the contract and assemble the workers' modules into one workbook. Accept or reject change requests, keep `MODEL_GOVERNANCE` current, and decide what ships. You own `CLAUDE.md`, `spec/**`, `src/common/**`, `build/**`, `tools/**`, `data/reference/**`, `tests/contract/**`, `tests/fixtures/**` and the sheets START_HERE, EXECUTIVE_DASHBOARD, GLOBAL_ASSUMPTIONS, METRIC_DICTIONARY, MODEL_GOVERNANCE and VALIDATION_CHECKS.

## Integration loop

For each worker branch that reports ready:

1. `git fetch` and check out the integration branch (currently `claude/financial-modeling-architecture-o2xiwz`).
2. Run `python tools/check_ownership.py <worker> <integration-branch>` on the worker branch. Reject any branch that touches files it does not own.
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
