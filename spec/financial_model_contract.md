# Financial Model Contract

Status: **v1.1, frozen for the first worker wave.** v1.1 (2026-10-25, pre-launch review) adds the separate dates and the equity bridge (§0, §3.1), a single Target Purchase Price (§6), the shock precedence rules (§6.1–6.2) and the three data-quality measures (§7.5). See D-023…D-028. Source requirement: `spec/source/Indian_Equity_Valuation_and_MF_NAV_Model_v3.xml` (spec v3.0). Requirement IDs such as `R004` refer to that file's `<non_negotiable_rules>`. Decision IDs such as `D-004` refer to `spec/decisions.md`.

This document is the single definition of every quantity that crosses a module boundary. If a worker needs a definition that is missing here, they file a change request (`spec/change_requests/`). They do not invent a local definition.

Every formula below exists twice:

1. As a **Python reference function** in the owning module (listed in each section). This is the executable definition, tested against the hand-computed cases in `spec/test_plan.md`.
2. As an **Excel formula** emitted by the same module's sheet builder. The QA harness recalculates the workbook in LibreOffice and checks that the Excel result equals the Python reference result for the same inputs (`spec/test_plan.md` §W).

---

## 0. Conventions (apply everywhere)

| Topic | Rule |
|---|---|
| Percentages | Stored as decimals: 15% is `0.15`. Displayed with a percent format. A column ending in `_Pct` always holds a decimal. |
| Aggregate money | **INR crore** (`INR_Cr`), 1 crore = 10,000,000 INR. Column suffix `_INR_Cr`. |
| Per-share and per-unit values | **INR** (absolute rupees), suffix `_INR`. Local-currency prices use suffix `_LCY` and carry a `Currency` column. |
| Quantities | Absolute share or unit counts. Never in lakh or crore. |
| Unit conversion | `Market_Value_INR_Cr = Quantity × Price_INR / 1e7`. Source values in lakh are converted with `/100` to crore at import. The raw value and raw unit are preserved (`spec/data_schema.md`). |
| Dates | ISO `YYYY-MM-DD`. Every value that depends on a date carries its own date column. The five model dates are never merged (table below). |
| Fiscal periods | Indian fiscal year: `FY2026` = 2025-04-01 to 2026-03-31. Quarters: `Q1FY2027` ends 2026-06-30. Labels are produced by `src/common/units.py::fiscal_label`. |
| Year fractions | `τ = days / 365.25` for discounting and roll-forward. XIRR uses Excel's `days / 365` convention. Both are named explicitly in every formula below. |
| Accounting basis | `Standalone` or `Consolidated`, recorded per observation. One valuation uses one basis. Mixing is a validation FAIL. |
| Missing values | Blank / `None`, never `0`. Status text explains why (R009, missing-data rule). |
| Identifiers | `Entity_ID` = issuer (`C001`…). `Security_ID` = instrument / share class (`S00001`…). `ISIN` is the matching key for imports. `Fund_ID` = scheme (`MF001`…). `Plan_ID` = scheme + plan + option (`MF001-DIR-GR`). Names are never join keys (D-010). |

### 0.1 The five model dates (D-025)

| Date | Meaning | Where it is held |
|---|---|---|
| Financials date | `Anchor_Date` (A): period end of the reported balance sheet behind BV_0. `Latest_Results_Period_End` (R): end of the latest reported earnings period, interim included. | `tbl_ValuationOutputs`, per security |
| `Price_Date` | Market close used for every compared price: `in_Price_Date` | `tbl_MarketPrices`, `tbl_ValuationOutputs`, `tbl_NAVSummary` |
| `Portfolio_Date` | Date of the fund's disclosed holdings snapshot | `tbl_Holdings_*`, `tbl_NAVSummary` |
| `NAV_Date` | Date of the Official NAV used | `tbl_OfficialNAV`, `tbl_NAVSummary` |
| `Valuation_Date` | `in_Valuation_Date`, the date every fair value is stated at | `tbl_ValuationOutputs`, `tbl_NAVSummary` |

Labelling rule: a value is captioned with the date it is **reported** at. A reported number is never relabelled as current. Anything carried from an earlier date to `Valuation_Date` is captioned *estimate* and shows its bridge (§3.1a).

---

## 1. The five distinct value outputs (mandatory display rule)

These five outputs must never share a label, a cell, or a chart series without a legend that distinguishes them. The label strings are fixed in `src/common/enums.py::OutputLabel`.

