# Indian Equity Valuation and MF NAV Engine

Source, reference math and validation harness for a formula-driven Excel model. The model values Indian listed companies and estimates the modelled intrinsic value per unit of **Parag Parikh Flexi Cap Fund** and **HDFC Mid Cap Fund** (Direct Plan, Growth). The requirement is spec v3.0 (`Indian_Equity_Valuation_and_MF_NAV_Model_v3.xml`).

> **Status: architecture only.** The contract, schemas, interfaces, ownership map, contract tests, build pipeline and QA harness exist. No valuation, NAV, data or chart module is implemented yet, so a build today produces a skeleton workbook whose module sheets read "NOT YET BUILT". No real data has been retrieved.

## Layout

```
CLAUDE.md                      shared rules for every session (read first)
spec/
  financial_model_contract.md  definitions and formulas: the single source of truth
  data_schema.md               every table (generated from src/common/schema.py)
  workbook_interface.md        how modules link inside the workbook
  decisions.md                 architecture decisions and spec-ambiguity resolutions
  test_plan.md                 contract, independent, workbook and end-to-end tests
  ownership.toml               who may edit which files and sheets
  worker_briefs/               launch brief per worktree (00-main … 05-qa)
  change_requests/             how workers request contract changes
src/
  common/                      schema, enums, units, validation, styles, Excel rules, WorkbookContext
  ingestion/  valuations/  scenarios/  fund_nav/  peers/  charts/   module interfaces (stubs)
build/
  generate_workbook.py         integration build → build/out/*.xlsx (never committed)
  recalc.py                    LibreOffice forced recalculation for verification
  interface_stubs.py           stubs for isolated single-worker builds
data/
  reference/                   metric dictionary, global inputs, seed scope and peer groups
  canonical/                   source-backed CSVs (01-data)
  raw/                         retrieved source files + source_manifest.csv hashes
tests/
  contract/                    frozen hand-computed acceptance tests per module
  fixtures/synthetic/          SYNTHETIC data (rejected by production builds)
tools/                         ownership check, schema-doc and fixture generators
```

## Parallel sessions

```
# Data and source audit
claude --worktree 01-data      --model sonnet --effort high   "Read CLAUDE.md and spec/worker_briefs/01-data.md, then execute the brief."
# Bank and insurance valuation
claude --worktree 02-valuation --model opus   --effort xhigh  "Read CLAUDE.md and spec/worker_briefs/02-valuation.md, then execute the brief."
# Mutual-fund NAV engine
claude --worktree 03-nav       --model sonnet --effort high   "Read CLAUDE.md and spec/worker_briefs/03-nav.md, then execute the brief."
# Charts and peer comparisons
claude --worktree 04-charts    --model sonnet --effort medium "Read CLAUDE.md and spec/worker_briefs/04-charts.md, then execute the brief."
# Independent reviewer
claude --worktree 05-qa        --model opus   --effort high   "Read CLAUDE.md and spec/worker_briefs/05-qa.md, then execute the brief."
# Integration (main checkout)
claude --model opus --effort xhigh "Read CLAUDE.md and spec/worker_briefs/00-main.md. You are the integration session."
```

All five workers can start at once. 02, 03 and 04 develop against synthetic fixtures and stubbed interfaces (`--test-build --only <id>`), then switch to real data as 01-data delivers it. 05-qa writes its clean-room tests and the workbook harness from the spec while the others build.

## Quick check

```
pip install -r requirements.txt   # plus LibreOffice (soffice) for workbook tests
python -m pytest                              # 20 pass; 63 contract tests skip until each owner implements them
python build/generate_workbook.py --test-build
```
