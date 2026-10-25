# Data provenance audit

**Status: NOT RUN** (2026-10-25). 01-data's canonical data (`source_log.csv`, `source_manifest.csv`, `data/raw/`) is not merged into the integration branch, and no production build exists. No row has been sampled or checked.

## Method (to be executed on the first production build)

1. **Automated trace (PROV-01):** every non-blank `*Source_ID` in every canonical CSV exists in `source_log`. Every `source_log.Source_Doc_ID` exists in `source_manifest`. Every log row has a URL or file path, a page or table, and a unit (`tests/independent/test_I_real_data.py`).
2. **Hash check (PROV-02):** every manifest row with a `Local_Path` is hashed (SHA256) and compared. A row without a local file must have a URL.
3. **Sampled manual audit (PROV-03):** at least 10% of `source_log` rows, stratified by `Entity_ID` × `Metric` (at least one row per stratum; the HDFC Bank and fund-holdings strata first, for G1). The sample is drawn with a recorded seed. For each sampled row, open the cited document and page, then confirm:
   * value;
   * unit, including lakh → crore;
   * reporting period;
   * accounting basis;
   * that the canonical value equals the converted raw value.

   The full sample, the method and every mismatch are recorded here.