| Output | Definition | Section |
|---|---|---|
| **Official NAV** | Published NAV for the exact `Plan_ID` and NAV date, from AMFI or the AMC. An imported observation. Never computed or overwritten. | §7.1 |
| **Modelled Intrinsic Value per Unit** (a.k.a. Estimated Fair NAV) | Official NAV adjusted by the security fair values of the disclosed portfolio snapshot. Produced for the Base, Bear and Bull cases and for the Selected scenario. Always labelled *estimate*. | §7.2–7.3 |
| **Scenario Market NAV** | The disclosed portfolio snapshot marked at the *Selected Scenario Market Prices*. Not a forecast. | §7.4 |
| **Hypothetical Rebalanced Portfolio Value** | A separate user-built basket. Never attached to an existing fund's NAV (R011). | §7.6 |
| **Target Purchase Price** | Per security: `Selected_Scenario_Fair_Value × (1 − Required_Margin_of_Safety_Pct)`. One definition (D-023). | §6 |

---

## 2. Cost of equity and discounting

Owner: `02-valuation` · Reference: `src/valuations/discounting.py`

```
r_e = Rf + β × ERP                     (CAPM; each input carries a source or is a flagged User assumption)
DF(τ) = (1 + r_e)^(−τ)                 τ in years, days/365.25, end-of-period discounting
```

* `Rf` is the 10-year G-sec yield as of the valuation date (RBI/CCIL source). `ERP` and `β` are User assumptions unless sourced.
* Cash flows of fiscal year *t* are dated at that fiscal year end.
* Rates are annual effective rates, not continuously compounded.

---

## 3. Bank valuation (R004)

Owner: `02-valuation`. Primary method: Residual Income. Secondary methods: DDM, justified P/B, peer-relative. A conventional FCFF/WACC DCF is **forbidden** as a bank's primary method. `validate_method_for_business_model` raises if it is attempted.

### 3.1 Valuation anchor and roll-forward (D-007, D-025)

All bank and insurer models first value the equity **per share at an anchor date `A`**: the period end of the latest **reported fiscal-year balance sheet** (audited annual accounts, the same accounting basis throughout). BV_0 is that reported book value. It is historical information, captioned "as of A", and never relabelled as current. Forecast years `t = 1 … N` are the fiscal years after A.

The value is then rolled forward to the common valuation date `V`:

```
V_V = V_A × (1 + r_e)^τ(A,V) − Σ_{d ∈ (A, V]} DPS_d × (1 + r_e)^τ(d,V)
```

`d` runs over dividends whose **ex-date** falls after `A` and on or before `V`. These dividends are included in `BV_A`, because Indian GAAP and Ind AS do not deduct a proposed dividend until it is approved, and they have left the company by `V`. Reference: `rollforward.roll_forward_value`.

The roll-forward is not an extra assumption. Under the same forecasts it is the value at V that the model expects: value accretes at `r_e` and dividends paid leave it. What it does *not* do is show the earnings and equity it implies, or absorb interim results reported after A. §3.1a makes both explicit.

### 3.1a Equity bridge A → V (D-025)

Reference: `rollforward.equity_bridge`. Shown on every VAL_* sheet as its own block, one line per component, each tagged *Reported* or *Forecast*:

```
  BV_A                                     Reported   book value per diluted share at A
+ EPS_reported(A, R]                       Reported   Σ EPS of discrete interim periods ending in (A, V];
                                                      R = latest such period end, or A if none
+ EPS_forecast(R, V]                       Forecast   forecast EPS accrued by calendar day:
                                                      Σ_t EPS_t × days((R,V] ∩ FY_t) / days(FY_t)
− Σ DPS_d, ex-date d in (A, V]             Reported
= BV_V_est                                 Estimate   "Estimated book value per share at V"
```

* **Interim check.** When interim periods have been reported (R > A): `Interim_EPS_Deviation_Pct = EPS_reported(A,R] / EPS_forecast(A,R] − 1`, the forecast accrued the same way. `|deviation| > in_Interim_EPS_Dev_Warn` (default 0.15) sets `Forecast_Update_Flag = WARNING`: the year-1 drivers disagree with reported results and must be reviewed. Interim results never overwrite the forecast silently.
* Any multiple stated at V (market P/B, implied P/B = `V_V / BV_V_est`) uses `BV_V_est` and is captioned *estimate*. A multiple on reported book value says "on BV at A".
* If V is after the last forecast year end, `equity_bridge` raises `ValuationError`. The model has no forecast covering V.
* Moving the anchor to an interim balance sheet (banks publish half-yearly statements of assets and liabilities) needs stub-period RI discounting. That is a change request, not a worker decision.

### 3.1b Financials freshness

```
Financials_Age_Days = V − R          STALE when > in_Financials_Stale_Days (default 135)
Anchor_Age_Days     = V − A          FAIL  when > in_Anchor_Max_Age_Days  (default 425)
Freshness_Status    = FAIL if the anchor check fails, else STALE if the financials check fails, else PASS
```

