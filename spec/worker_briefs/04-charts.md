# Brief 04-charts: Charts and peer comparisons

**Launch:** `claude --worktree 04-charts --model sonnet --effort medium "Read CLAUDE.md and spec/worker_briefs/04-charts.md, then execute the brief."`

## Mission

Build the editable peer universe and peer statistics (contract §9), and every native Excel chart the spec requires. Each chart is bound to live tables and formula outputs and carries full metadata. Where data is missing or a metric is not meaningful, show an honest notice instead of a chart.

## You own

`src/peers/**`, `src/charts/**`, `tests/peers/**`, `tests/charts/**`, `data/canonical/peer_membership.csv`, `data/canonical/peer_metrics.csv`, and the PEER_GROUPS sheet, plus every chart (D-017).

## Read first

`spec/financial_model_contract.md` §9 → spec `<chart_interpretation_and_quality>`, `<company_metrics_and_visualisations>`, `<peer_comparison>`, `<sector_analysis_and_charts>` → `spec/workbook_interface.md` §4 → `src/charts/spec.py`, `src/peers/peer_table.py` → `tests/contract/test_peers_contract.py`.

## Work

1. `peer_statistic` must pass `python -m pytest tests/contract/test_peers_contract.py --strict-impl`.
2. **Peer membership** (`peer_membership.csv`): seed from `data/reference/peer_groups_seed.csv`. Every member needs an `Inclusion_Rationale` (business model, size, asset quality, funding, profitability) and an `As_Of_Date`. Members must be in the registry: ask 01-data to add any missing ones. Propose PG_INSURANCE members with rationale.
3. **PEER_GROUPS sheet**:
   * `tbl_PeerMembership`, with `Included` editable (blue);
   * `tbl_PeerMetrics`, where P/E, P/B and P/ABV are **formulas** over `tbl_MarketPrices` and `tbl_RawFinancials` at `in_Price_Date`. Only metrics that cannot be derived go into `peer_metrics.csv`, labelled third-party;
   * the `Value_If_Valid` helper column;
   * `tbl_PeerSummary` with Median / N_Valid / N_Excluded / Min / Max per (group, metric, excluded subject). It is blank, not 0, when N_Valid = 0.
   Bank EV multiples are `Is_Meaningful = FALSE`.
4. **Chart catalogue** (`src/charts/catalogue.py`): one `ChartSpec` per spec chart. That covers G001–G007, V001–V012, B001–B009, the six peer charts, the six sector-allocation charts, the three concentration charts and the six NAV charts. Implement `validate_chart_spec`: every metadata field present; NM specs carry no series.
5. **Renderer** (`render_charts`). For every reserved zone (`ctx.chart_zones`), find its spec and decide:
   * enough observations → a native chart (line/column/bar/scatter/doughnut; never 3D) with title, axis units, legend and a source/date note in the cell below. Forecast series are visually separated (dashed or a separate series);
   * fewer than `min_observations` → a visible notice: "Data unavailable – n = k – see MISSING_DATA";
   * V001 (historical price vs historical fair value) → render only if point-in-time valuations exist. Otherwise render the V002-style current comparison with the limitation stated (spec `<historical_fair_value_chart_rule>`);
   * an NM metric → the notice with its reason.
   A zone with no spec is a build error, not a blank area.
6. **Tests** in `tests/charts/`: every catalogue spec validates; every zone reserved in a `--test-build` gets a chart or a notice; chart XML series reference cell ranges (W-13 pre-check).

## Rules

* Charts read only interface tables and named outputs (`spec/workbook_interface.md` §2).
* Use one consistent restrained style. Colour never carries meaning without a text label.
* Never fabricate a series to fill a chart (spec `<multiple_validity>`).

## Done when

- [ ] Peer contract tests pass under `--strict-impl`; `tests/peers` and `tests/charts` pass
- [ ] `--test-build --only 04-charts` and the integrated test build render every zone
- [ ] Ownership check clean
