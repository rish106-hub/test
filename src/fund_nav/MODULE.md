# Module 03-nav: MF NAV engine and scenario controls (src/fund_nav and src/scenarios)

Delivery document required by `spec/module_contracts.toml` (D-027). `tools/check_module_contract.py 03-nav` rejects the module while any section below is empty or contains TODO. Keep it short and factual. Every claim should point to a file, a table, a test or a contract section.

## Inputs

TODO: every interface table, defined name and canonical CSV the module reads, with the contract section that defines it. It must match `consumes` in `spec/module_contracts.toml`.

## Outputs

TODO: every interface table, name, sheet and CSV the module produces, with units. It must match `builds_tables`, `defines_names` and `writes_csv`.

## Assumptions

TODO: every assumption the module makes that the contract does not fix: value, rationale, Assumption_ID or source. "None" is an acceptable answer only if it is true.

## Limitations

TODO: what the module does not do yet, known data gaps (with their `missing_data.csv` IDs), and their impact on outputs.

## Tests

TODO: the contract tests that pass under `--strict-impl`, your own tests, and the isolated build and recalculation you ran, with date and result. Anything not run is NOT RUN.