The defaults follow SEBI LODR Regulation 33 deadlines: quarterly results within 45 days of quarter end, and annual audited results within 60 days of year end. Past either threshold, a newer filing should exist and 01-data should look for it. `Freshness_Status` travels with the security into `tbl_ValuationOutputs` and from there into the fund freshness measure (§7.5c).

### 3.2 Residual Income (primary)

Reference: `bank_ri.residual_income_value`

Clean surplus, per share, fiscal years `t = 1 … N` after the anchor:

```
BV_t  = BV_{t−1} + EPS_t − DPS_t
RI_t  = EPS_t − r_e × BV_{t−1}                      (beginning-of-year book value)
PV_RI = Σ_{t=1..N} RI_t × (1 + r_e)^(−t)
RI_{N+1} = (ROE_T − r_e) × BV_N                     (ROE_T = sustainable terminal RoE)
TV_N  = RI_{N+1} / (r_e − g)                        requires g < r_e, else INVALID
PV_TV = TV_N × (1 + r_e)^(−N)
V_A   = BV_0 + PV_RI + PV_TV
Terminal_Value_Share = PV_TV / V_A
```

* `BV` is common shareholders' equity per diluted share, excluding minority interest and any preference or AT1 capital.
* In the forecast years, EPS is derived from the bank driver model (§3.6). RI never takes a typed-in EPS without a driver trail.
* If `ROE_T = r_e`, then `PV_TV = 0`. That is valid: the stock converges to P/B = 1 after year N.
* `Terminal_Value_Share > in_TV_Share_Warn` (GLOBAL_ASSUMPTIONS) sets `Terminal_Flag = WARNING`.

### 3.3 Dividend Discount Model (secondary)

Reference: `ddm.dividend_discount_value`

```
PV_D  = Σ_{t=1..N} DPS_t × (1 + r_e)^(−t)
DPS_{N+1} = ROE_T × BV_N × Payout_T
TV_N  = DPS_{N+1} / (r_e − g)                       requires g < r_e
V_A   = PV_D + TV_N × (1 + r_e)^(−N)
```

Consistency requirement, tested in T-BNK-01: with constant ROE, constant payout and `g = ROE × (1 − payout)`, the RI value, the DDM value and the justified P/B × BV must agree to 1e-9.

### 3.4 Justified P/B (secondary)

Reference: `justified_pb.justified_pb`

```
P/B_justified = (ROE_T − g) / (r_e − g)              requires g < r_e
V_A = P/B_justified × BV_0
```

### 3.5 Peer-relative (secondary)

Reference: `peer_relative.peer_relative_value`. Peer statistics come from `04-charts` via `tbl_PeerSummary` (§9).

```
V = Peer_Median_Multiple × Company_Metric
    P/B  → BVPS          P/ABV → ABVPS          P/E → EPS (state trailing or forward, and its period)
```

* The median uses only peers with `Included = TRUE` **and** a valid numeric multiple.
* `N_Valid < 3` sets `Peer_Flag = WARNING`. `N_Valid = 0` makes the output blank and `UNVALUED`, never 0.
* For banks, EV/EBITDA and EV/Revenue are `Not Meaningful` (`NM`). They are never computed.

### 3.6 Bank driver model

Reference: `bank_drivers.project_bank`. Drivers per forecast year: advance growth, the ratio of interest-earning assets to advances, NIM, non-interest income growth, opex growth, credit cost (as a % of average advances), tax rate and payout ratio. Deposit growth, loan yield and cost of deposits are shown as **consistency displays** next to NIM (B005, B006). They do not drive the P&L in v1. Making them drivers needs a change request that defines the funding identity.

All amounts are in INR crore except shares (absolute count) and per-share values (INR):

```
Adv_t          = Adv_{t−1} × (1 + Advance_Growth_t)
IEA_t          = Adv_t × IEA_to_Advances_t                 (IEA_0 = Adv_0 × base ratio)
NII_t          = NIM_t × (IEA_{t−1} + IEA_t) / 2
NonII_t        = NonII_{t−1} × (1 + NonII_Growth_t)
Opex_t         = Opex_{t−1} × (1 + Opex_Growth_t)
PPOP_t         = NII_t + NonII_t − Opex_t
Provisions_t   = Credit_Cost_t × (Adv_{t−1} + Adv_t) / 2
PAT_t          = (PPOP_t − Provisions_t) × (1 − Tax_t)
EPS_t          = PAT_t × 1e7 / Diluted_Shares_t
DPS_t          = EPS_t × Payout_t
Equity_t       = Equity_{t−1} + PAT_t − DPS_t × Diluted_Shares_t / 1e7   (dividend of year t deducted in year t)
BVPS_t         = Equity_t × 1e7 / Diluted_Shares_t
ROE_t          = PAT_t / ((Equity_{t−1} + Equity_t) / 2)
```

