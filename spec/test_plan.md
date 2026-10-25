# Test Plan

Three layers. A test counts only if it has **executed**. Results go to `build/out/validation_results.csv` with `Executed = TRUE`; everything else is reported as `NOT RUN` (spec `<formula_audit>`, R-governance).

| Layer | What it proves | Where | Run by |
|---|---|---|---|
| **C** Contract | Each Python reference function matches hand-computed values | `tests/contract/` (frozen) | every worker, gate by 00-main with `--strict-impl` |
| **I** Independent | A clean-room re-implementation written from the spec agrees with the workers' reference | `tests/independent/` | 05-qa |
| **W** Workbook | The generated Excel formulas, recalculated in LibreOffice, equal the Python reference and obey the interface rules | `tests/workbook/` | 05-qa |
| **E** End-to-end | One real bank → one real holding → one real fund NAV estimate, with independent controls | `tests/workbook/test_e2e_*.py` | 05-qa on the production build |

Commands:

```
python -m pytest                      # all; unimplemented contract tests show as SKIPPED with owner
python -m pytest --strict-impl        # merge / QA gate: NotImplementedError = failure
python -m pytest -m workbook          # tests that need LibreOffice
```

---

## C. Contract tests (hand-derived)

Every expected value was computed by hand arithmetic, independently of any implementation. On 2026-10-25 they were checked to be mutually consistent and achievable by a throwaway implementation that passed all 63 under `--strict-impl`. That implementation was not committed.

### Pricing controls: `test_pricing_contract.py` (03-nav, contract §6)

