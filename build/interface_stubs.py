"""Value-only stubs of cross-module interface tables for isolated worker builds.

`python build/generate_workbook.py --test-build --only 03-nav` builds 00-main and
03-nav for real. Every interface table that 03-nav consumes but does not build
(tbl_Registry, tbl_ValuationOutputs, ...) is stubbed here from the synthetic
fixtures, so 03-nav's formulas resolve and recalculate in LibreOffice without the
other workers' code.
"""
from __future__ import annotations

from src.common import schema as S
from src.common.rows import typed_value
from src.common.workbook import WorkbookContext

# (schema table, excel name, sheet, row filter) for every interface table.
INTERFACE_TABLES = [
    (S.SECURITY_REGISTRY, "tbl_Registry", "MASTER_SECURITY_REGISTRY", None),
    (S.MARKET_PRICES, "tbl_MarketPrices", "MARKET_PRICES", None),
    (S.RAW_FINANCIALS, "tbl_RawFinancials", "RAW_FINANCIAL_DATA", None),
    (S.VALUATION_OUTPUTS, "tbl_ValuationOutputs", "VALUATION_OUTPUTS", None),
    (S.HISTORICAL_METRICS, "tbl_HistoricalMetrics", "HISTORICAL_METRICS", None),
    (S.PEER_SUMMARY, "tbl_PeerSummary", "PEER_GROUPS", None),
    (S.SECTOR_SHOCKS, "tbl_SectorShocks", "SCENARIO_ANALYSIS", None),
    (S.PRICE_CONTROLS, "tbl_PriceControls", "SCENARIO_ANALYSIS", None),
    (S.FUND_HOLDINGS, "tbl_Holdings_MF001", "PPFAS_FLEXICAP_HOLDINGS", ("Fund_ID", "MF001")),
    (S.FUND_HOLDINGS, "tbl_Holdings_MF002", "HDFC_MIDCAP_HOLDINGS", ("Fund_ID", "MF002")),
    (S.FUND_PLANS, "tbl_FundPlans", "MF_NAV_CALCULATOR", None),
    (S.OFFICIAL_NAV, "tbl_OfficialNAV", "MF_NAV_CALCULATOR", None),
    (S.FUND_SCHEME_TOTALS, "tbl_SchemeTotals", "MF_NAV_CALCULATOR", None),
    (S.NAV_SUMMARY, "tbl_NAVSummary", "MF_NAV_CALCULATOR", None),
]


def add_stubs(ctx: WorkbookContext, data, built_workers: set[str]) -> list[str]:
    """Stub every interface table whose sheet owner was not built. Returns stubbed names."""
    stubbed = []
    next_row: dict[str, int] = {}
    for table, name, sheet, filt in INTERFACE_TABLES:
        if ctx.sheet_owner[sheet] in built_workers or name in ctx.tables:
            continue
        rows = data.rows(table.key)
        if filt:
            rows = [r for r in rows if r.get(filt[0]) == filt[1]]
        headers = [c.name for c in table.columns]
        values = [[typed_value(c, r.get(c.name)) for c in table.columns] for r in rows]
        top = next_row.get(sheet, 3)
        ctx.add_stub_table(sheet, top, name, headers, values)
        next_row[sheet] = top + max(len(values), 1) + 4
        stubbed.append(name)
    return stubbed