The dividend timing simplification (year *t*'s dividend leaves equity in year *t*) matches the clean-surplus identity of §3.2, so `BVPS_t` here equals `BV_t` there when shares are constant.

Capital retention check: `BV_t` must agree with `(Equity_t / Shares_t)` from the driver balance sheet to within 0.5%. A larger gap means the clean-surplus link is broken and the check FAILs.

### 3.7 Scenario cases (D-008)

`Bear`, `Base` and `Bull` are three complete driver sets. Each case's fair value comes from re-running §3.2–3.6 on that set. A case value must never be `Base × (1 ± k)`.

### 3.8 Blend into Base Fair Value (D-009)

```
FV_case = Σ_m w_m × V_m,case          Σ w_m = 1 (validated), w_m ≥ 0
```

Default weights: primary method = 1, all others = 0, with the others shown as cross-checks. Weights are User assumptions recorded in MODEL_GOVERNANCE.

---

## 4. Insurance holding company: Max Financial Services (C007)

Owner: `02-valuation` · Reference: `insurance_sotp.sotp_value_per_share`

```
Appraisal_Value = EV + VNB × VNB_Multiple                (Method A)
             or = EV × Target_P/EV                        (Method B)
Stake_Value     = Stake_Pct × Appraisal_Value × (1 − Holdco_Discount_Pct)
Equity_Value    = Stake_Value + Parent_Cash − Parent_Debt + Other_Parent_Net_Assets
Value_per_Share = Equity_Value × 1e7 / Diluted_Parent_Shares      (INR crore → INR)
```

* Exactly one of Method A and Method B per case. Supplying both raises `DoubleCountingError`, because a P/EV multiple already prices future new business.
* `Stake_Pct` is the economic interest in Axis Max Life on the anchor date, from a filing. Never hard-code it.
* Then roll forward to `V` (§3.1).

---

## 5. Non-financial companies (phase 5 placeholder)

Owner: `02-valuation`, in a later wave. FCFF DCF with WACC, FCFE where appropriate, and EV multiples with an explicit equity-to-EV bridge. The interface is the same as banks: the module emits `FV_Base`, `FV_Bear` and `FV_Bull` per Security_ID into `tbl_ValuationOutputs`, plus `Terminal_Value_Share` and the method. Until a model exists, a holding is `UNVALUED` (R009).

---

## 6. Per-security price and fair-value controls (R007, R008)

Owner: `03-nav` · Reference: `src/scenarios/pricing.py::resolve_controls` · Sheet: `SCENARIO_ANALYSIS`, table `tbl_PriceControls`, one row per Security_ID.

Inputs. Blue cells for inputs; purple for overrides.

| Input | Default | Validation |
|---|---|---|
| `Original_Market_Price` | linked to `tbl_MarketPrices` | read-only link; the scenario engine never writes it (R008) |
| `Model_FV_Base` / `Model_FV_Bear` / `Model_FV_Bull` | linked to `tbl_ValuationOutputs` | read-only link |
| `Market_Price_Scenario_Mode` | `Original Market Price` | list: `Original Market Price`, `Market Price Shock`, `Absolute Scenario Market Price` |
| `Market_Price_Shock_Pct` | 0 | decimal > −1 |
| `Absolute_Scenario_Price` | blank | > 0 or blank |
| `Fair_Value_Scenario_Mode` | `Model Base Fair Value` | list: `Model Base Fair Value`, `Fundamental Assumption Scenario`, `Manual Fair-Value Bias` |
| `Fundamental_Case` | `in_Global_Case` | list: `Bear`, `Base`, `Bull` |
| `Fair_Value_Bias_Pct` | 0 | decimal > −1 |
| `Required_Margin_of_Safety_Pct` | `in_Default_MoS` | 0 ≤ x < 1 |

Global and sector shocks: `in_Global_Price_Shock_Pct` (GLOBAL_ASSUMPTIONS) and `tbl_SectorShocks[Sector_Price_Shock_Pct]`, both defaulting to 0 (D-006).

Outputs, each in a separate column:

```
Effective_Shock_Pct           = (1 + Global) × (1 + Sector) × (1 + Market_Price_Shock_Pct) − 1
Market_Price_After_Shock      = Original_Market_Price × (1 + Effective_Shock_Pct)
Selected_Scenario_Market_Price=
    Original Market Price           → Original_Market_Price
    Market Price Shock              → Market_Price_After_Shock
    Absolute Scenario Market Price  → Absolute_Scenario_Price      (blank → #N/A + Control_Status FAIL, D-014)
Fair_Value_After_Bias         = Model_FV_Base × (1 + Fair_Value_Bias_Pct)
Fundamental_Case_FV           = Model_FV_{Fundamental_Case}
Selected_Scenario_Fair_Value  =
    Model Base Fair Value           → Model_FV_Base
    Fundamental Assumption Scenario → Fundamental_Case_FV
    Manual Fair-Value Bias          → Fair_Value_After_Bias
Implied_Upside_To_Fair_Value  = Selected_Scenario_Fair_Value / Selected_Scenario_Market_Price − 1
Fair_Value_Gap                = Fair_Value_After_Bias / Original_Market_Price − 1
Target_Purchase_Price         = Selected_Scenario_Fair_Value × (1 − Required_Margin_of_Safety_Pct)      (D-023)
FV_Label                      = "Model output (unmodified)" if mode = Model Base Fair Value
                                "Model output – fundamental case <case>"  if Fundamental
                                "MANUALLY BIASED fair value (<bias>%)"     if Manual
```

Fair-value quantities stay distinct, in separate columns: `Model_FV_Base` (the model output, read-only), `Fundamental_Case_FV`, `Fair_Value_After_Bias` (the adjusted fair value) and `Selected_Scenario_Fair_Value` (the one the selector picks). `Target_Purchase_Price` has one definition and it reads only `Selected_Scenario_Fair_Value`. At default controls it equals `Model_FV_Base × (1 − MoS)`, which is the spec's first formula. A market-price shock never changes it.

### 6.1 How price shocks combine (D-006, D-024)

```
P_scenario = P_0 × (1 + s_global) × (1 + s_sector) × (1 + s_security)        P_0 = Original_Market_Price
```

Each shock is a decimal (−10% = −0.10). The rules:

1. **From the original price.** `P_0` is always `Original_Market_Price`. No scenario price is ever computed from another scenario price.
2. **Once.** The three shock inputs are read in exactly one place, `tbl_PriceControls[Effective_Shock_Pct]`. Holdings, NAV Method 3, rebalancing and charts read `Selected_Scenario_Market_Price` and never apply a shock again. QA scans for this (W-17).
3. **The mode decides, and precedence is fixed.** `Market_Price_Scenario_Mode` alone chooses the price:

| Mode | Selected_Scenario_Market_Price | Inputs ignored |
|---|---|---|
| `Original Market Price` | `P_0` | every shock and any absolute price |
| `Market Price Shock` | `P_0 × (1 + Effective_Shock_Pct)` | any absolute price |
| `Absolute Scenario Market Price` | `Absolute_Scenario_Price`, overriding every percentage shock. Blank → `#N/A` and FAIL (D-014) | every shock |

4. **Foreign securities.** The shock applies to the price in the trading currency. FX is unchanged, so the INR price moves by the same factor.

### 6.2 Ignored inputs are disclosed

`Control_Warning` lists every input that is set but has no effect under the current modes, joined by `"; "` in this order:

| Condition | Text |
|---|---|
| any of the three shocks ≠ 0 and the mode is not `Market Price Shock` | `Price shocks set but ignored (mode: <market mode>)` |
| `Absolute_Scenario_Price` not blank and the mode is not `Absolute Scenario Market Price` | `Absolute price set but ignored (mode: <market mode>)` |
| `Fair_Value_Bias_Pct` ≠ 0 and the FV mode is not `Manual Fair-Value Bias` | `Fair-value bias set but ignored (mode: <fair-value mode>)` |

Blank means nothing is ignored. A warning never changes `Control_Status`.

### 6.3 Other rules

* No control changes another control's output. The spec's worked example (750 / 500 / −10% / −10% / 595) is test T-PRC-01…03.
* Reset (spec `<reset_controls>`): a `Reset` column computes the default for every input. The documented reset is to copy the `Reset_*` values over the inputs, or regenerate the workbook. Sheet `VALIDATION_CHECKS` shows `Controls_At_Default = TRUE/FALSE`.
* An unvalued security has a blank `Model_FV_*`. Its fair-value outputs, `Target_Purchase_Price` included, are blank and `Control_Status = UNVALUED`. Market-price outputs still work.

---

## 7. Mutual-fund NAV engine (R006, R009, R011)

Owner: `03-nav` · Reference: `src/fund_nav/`

### 7.0 Holding line classification

Every holdings line has an `Asset_Class` (§ data_schema) and a `Valuation_Coverage_Status`:

| Status | Applies to | Fair value used | Counts as covered |
|---|---|---|---|
| `MODEL_VALUED` | equity with a valid `tbl_ValuationOutputs` row for the case | model FV | yes |
| `CARRYING_VALUE` | cash, TREPS/repo, receivables, payables, accrued items, net current assets | disclosed value (adjustment 0 by construction) | yes |
| `MARKET_PASS_THROUGH` | debt, money-market, derivatives, REIT/InvIT, foreign ETFs without a model | market value (adjustment 0) | yes, reported separately |
| `UNVALUED` | equity without a valid model output, or any POSITION line that is not `MATCHED` (§7.5a) | **market price is used, adjustment 0**, flagged (D-015) | **no** |

### 7.1 Official NAV

Imported from `tbl_OfficialNAV` keyed by (`Plan_ID`, `NAV_Date`). The NAV date used is `in_Price_Date`. If no NAV exists for that date, the latest earlier NAV is used and `NAV_Date_Warning` shows the gap in days.

### 7.2 Method 1: Weighted Valuation Adjustment

Reference: `methods.weighted_adjustment_nav`

```
w_i        = disclosed weight of line i as a fraction of total scheme net assets (decimal)
Adj_i      = w_i × (FV_i / P_i − 1)          FV_i, P_i in the same currency (FX cancels)
           = 0 for CARRYING_VALUE, MARKET_PASS_THROUGH and UNVALUED lines
Fair_NAV_M1 = Official_NAV × (1 + Σ_i Adj_i)
```

`P_i` is `Original_Market_Price` at `in_Price_Date`. The disclosed weights are as of `Portfolio_Date`. Drift between those two dates is a stated limitation, measured by §7.7 diagnostic D2.

### 7.3 Method 2: Quantity-Based Fair NAV (D-004)

Reference: `methods.quantity_based_nav`

A scheme's portfolio belongs to all of its plans (Direct and Regular, Growth and IDCW). Plan NAVs differ only through plan-level expense accruals and distributions. Scheme quantities divided by one plan's units would therefore be wrong. The contract uses the ratio form:

```
MV_i^mkt   = q_i × P_i^INR / 1e7                      INR crore
MV_i^fair  = q_i × FV_i^INR / 1e7                     (FV_i := P_i for non-MODEL_VALUED lines)
ONA        = Σ CARRYING_VALUE and MARKET_PASS_THROUGH line values  (assets +, liabilities −)
NA_mkt     = Σ_equity MV_i^mkt + ONA
NA_fair    = Σ_equity MV_i^fair + ONA
Fair_NAV_M2(plan) = Official_NAV(plan) × NA_fair / NA_mkt
```

* The spec's form, `(Σ q·FV + OA − L) / Units`, is identical when `Units = NA_mkt × 1e7 / Official_NAV`. If plan-level units and plan net assets are disclosed, `units_based_nav` is available as a secondary output and must agree to the reconciliation tolerance.
* **Reconciliation** at `Portfolio_Date`: `Σ disclosed Market_Value_INR_Cr + ONA` vs `Reported_Scheme_Net_Assets_INR_Cr` for the same date. If `|gap| / reported > in_Recon_Tolerance_Pct` (default 0.005), the result is FAIL.
* No line may be counted twice. A line is either a security position or an ONA component.

### 7.4 Method 3: Scenario Market NAV

Reference: `methods.scenario_market_nav`

```
NA_scen  = Σ_equity q_i × Selected_Scenario_Market_Price_i^INR / 1e7 + ONA
Scenario_Market_NAV(plan) = Official_NAV(plan) × NA_scen / NA_mkt
```

With every control at its default, `Scenario_Market_NAV = Official_NAV` exactly. Test T-NAV-03 checks this.

### 7.5 Data quality: three separate measures (R009, D-026)

A holding can be imported and still have no valid fair value, and a valued holding can rest on old financials. These are different problems, so the model reports three measures. Each has its own status, and they are **never combined into one score**. All three appear per plan in `tbl_NAVSummary` and on EXECUTIVE_DASHBOARD.

#### 7.5a (1) Holdings coverage: is the official portfolio imported and markable?

Reference: `coverage.holdings_coverage`, `coverage.match_status`

```
Holdings_Match_Status (POSITION lines only)
    MATCHED     registry Security_ID found for the disclosed ISIN, and a price at in_Price_Date
    UNMATCHED   no registry Security_ID
    NO_PRICE    Security_ID known, no price at in_Price_Date
Holdings_Value_Coverage_Pct = Σ disclosed line values (positions + ONA) / Reported_Scheme_Net_Assets_INR_Cr
Holdings_Match_Pct          = Σ w_i (MATCHED) / Σ w_i (POSITION lines)
Holdings_Coverage_Status    = PASS if Recon_Status = PASS (§7.3) and Holdings_Match_Pct = 1, else FAIL
```

A line that is not `MATCHED` is never `MODEL_VALUED`. In the workbook its price lookup stays `#N/A` (WI-6), so Method 2 and Method 3 show `#N/A` until 01-data resolves it. The unmatched lines are listed by `Holding_Line_ID` on MF_COVERAGE_AUDIT.

#### 7.5b (2) Valuation coverage: how much has a valid fair value?

Reference: `coverage.coverage_summary`

```
Valuation_Coverage_Total_Pct  = Σ w_i over lines whose status ≠ UNVALUED          (denominator: total scheme net assets)
Valuation_Coverage_Equity_Pct = Σ w_i (MODEL_VALUED) / Σ w_i (equity lines)
Unvalued_Weight_Pct  = Σ w_i (UNVALUED)
Unvalued_Count, Unvalued_Value_INR_Cr
```

Thresholds from GLOBAL_ASSUMPTIONS: `Valuation_Coverage_Equity_Pct < in_Coverage_Warn` is WARNING, and `< in_Coverage_Fail` is FAIL. Each Fair NAV output carries the caption `"Covers X% of equity; Y% of net assets unvalued (adjustment 0)"`, with X and Y to one decimal place (e.g. `Covers 83.3% of equity; 10.0% of net assets unvalued (adjustment 0)`). This caption is generated, not typed, and it must appear on EXECUTIVE_DASHBOARD.

#### 7.5c (3) Data freshness: how old is each input?

Reference: `coverage.freshness_summary`. Ages are in days to `in_Valuation_Date`; each date in §0.1 is shown separately.

```
Holdings_Age_Days        = Valuation_Date − Portfolio_Date               STALE when > in_Holdings_Stale_Days (45)
NAV_Date_Gap_Days        = Valuation_Date − NAV_Date                     STALE when > in_Price_Stale_Days (3)
Max_Financials_Age_Days  = max over MODEL_VALUED lines of (Valuation_Date − Financials_As_Of)
Stale_Valued_Weight_Pct  = Σ w_i over MODEL_VALUED lines with Financials_As_Of blank
                           or older than in_Financials_Stale_Days (135)     STALE when > 0
Freshness_Status         = STALE if any of the three checks is STALE, else PASS
```

`Financials_As_Of` is the issuer's `Latest_Results_Period_End` (§3.1a). A blank date counts as stale, never as fresh. Price freshness per security is D3 in §7.7 and `in_Price_Stale_Days` in `tbl_MarketPrices`.

### 7.6 Method 4: Hypothetical Rebalanced Portfolio (R011)

Reference: `rebalance.build_hypothetical_portfolio` · Sheet `PORTFOLIO_REBALANCING`

```
Effective_Weight_i = Sector_Weight_s × Constituent_Weight_i|s
Target_Value_i     = Capital_INR × Effective_Weight_i
Buy_Price_i        = user Assumed_Buy_Price_i, else Selected_Scenario_Market_Price_i
Quantity_i         = user Quantity_Override_i, else FLOOR(Target_Value_i / (Buy_Price_i × (1 + TC_Pct)))
Cost_i             = Quantity_i × Buy_Price_i
Fee_i              = Cost_i × TC_Pct
Cash_Remaining     = Capital_INR − Σ (Cost_i + Fee_i)          must be ≥ 0, else FAIL
HRPV_Market        = Σ Quantity_i × Selected_Scenario_Market_Price_i + Cash_Remaining
HRPV_Fair          = Σ Quantity_i × Selected_Scenario_Fair_Value_i + Cash_Remaining  (unvalued lines at market, flagged)
```

Custom-allocation validation (`custom_allocation.validate_allocation`):

* `Σ Sector_Weight + Explicit_Cash_or_Unallocated = 1` (±1e-6).
* `Σ Constituent_Weight|s = 1` within each sector that has a non-zero weight.
* A Security_ID appears at most once.
* Weights are ≥ 0.

Custom inputs live only in `tbl_CustomAllocation`. No formula in an actual-holdings table may reference that table. QA checks this by scanning formulas (T-CUS-03).

### 7.7 Diagnostics and outputs

| Output | Definition |
|---|---|
| `Diff_vs_Official_INR` | `Fair_NAV − Official_NAV` (per unit) |
| `Diff_vs_Official_Pct` | `Fair_NAV / Official_NAV − 1` |
| Sector contribution | `Σ_{i∈s} Adj_i`. The sector contributions sum to `Σ Adj_i` exactly. |
| D1 Holdings age | See §7.5c `Holdings_Age_Days`. |
| D2 Method drift | `Fair_NAV_M1 − Fair_NAV_M2`. Non-zero means the disclosed weights have drifted from `q × P / NA_mkt`. |
| D3 Price-date mix | The count of securities whose `Price_Date ≠ in_Price_Date`. Must be 0, or each such row is listed. |
| D4 FX timestamp | For foreign lines: local close timestamp, FX rate date and the gap from `in_Price_Date`. |

### 7.8 Overlap (spec `<overlap_analysis>`)

Reference: `overlap.overlap_by_weight`

```
Overlap_Pct(A, B) = Σ_i min(w_i^A, w_i^B)          over Security_IDs held by both
Common_Count      = |{i : w_i^A > 0 and w_i^B > 0}|
```

### 7.9 Fund performance

Reference: `performance.py`. Inputs: a daily Official NAV series and a benchmark TRI series, both with source.

```
Return(h)      = NAV_end / NAV_start − 1 ;  CAGR(h) = (NAV_end/NAV_start)^(365/days) − 1
Vol_ann        = stdev(daily simple returns, sample) × √252
Max_Drawdown   = min_t (NAV_t / max_{s≤t} NAV_s − 1)
Downside_Dev   = √(mean(min(r_t − MAR_daily, 0)²)) × √252        MAR_daily = (1+MAR)^(1/252) − 1
Sharpe         = (CAGR − Rf) / Vol_ann ;  Sortino = (CAGR − MAR) / Downside_Dev
Rolling(h)     = series of Return(h) computed at each date with full h-history; report n
```

Expense ratios are already inside NAV. They are never deducted again.

---

## 8. Expected five-year return (spec `<expected_return_framework>`)

Owner: `02-valuation` · Reference: `expected_return.py`

```
Exit_Value_T (bank) = Exit_PB × BVPS_T          (Exit_PB is an explicit user assumption; no automatic convergence)
Cash flows: −Price_0 at V; +DPS_t at each assumed payment date; +Exit_Value_T at V + 5y
Annualised_TR = XIRR(cash flows, dates)          Excel XIRR convention, days/365
Reinvestment_Mode ∈ {"Dividends not reinvested (XIRR)", "Dividends reinvested at r_reinv"}
Prob_Weighted = Σ p_c × Annualised_TR_c         only if p_Bear, p_Base, p_Bull are all entered and Σp = 1 ± 1e-9
```

The probabilities default to blank, and the weighted output is blank until they are entered. The model never invents them. Summing EPS growth, dividend yield and re-rating as an approximate return is forbidden.

---

## 9. Peers

Owner: `04-charts` · Reference: `src/peers/peer_table.py` · Sheet `PEER_GROUPS`

* `tbl_PeerMembership` has columns `Peer_Group_ID`, `Security_ID`, `Included` (TRUE/FALSE), `Inclusion_Rationale` (required text) and `As_Of_Date`.
* `tbl_PeerMetrics` has one row per (Security_ID, Metric_ID) with `Value`, `Period`, `Price_Date`, `Source_ID` and `Is_Meaningful`.
* Helper column `Value_If_Valid = IF(AND(Included, Is_Meaningful, ISNUMBER(Value)), Value, "")`.
* `tbl_PeerSummary` has columns `Peer_Group_ID`, `Metric_ID`, `Median`, `N_Valid`, `N_Excluded` and `Min`/`Max`. `Median` uses `MEDIAN` over the helper column, so text is ignored. If `N_Valid = 0`, the result is blank, not 0.
* The subject company is excluded from its own peer median.

---

## 10. Terminal-value and sanity controls (spec `<terminal_value_controls>`)

Reference: `src/valuations/terminal.py`

| Check | Rule | Status |
|---|---|---|
| TV-1 | `g < r` for every Gordon terminal | FAIL, and the value is blank, not computed |
| TV-2 | `Terminal_Value_Share` shown for every method | — |
| TV-3 | `Terminal_Value_Share > in_TV_Share_Warn` | WARNING |
| TV-4 | Sensitivity grid: r_e ±100 bp × g ±100 bp (or × ROE_T ±200 bp for RI) | shown as heatmap V011 |
| TV-5 | Any grid cell with `g ≥ r` | shown as `n/a (g ≥ r)`, never a number |

---

## 11. Status vocabulary

`PASS`, `WARNING`, `FAIL`, `MISSING` and `STALE` are always written as text **next to** any colour (colour safety). Data statuses (spec `<data_statuses>`) are in `src/common/enums.py::DataStatus`. The additional status `SYNTHETIC_TEST_FIXTURE` is accepted only in a test build (D-013).
