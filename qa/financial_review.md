# Financial review (spec v3 `<financial_checks>` and `<portfolio_checks>`)

Status as of 2026-10-25. The latest **production** build does not exist yet: 01-data, 02-valuation and 03-nav are not merged. An item is PASS, WARNING or FAIL only with evidence from an executed check. Everything else is NOT RUN, with the reason given. Contract-level observations from the clean-room implementation are listed separately, because they are reviews of the definitions, not of the build.

## Financial checks

| # | Check | Status | Evidence / reason |
|---|---|---|---|
| FC-1 | Financial units and currency consistency | NOT RUN (build) | W-16 (q × P / 1e7, Close_INR = Close_LCY × FX) needs worker sheets. The contract definitions were checked: the clean-room reproduces T-BNK-10 (crore → INR per share via 1e7) and T-NAV-03 (FX cancels in FV/P). |
| FC-2 | Share count and corporate-action adjustments | NOT RUN | Needs real raw_financials and corporate_actions (01-data). |
| FC-3 | Balance-sheet and capital reconciliations | NOT RUN (build) | Contract definition verified: I-PROP-08 shows that driver-model BVPS equals the clean-surplus BV over 400 random projections, so the §3.6 capital-retention check passes. The workbook check needs VAL_* (F-012). |
| FC-4 | Consistent standalone/consolidated basis | NOT RUN | Needs real raw_financials. |
| FC-5 | Valuation formula signs and discounting periods | NOT RUN (build) | Contract definitions verified by the clean-room against T-BNK-00…05 and 11…14 (end-of-year discounting, τ = days/365.25, dividends compounded from ex-date). The comparison with 02's reference (I-CMP-01…06) is NOT RUN until merge. |
| FC-6 | Terminal growth below terminal discount rate | NOT RUN (build) | The clean-room raises on g ≥ r (I-BNK-04). W-14b cannot locate VAL_* grid cells (F-012). |
| FC-7 | Appropriate business-model method (R004) | NOT RUN (build) | I-BNK-06 passes on the clean-room. E-01 checks HDFC Bank's Primary_Method = Residual Income on the production build. |
| FC-8 | Current and forward multiples | NOT RUN | Needs peers (04-charts, Wave 2) and real prices. |
| FC-9 | Diluted share-count treatment | NOT RUN | Needs real data and the VAL_* inputs (F-012). |

## Portfolio checks

| # | Check | Status | Evidence / reason |
|---|---|---|---|
| PC-1 | Duplicate ISIN / Security_ID detection | NOT RUN | Needs real security_registry (01-data). The schema PK check runs in `src/common/validate.py`. |
| PC-2 | Holdings reconciled to the source file | NOT RUN | I-REAL-01 and E-02/E-03 run once real holdings land. |
| PC-3 | No contamination by custom portfolio inputs | NOT RUN (build) | I-CUS-01-03 passes on the clean-room. W-10d (perturb tbl_CustomAllocation, then assert that no holdings, NAV or control cell moves) and W-06 run after the 03-nav merge. |
| PC-4 | Sector weights reconcile to actual or unallocated | NOT RUN (build) | I-PROP-03: sector contributions sum to the total over 400 random funds, on the clean-room. |
| PC-5 | Constituent weights reconcile within sector | NOT RUN (build) | I-CUS-01-03 (clean-room). |
| PC-6 | Valuation coverage and unvalued weights disclosed | NOT RUN (build) | W-12/W-18 run after merge. **F-011:** the dashboard lacks Unvalued_Count, Unvalued_Weight_Pct and NAV_Date_Gap_Days. **F-013:** total coverage can be negative. |
| PC-7 | Holdings, price and valuation dates visible | NOT RUN (build) | W-12, W-19 and W-03c (date columns of tbl_NAVSummary). |
| PC-8 | Fair NAV and Scenario NAV not labelled official | PASS (partial) / NOT RUN | W-08a PASS: START_HERE defines all five OutputLabel captions. W-08b (captions next to every output cell) is NOT RUN until 03-nav merges. |
| PC-9 | Hypothetical rebalancing kept separate | NOT RUN (build) | I-HYP-01-02 passes on the clean-room. W-10d and W-06 cover the workbook after merge. |

## Contract-level review (clean-room implementation, executed)

* Every hand-derived contract case (75 contract tests' expectations) is reproduced by an independent implementation written from `spec/` only (I-BNK, I-INS, I-PRC, I-NAV, I-CUS, I-HYP, I-OVL, I-PEER: 40 tests PASS). The contract is internally consistent and achievable.
* Properties verified on the clean-room over seeded random inputs:
  * steady-state RI = DDM = justified P/B (1e-9);
  * Method 1 = Method 2 when weights equal q × P / NA;
  * sector contributions sum to the total;
  * Scenario NAV = Official NAV at default controls;
  * a monotone fair-value change gives a monotone NAV;
  * the shock algebra is order-independent, and the TPP is unaffected by price shocks;
  * the equity-bridge identities hold.
* Ambiguities found while implementing (two careful readers would differ): **F-001, F-002, F-005, F-006, F-007, F-008, F-009, F-013**. Internal contradictions: **F-003, F-004, F-010**. Interface gaps that prevent independent verification: **F-012**. Build or test defects in 00-main code: **F-011, F-014, F-015**.
