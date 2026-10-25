# Change Requests

`spec/`, `src/common/`, `tests/contract/`, `tests/fixtures/` and `build/` are frozen for workers. If you need one of them changed, for example a new column, a new enum value, a clarified formula, a fixture case or a new link pattern, do **not** edit it and do **not** work around it locally. File a change request instead:

1. Create `spec/change_requests/CR-<worker>-<nnn>-<slug>.md` **on your own branch**. This one path is writable by every worker:

   ```
   # CR-03-nav-001: add Bear/Bull/Selected link patterns
   Requested by: 03-nav            Date: 2026-10-26
   Contract section: workbook_interface §3
   Problem: <what you cannot express with the current contract>
   Proposal: <exact text, column or formula>
   Impact on other workers: <who must change what>
   Tests: <new/changed contract tests with hand-derived values>
   ```

2. Keep working against the current contract. If you are blocked, implement the rest and leave the dependent piece raising `NotImplementedError("blocked on CR-…")`.
3. 00-main accepts or rejects the CR, edits the frozen files and logs a `MODEL_GOVERNANCE` row. It then tells the affected workers to merge the integration branch.

A CR that changes a definition in `financial_model_contract.md` also needs a hand-computed test case. A definition with no test is not part of the contract.
