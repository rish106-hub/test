# Completion criteria (spec v3 `<completion_criteria>`)

Status as of 2026-10-25. No criterion is marked met without an executed check. No production build exists yet, and worker modules are not merged, so every criterion is **NOT RUN** (not met as far as QA can show). The "Check" column names the automated or manual check that will decide each one.

| # | Criterion (abridged) | Status | Check that decides it | Notes |
|---|---|---|---|---|
| CC-01 | Seven dedicated company valuation sheets linked to the registry and summary outputs | NOT RUN | W-01, W-03e, W-05 | Wave 1 builds HDFC Bank only (D-028). |
| CC-02 | Both Direct Plan Growth schemes have independent, source-backed constituent tables | NOT RUN | I-REAL-01, PROV-01, E-02 | Needs 01-data. |
| CC-03 | All material holdings have a valuation status and method or a missing-data warning | NOT RUN | W-03c, W-12, W-02 (#N/A explained by status) | |
| CC-04 | Shocks, bias and absolute prices operate independently and recalculate linked outputs | NOT RUN | W-10a–c, W-10h, W-06, W-17, E-04 | The logic is verified on the clean-room (I-PRC-*, I-PROP-07a). The workbook check awaits 03-nav. |
| CC-05 | Official NAV, fair NAV, scenario NAV and hypothetical value are distinguished | NOT RUN (partial PASS) | W-08a (PASS), W-08b | |
| CC-06 | Sector, growth, earnings, multiples, peers, sensitivity and NAV scenarios as functioning charts | NOT RUN | W-13 | 04-charts is Wave 2. |
| CC-07 | Every chart linked to formula outputs or sourced data, not images | NOT RUN | W-13 | |
| CC-08 | Source traceability, missing-data warnings, valuation coverage and executed validation results | NOT RUN (partial) | PROV-01/02/03, W-12, W-18; `qa/run_validation.py` | Executed validation results exist (this runner). Traceability awaits data. |
| CC-09 | A new security from any sector can be added without rewriting the NAV engine | NOT RUN | W-10 variant with an added registry/holdings row | Not yet automated; planned after the 03-nav merge. |
| CC-10 | The four fund-level values are clearly separated throughout | NOT RUN | W-08b, W-18 | |
| CC-11 | Market shock, fundamental change, manual bias and absolute price are independent controls with separate outputs | NOT RUN | W-03a/b, W-10a–c, W-10e | |
| CC-12 | Data-feasibility audit before completion | NOT RUN | Review of DATA_FEASIBILITY / dataset_inventory | Needs 01-data. |
| CC-13 | Complete end-to-end test from one company to an actual fund's intrinsic value per unit | NOT RUN | E-01…E-04 (gate G1) | |
| CC-14 | Fund performance vs benchmark, rolling returns, risk, fees and common holdings where data allows | NOT RUN | T-PERF via the 03-nav merge; FUND_PERFORMANCE review | |
| CC-15 | Point-in-time-aware historical testing with bias, error and sample reporting | NOT RUN | H-01 | No point-in-time data exists. |
| CC-16 | Every key assumption and override traceable in the governance log | NOT RUN | Review of governance_log.csv and assumptions.csv | |
