# CR-03-nav-002: Controls_At_Default interface, the W-17 reset check, and Control_Warning's shock test

Requested by: 03-nav            Date: 2026-10-25
Contract section: §6.1 rule 2, §6.2, §6.3; test_plan W-11, W-17

Problem:
1. `tbl_PriceControls` must have exactly the schema columns, so the `Reset_*` columns and `Controls_At_Default` live in private tables on SCENARIO_ANALYSIS (`tbl_Nav_PriceDefaults`, `tbl_Nav_ControlsStatus`). 00-main's VALIDATION_CHECKS ("shows Controls_At_Default") has no interface to read: `tbl_Nav_*` is private, and 03-nav defines no `out_*` names (`defines_names = []`).
2. W-17 says the three shock inputs are referenced only by `Effective_Shock_Pct`. The reset check has to compare `Market_Price_Shock_Pct`, `tbl_SectorShocks` and `in_Global_Price_Shock_Pct` with their defaults, so those cells are also read in `tbl_Nav_PriceDefaults[At_Default]` and `tbl_Nav_ControlsStatus`. Neither applies a shock to a price.
3. §6.2 says to warn when "any of the three shocks != 0" and the mode is not Market Price Shock, but §6.1 rule 2 forbids reading the three inputs outside `Effective_Shock_Pct`. 03-nav tests the net `Effective_Shock_Pct` (rounded to 10 places). The two differ only when non-zero shocks cancel exactly (for example global -10% with a security +11.11%), where the price is the same either way.

Proposal:
* Add `Controls_At_Default` as an interface: either an `out_Controls_At_Default` name (03-nav then lists `out_Controls_At_Default` in `defines_names`) or a `tbl_Nav_ControlsStatus` entry in 00-main's `consumes`. 03-nav prefers the name.
* Exempt the two reset-check tables from the W-17 scan, or reword W-17 to "no price formula reads a shock input other than `Effective_Shock_Pct`".
* Reword §6.2 row 1 to "the net `Effective_Shock_Pct` is not 0".

Impact on other workers: 00-main (names/consumes, W-17 wording); 05-qa (W-17 scan scope).

Tests: contract tests T-PRC-03/06/11 pass unchanged; `tests/fund_nav/test_sheet_matches_reference.py` compares the workbook warning and status text with `resolve_controls`.
