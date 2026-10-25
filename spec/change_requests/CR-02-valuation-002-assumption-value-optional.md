# CR-02-valuation-002: allow a blank Value in tbl_Assumptions (an input not yet set)

Requested by: 02-valuation            Date: 2026-10-25
Contract section: data_schema `assumptions` (src/common/schema.py `ASSUMPTIONS`), R001

## Problem

`ASSUMPTIONS.Value` is `required=True`. A driver row that has a rationale, an evidence plan and a source type, but no value yet (because the real data has not landed), fails production validation. `tools/check_module_contract.py` validates `data/canonical/assumptions.csv` in production mode, so such a file is rejected.

The 02-valuation brief asks for the HDFC Bank driver structure to be drafted in `assumptions.csv`, "leaving any value that would need real data blank". Under the current schema the file can hold only the four D-009 weight rows. The draft therefore lives in the parameter catalogue on VALUATION_ASSUMPTIONS and in `src/valuations/parameters.py` instead.

## Proposal

Set `C("Value", "float", required=False, description="Blank = not yet set; the input resolves to MISSING and dependent outputs stay blank")`. This is the convention `global_inputs` already uses: "Blank Value = not yet set; dependent outputs stay blank rather than using a hidden default".

02-valuation already treats a blank Value as "not set" (`src/valuations/parameters.py::parse_rows`). The row is skipped during resolution, so the sheet input is blank and shows MISSING, and the fair value is blank and UNVALUED. Nothing is ever defaulted (R001, R009). `tests/valuations/test_valuation_module.py::test_blank_assumption_value_is_not_set` covers this.

## Impact on other workers

* 03-nav and 05-qa read `tbl_Assumptions` only for display or provenance. A blank Value is already possible in the workbook, because a user can clear the blue cell. The perturbation test `test_missing_input_leaves_fair_value_blank_and_unvalued` shows the effect: FV blank, never 0.
* `spec/data_schema.md` must be regenerated.

## Tests

No formula changes. The new behaviour is a validation rule:

* `validate_rows(ASSUMPTIONS, [row with Value ""])` returns no problem. Today it returns "Value is required".
* `parse_rows` on that row returns `[]`, so the resolver finds no row and the input stays MISSING. This is the existing test above.
