# Brief 02-valuation: Bank and insurance valuation

**Launch:** `claude --worktree 02-valuation --model opus --effort xhigh "Read CLAUDE.md and spec/worker_briefs/02-valuation.md, then execute the brief."`

## Mission

Phase 2: one **complete, validated HDFC Bank valuation path**. That means historicals, driver forecasts, Residual Income, DDM, justified P/B, peer-relative value, sensitivity, scenario cases and expected return, with key chart zones. Then replicate the template to the other five banks, and build the Max Financial insurance SOTP (phase 4). Every number must trace to a source or to a documented assumption.

## You own

`src/valuations/**`, `tests/valuations/**`, `data/canonical/assumptions.csv`, `reports/valuation/**`, and the sheets VAL_* (the seven named ones plus template-generated `VAL_<NAME>` for later holdings), VALUATION_ASSUMPTIONS, VALUATION_OUTPUTS and HISTORICAL_METRICS.

## Read first

`spec/financial_model_contract.md` §2–§5, §8, §10 (your formulas) → `spec/workbook_interface.md` → `tests/contract/test_bank_valuation_contract.py`, `test_insurance_contract.py`, `test_returns_contract.py` (your acceptance numbers) → `src/valuations/*.py` (interfaces).

## Work

**Wave 1 scope (D-028):** items 1–5 for HDFC Bank only, on real data, until gate G1 passes (`spec/worker_briefs/00-main.md`). Peer-relative stays a cross-check with weight 0 (D-009) until 04-charts delivers peers in Wave 2.

1. **Reference functions.** Implement every stub in `src/valuations/`. `python -m pytest tests/contract/test_bank_valuation_contract.py tests/contract/test_insurance_contract.py tests/contract/test_returns_contract.py --strict-impl` must pass. Do not change the tests. If you think one is wrong, file a change request with your derivation.
2. **Bank sheet template.** Write one generator function, e.g. `build_bank_sheet(ctx, security_id, data)`, that lays out a VAL_* sheet:
   * header: IDs, business model, accounting basis, and the dates kept separate (contract §0.1: anchor date, latest results period end, price date, valuation date), price (green link), data-status summary;
   * the **equity bridge** A → V (§3.1a): reported BVPS at A captioned "as of A", reported interim EPS, forecast stub EPS, dividends, and estimated BVPS at V captioned *estimate*; plus the interim deviation flag and the freshness checks (§3.1b). Each feeds its `tbl_ValuationOutputs` column;
   * history block (≥10 FY and ≤20 quarters) with formulas over `tbl_RawFinancials`, feeding `tbl_HistoricalMetrics` with `Is_Forecast = FALSE`;
   * a driver input block per case (Bear/Base/Bull), in blue cells sourced from `assumptions.csv`; every driver row needs a `Rationale` and a source type;
   * projection (§3.6), RI (§3.2), DDM (§3.3), justified P/B (§3.4), peer-relative (§3.5, linking `tbl_PeerSummary`), blend (§3.8), roll-forward (§3.1);
   * TV share and flags, a sensitivity grid r × g / r × ROE_T where cells with g ≥ r show `n/a (g ≥ r)`, and expected return by XIRR (§8) with explicit `Exit_PB`;
   * EV/EBITDA and EV/Revenue cells reading `Not Meaningful` with the reason (spec `<multiple_validity>`);
   * named outputs `out_<SID>_FV_Base`, `_FV_Bear`, `_FV_Bull`, `_TV_Share`;
   * chart zones (`ctx.reserve_chart_zone`) for G001–G007, V002–V012 and B001–B009, each naming its chart ID.
3. **VALUATION_OUTPUTS.** One row per registry security. Rows for securities with a model link to that sheet's `out_*` names. Every other security gets `UNVALUED` with blank FVs (R009), never 0. **VALUATION_ASSUMPTIONS** renders `tbl_Assumptions`.
4. **Develop on fixtures first.** `python build/generate_workbook.py --test-build --only 02-valuation` puts synthetic security S90001 on VAL_HDFC_BANK with stubbed peers. Recalculate it (`build/recalc.py`) and write `tests/valuations/test_sheet_matches_reference.py`, which checks that every `out_*` value equals your Python reference to 1e-9. When 01-data's real data lands (merge the integration branch), switch HDFC Bank to real inputs.
5. **Assumptions are evidence-led** (spec `<persona>`). Base drivers come from reported history and cited management guidance. Bear and Bull are full alternative driver sets (D-008). ERP, β and exit P/B are user assumptions with written reasoning in `assumptions.csv` and a `MODEL_GOVERNANCE` change request. Never invent consensus or scenario probabilities.
6. **Wave 2, only after gate G1 (D-028).** **Replicate** the template to Federal, AU SFB, Indian Bank, ICICI and Kotak with their own data and drivers. **Max Financial**: SOTP (§4) on VAL_MAX_FINANCIAL, using Method A or B per case, never both. Stake %, EV and VNB come from filings via 01-data.
7. **`reports/valuation/<company>.md`**: key drivers, the sensitivity of the value to them, method limitations, data gaps.

## Rules

* R004: a bank's primary method is RI. Calling `validate_method_for_business_model` is mandatory in the sheet builder.
* Formulas come only from the whitelist. Import cross-table links from `src/common/link_patterns.py`. A forecast EPS must never be labelled consensus (`MetricKind.MODELLED`).
* A biased or overridden value is never labelled as unmodified model output.

## Done when

- [ ] `python tools/check_module_contract.py 02-valuation --manifest build/out/manifest.json --run-tests` prints no REJECT, and `src/valuations/MODULE.md` is filled in
- [ ] The contract tests above pass under `--strict-impl`
- [ ] HDFC Bank: full path on real data. Excel equals Python for every `out_*`. TV share and flags shown. Sensitivity grid present
- [ ] `tbl_ValuationOutputs` covers every registry security, with unvalued ones visible
- [ ] Every assumption row has a rationale and source type; no blank critical input is hidden
- [ ] `--test-build --only 02-valuation` and the production build both pass; ownership check clean

Hand-off to 03-nav happens through `tbl_ValuationOutputs` only.
