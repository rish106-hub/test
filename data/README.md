# data/

| Folder / file | Owner | Contents |
|---|---|---|
| `reference/` | 00-main | Model reference data: `metric_dictionary.csv`, `global_inputs.csv` (the `in_*` names), `initial_scope.csv` (seed companies C001–C007 and their classification), `peer_groups_seed.csv` (peer sets named in the spec). This is configuration, not market data. |
| `source_manifest.csv` | 01-data | One row per retrieved source document, with URL and SHA256. Created by 01-data. |
| `raw/<entity>/` | 01-data | Retrieved source files, committed when licensing allows. |
| `canonical/` | 01-data (most), 02 (`assumptions.csv`), 04 (`peer_*.csv`), 00-main (`governance_log.csv`) | Validated, source-linked CSVs; schemas in `spec/data_schema.md`. Observation tables are append-only. |
| `scenarios/` | 03-nav | Saved hypothetical inputs (custom allocation). Never mixed with actual holdings. |

Rules: no value without a `Source_ID` (R002). A missing value is blank plus a row in `canonical/missing_data.csv`, never 0 and never an estimate. Every CSV must pass `src/common/validate.py::validate_csv` in production mode before it is committed.

`initial_scope.csv` classifications are marked `User assumption` until 01-data confirms them against exchange and company sources.