| ID | Case | Expected |
|---|---|---|
| T-PRC-00 | All controls at default | Selected price 750, selected FV 500, label "Model output (unmodified)" |
| T-PRC-01 | Spec manual test 1: shock −10% on 750 | 675; FV still 500; inputs unchanged |
| T-PRC-02 | Spec manual test 2: bias −10% on 500 with shock active | FV 450; price still 675; label contains "MANUALLY BIASED" |
| T-PRC-03 | Spec manual test 3: absolute 595, with every shock also set | 595; FV 500; original 750 untouched |
| T-PRC-04 | Derived outputs | upside 450/675−1 = −33.33%; FV gap 450/750−1 = −40%; target base 400, selected 360 at 20% MoS |
| T-PRC-05 | Spec manual test 8: sector −5% compounding with security −10% | 750 × 0.9 × 0.95 = 641.25 |
| T-PRC-06 | Shocks set but mode Original | selected 750; after-shock 641.25 is displayed but not selected |
| T-PRC-07 | Fundamental case Bear | 400 |
| T-PRC-08 | Absolute mode, blank price | `None` (#N/A), status FAIL (D-014) |
| T-PRC-09 | Unvalued security | price controls work; every FV output is blank; status UNVALUED |

### Bank valuation: `test_bank_valuation_contract.py` (02-valuation, contract §2–3, §10)

| ID | Case | Expected / derivation |
|---|---|---|
| T-BNK-00 | CAPM 6.5% + 1.1 × 6%; DF(12%, 2y) | 13.1%; 1/1.12² |
| T-BNK-01 | Steady state BV 100, r 12%, ROE 15%, payout 50%, g 7.5%, N = 5 | RI = DDM = P/B_j × BV = 100 + 3/0.045 = **166.6667**; TV share 0.32585 |
| T-BNK-02 | BV 100; EPS 15, 16.5, 18; DPS 3, 3.3, 3.6; r 13%; ROE_T 14%; g 5% | BV 100 → 112 → 125.2 → 139.6; RI 2.0, 1.94, 1.724; PV_RI 4.48403; TV 1.396/0.08 = 17.45; PV_TV 12.09373; **V 116.57776** |
| T-BNK-03 | ROE_T = r | PV_TV = 0 |
| T-BNK-04 | g = r and g > r | TerminalGrowthError from RI, justified P/B and Gordon |
| T-BNK-05 | Roll-forward 166.667 from 2026-03-31 to 2026-10-25 (208 days), DPS 5 ex 2026-07-15; dividends outside the window ignored | 166.667 × 1.12^(208/365.25) − 5 × 1.12^(102/365.25) = **172.61685** |
| T-BNK-06 | FCFF DCF as a bank's primary method | MethodNotAllowedError (R004) |
| T-BNK-07 | Peer P/B 2.5 × BVPS 400 with n = 5, 2, 0 | 1000 PASS; 1000 WARNING; None MISSING |
| T-BNK-08 | Blend weights | 100; 95; None when a weighted method is missing; error when weights sum to 0.9 |
| T-BNK-09 | TV flag at 80% vs 75% threshold; grid with g = r | WARNING; cell None |
| T-BNK-10 | One-year driver projection (§3.6): Adv 1000 → 1100, IEA ×1.5, NIM 4%, NonII 20 → 22, opex 40 → 42, credit cost 1%, tax 25%, payout 20%, 1e8 shares, equity 200 | NII 63; PPOP 43; provisions 10.5; PAT 24.375 Cr; EPS ₹2.4375; DPS ₹0.4875; equity 219.5; BVPS ₹21.95; ROE 24.375/209.75 |

### Insurance SOTP: `test_insurance_contract.py` (02-valuation, contract §4)

| ID | Case | Expected |
|---|---|---|
| T-INS-01 | EV 20,000 + VNB 2,000 × 15; stake 80%; holdco discount 10%; cash 500; debt 300; 34.5 Cr shares | appraisal 50,000; equity 36,200 Cr; **₹1,049.28/share** |
| T-INS-02 | P/EV 2.0 instead | appraisal 40,000 |
| T-INS-03/04 | Both methods / neither | DoubleCountingError |

### NAV engine: `test_nav_contract.py` (03-nav, contract §7; cases in `tests/contract/cases.py`)

MF001: net assets 1,000 Cr = S90001 300 (₹750, FV 500/400/600) + S90002 200 (₹100, FV 120/90/150) + S90003 100 (unvalued) + cash 410 − payables 10. Official NAV Direct 80, Regular 72.
MF002: 500 Cr = S90002 100 + S90004 340 (USD 400 × FX 85; FV USD 440/380/500) + cash 60. Official NAV 150.

| ID | Case | Expected |
|---|---|---|
| T-NAV-01 | Classification | L1, L2 MODEL_VALUED; L3 UNVALUED; cash and payables CARRYING_VALUE |
| T-NAV-02 | Method 1 MF001 Base/Bear/Bull | 0.3 × (−1/3) + 0.2 × 0.2 = −6% → **75.20**; −16% → 67.20; +4% → 83.20 |
| T-NAV-03 | Method 1 MF002 with FX | +10.8% → **166.20**; −5.4% → 141.90; +27% → 190.50 |
| T-NAV-04 | Method 2 MF001 | NA_mkt 1000; NA_fair 940; NAV 75.20 (= M1 because weights are consistent) |
| T-NAV-05 | Plan ratio (D-004) | Direct 75.20, Regular 67.68; same % for both |
| T-NAV-06 | Scenario NAV at default controls | = Official NAV 80.00 exactly |
| T-NAV-07 | S90001 absolute 595, S90002 shock −10% | NA_scen 918 → **73.44** |
| T-NAV-08 | Spec manual test 5: S90001 FV 500 → 600 | MF001 78.40; MF002 unchanged at 166.20 |
| T-NAV-09 | Spec manual test 6: S90005 in registry but in neither fund | zero exposure; not listed as an MF001 line |
| T-NAV-10 | Spec manual test 7: coverage | total 90%; equity 83.3%; unvalued 10%, 1 line, 100 Cr; WARNING; caption contains "83.3%" and "10.0%" |
| T-NAV-11 | S90002 also becomes unvalued | equity coverage 50%; FAIL |
| T-NAV-12 | Reconciliation vs 1,000 and vs 1,010 | gap 0 PASS; −0.99% FAIL |
| T-NAV-13 | Selected case with a biased FV of 450 | 80 × (1 − 0.12 + 0.04) = 73.60 |

### Custom allocation, hypothetical portfolio, overlap: `test_allocation_contract.py` (03-nav)

| ID | Case | Expected |
|---|---|---|
| T-CUS-01 | Spec `<example>` FS 30% × 20% | 6%; weights incl. explicit cash sum to 1 |
| T-CUS-02 | No cash line; constituent sum 0.5; duplicate ID; negative weight | each is reported |
| T-CUS-03 | Spec manual test 4: custom inputs change nothing in actual holdings | MF001 lines identical before and after |
| T-HYP-01 | ₹10 lakh capital, 60/40, buy at 595 / 90, TC 0.1% | quantities 1007 / 4440; cash ₹236.235 |
| T-HYP-02 | Quantity override overspends | FAIL |
| T-OVL-01 | MF001 vs MF002 | overlap 20%, 1 common security |

### Returns `test_returns_contract.py`, peers `test_peers_contract.py`, performance `test_performance_contract.py`, ingestion `test_ingestion_contract.py`

| ID | Expected |
|---|---|
| T-RET-01/02 | XIRR = 10.000% for a 5-year (1,826-day) Excel-convention flow and for an interim-dividend flow |
| T-RET-04 | blank probabilities → None; 0.25/0.5/0.25 → 8.75%; sum 1.1 → ProbabilityError |
| T-PEER-01 | median 3.0 of {2, 3, 4}. Excluded peer, NM peer and the subject are not counted (n_valid 3, n_excluded 3) |
| T-PEER-02/03 | no valid peers → None; missing value dropped → median 2.5 |
| T-PERF-01..04 | 100 → 130 over 730 days: return 30%, CAGR 14.0175%; max drawdown −25%; vol 4.16340; downside deviation 1.98585 (MAR 5%); missing start → None |
| T-ING-01..03 | match by ISIN, never by name; next id S00008; monthly diff flags removed S00002 and unmatched INE555N01005 |

---

## W. Workbook tests (05-qa)

Run against `build/out/*.xlsx` after `build/recalc.py`. Every W test writes a row to `validation_results.csv`.

| ID | Check | Method |
|---|---|---|
| W-01 | Release build: production mode, `unbuilt_sheets = []`, no `not_implemented`, no stubs | `build_report.json` |
| W-02 | No `#REF!`, `#NAME?`, `#DIV/0!` or `#VALUE!` anywhere. `#N/A` only in rows whose status column explains it | scan the recalculated values |
| W-03 | **Excel ≡ Python** for every security in `tbl_PriceControls`, every plan in `tbl_NAVSummary` and every `out_*` name: equal to 1e-9 relative, with the inputs read from the same workbook | `read_defined_names` plus table scan, then the reference functions |
| W-04 | Every formula uses whitelisted functions only | openpyxl (formulas) + `excel_contract.check_formula` |
| W-05 | No raw cell reference to another owner's sheet; cross-sheet access only via `tbl_*`/`in_*`/`out_*` | regex over formulas + `manifest.json` |
| W-06 | R008: no formula in `Original_Market_Price`, model FV or imported columns depends on a scenario input column | dependency scan of formulas |
| W-07 | Font colour matches content: blue/purple = constants, black = same-sheet formula, green = cross-sheet formula, grey = imported constant | openpyxl font colours |
| W-08 | The five value outputs carry their `OutputLabel` captions; nothing labelled "NAV" shows a fair or scenario value without its caption | label scan |
| W-09 | A production build contains no `SYNTHETIC` text and no `SRC-SYNTH` IDs | value scan |
| W-10a–h | **Spec manual tests 1–8 executed on the workbook**: perturb input cells in a copy (openpyxl), recalculate, and assert the output changes in T-PRC-01/02/03, T-CUS-03, T-NAV-08/09/10, T-PRC-05. First prove that an unperturbed openpyxl round trip recalculates to identical values, because openpyxl drops charts but must keep formulas, tables and names | perturbation harness |
| W-11 | Reset: with all controls at default, Scenario Market NAV = Official NAV for every plan, and `Controls_At_Default = TRUE` | recalc |
| W-12 | EXECUTIVE_DASHBOARD shows the coverage caption, unvalued count/weight and holdings-date/price-date warnings for every plan | value scan |
| W-13 | Every chart's series refer to cell ranges, not images; every chart has title, units and source note; charts with too few data points are replaced by a missing-data notice | `xl/charts/*.xml` |
| W-14 | Terminal controls: no Gordon cell with g ≥ r shows a number; TV share is present for every valued security | recalc |
| W-15 | Blank propagation: every cross-table link whose source column can be blank uses `link_patterns.blank_safe` | formula scan |
| W-16 | Units: a sample of `MV_Mkt_INR_Cr` re-derived from quantity × price / 1e7; per-share values re-derived from crore / shares | recalc |

## I. Independent re-implementation (05-qa)

05-qa writes `tests/independent/` **from `spec/` only, without reading `src/` implementations** (clean room). It covers contract §3.2 RI, §3.3 DDM, §3.6 drivers, §4 SOTP, §6 controls and §7.2–7.5 NAV and coverage. It runs on the **real** canonical data and compares against the reference functions. Disagreements are findings, not test edits.

## E. End-to-end acceptance (spec `<final_instruction>`, phase 3)

| ID | Check |
|---|---|
| E-01 | HDFC Bank valued by the full RI path from cited data, with no synthetic or blank critical inputs |
| E-02 | HDFC Bank confirmed as a holding of one actual Direct Plan Growth scheme **from that scheme's official disclosure** (cite the Source_ID) |
| E-03 | That fund's Fair NAV (M1 and M2) computed, reconciled to reported net assets, with the coverage caption |
| E-04 | Market-price shock, fair-value bias and absolute price applied to HDFC Bank move only the expected outputs (W-10 on real data) |

## H. Historical validation

Run only where point-in-time data exists (`raw_financials.Known_As_Of`). Otherwise every H test is reported `NOT RUN` with the reason. It must report look-ahead and survivorship handling, sample size and forecast errors (spec `<historical_model_validation>`).
