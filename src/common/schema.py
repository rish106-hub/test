"""Canonical table schemas: the single source of truth for every shared table.

Owner: 00-main. `spec/data_schema.md` is generated from this file
(`python tools/render_schema_doc.py`) and a test fails if the two drift.

`origin` says where a column's value comes from:
  stored        - persisted in the canonical CSV by the producing module
  workbook_link - not stored; the workbook fills it with a formula linking to
                  another table (e.g. registry Base_Fair_Value <- tbl_ValuationOutputs)
  workbook_calc - not stored; computed by a formula in the same table
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.common import enums as E


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str  # str | float | int | date | bool
    unit: str = ""
    required: bool = False
    enum: tuple[str, ...] | None = None
    origin: str = "stored"
    description: str = ""


@dataclass(frozen=True)
class Table:
    key: str                 # python handle
    excel_name: str          # Excel table name (tbl_*)
    sheet: str               # worksheet the table lives on
    csv_path: str | None     # canonical CSV under data/, None if workbook-only
    producer: str            # worktree that writes the data
    consumers: tuple[str, ...]
    primary_key: tuple[str, ...]
    columns: tuple[Column, ...]
    append_only: bool = False
    notes: str = ""

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"{self.key} has no column {name!r}")

    @property
    def stored_columns(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.origin == "stored")


def C(name, dtype="str", unit="", required=False, enum=None, origin="stored", description=""):
    return Column(name, dtype, unit, required, tuple(enum.values()) if enum else None, origin, description)


_DS = E.DataStatus

# --------------------------------------------------------------------------- sources
SOURCE_MANIFEST = Table(
    key="source_manifest", excel_name="tbl_SourceManifest", sheet="SOURCE_LOG",
    csv_path="data/source_manifest.csv", producer="01-data", consumers=("00-main", "05-qa"),
    primary_key=("Source_Doc_ID",), append_only=True,
    notes="One row per source document or file. SHA256 lets QA prove a raw file is unchanged.",
    columns=(
        C("Source_Doc_ID", required=True, description="DOC-000001 style, never reused"),
        C("Entity_or_Fund_ID", required=True),
        C("Document_Name", required=True),
        C("Document_Type", required=True, description="Annual report, Quarterly results, Portfolio disclosure, NAV file, Price file, ..."),
        C("Source_Tier", required=True, enum=E.SourceTier),
        C("URL", description="Official URL where the document was obtained"),
        C("Local_Path", description="Path under data/raw/ if the file is committed"),
        C("SHA256", description="Hash of the file as retrieved"),
        C("Publication_Date", "date"),
        C("Period_Covered"),
        C("Retrieval_Date", "date", required=True),
        C("Access_or_Licence_Note"),
    ),
)

SOURCE_LOG = Table(
    key="source_log", excel_name="tbl_SourceLog", sheet="SOURCE_LOG",
    csv_path="data/canonical/source_log.csv", producer="01-data", consumers=("00-main", "05-qa"),
    primary_key=("Source_ID",), append_only=True,
    notes="spec <source_log_fields>: one row per material extracted value (R002).",
    columns=(
        C("Source_ID", required=True, description="SRC-000001 style; referenced by every data row"),
        C("Source_Doc_ID", required=True, description="FK -> source_manifest"),
        C("Entity_ID", required=True, description="Entity_ID, Fund_ID or Plan_ID"),
        C("Metric", required=True, description="Metric_ID from metric_dictionary"),
        C("Reported_Value", "str", description="As printed in the source, unconverted"),
        C("Unit", required=True),
        C("Reporting_Period"),
        C("Observation_Date", "date"),
        C("Document_Name", required=True),
        C("URL_or_File_Path", required=True),
        C("Page_or_Table", required=True),
        C("Retrieval_Date", "date", required=True),
        C("Source_Type", required=True, enum=E.SourceTier),
        C("Destination_Table", required=True),
        C("Data_Quality_Status", required=True, enum=_DS),
    ),
)

DATASET_INVENTORY = Table(
    key="dataset_inventory", excel_name="tbl_DatasetInventory", sheet="DATA_FEASIBILITY",
    csv_path="data/canonical/dataset_inventory.csv", producer="01-data", consumers=("00-main", "05-qa"),
    primary_key=("Dataset_ID",),
    notes="spec <dataset_inventory_fields>. Phase-1 gate: must exist before real data reaches valuations.",
    columns=(
        C("Dataset_ID", required=True), C("Entity_or_Fund_ID", required=True),
        C("Metric_or_File", required=True), C("Preferred_Source", required=True),
        C("Backup_Source"), C("Available_History"), C("Latest_Observation_Date", "date"),
        C("Retrieval_Method", required=True), C("Refresh_Frequency", required=True),
        C("Access_or_Licensing_Constraint"), C("Quality_Status", required=True, enum=_DS),
        C("Missing_Data_Impact"),
    ),
)

MISSING_DATA = Table(
    key="missing_data", excel_name="tbl_MissingData", sheet="MISSING_DATA",
    csv_path="data/canonical/missing_data.csv", producer="01-data", consumers=("00-main", "02-valuation", "03-nav", "05-qa"),
    primary_key=("Missing_ID",),
    columns=(
        C("Missing_ID", required=True), C("Entity_or_Fund_ID", required=True),
        C("Dataset_ID"), C("Metric_ID"), C("Period"),
        C("Reason", required=True, description="What was tried and why it failed"),
        C("Impact", required=True, description="Which outputs are blank or degraded"),
        C("Logged_Date", "date", required=True),
        C("Status", required=True, description="Open / Resolved"),
    ),
)

# --------------------------------------------------------------------------- reference
METRIC_DICTIONARY = Table(
    key="metric_dictionary", excel_name="tbl_MetricDictionary", sheet="METRIC_DICTIONARY",
    csv_path="data/reference/metric_dictionary.csv", producer="00-main", consumers=("01-data", "02-valuation", "04-charts", "05-qa"),
    primary_key=("Metric_ID",),
    columns=(
        C("Metric_ID", required=True), C("Metric_Name", required=True),
        C("Definition", required=True), C("Unit", required=True),
        C("Applies_To", required=True, description="Bank | Insurer | NonFin | Fund | All"),
        C("Kind", required=True, enum=E.MetricKind),
        C("Formula", description="For Calculated metrics: formula over other Metric_IDs"),
        C("Spec_Ref", description="Section of the v3 spec or contract"),
    ),
)

# --------------------------------------------------------------------------- securities
SECURITY_REGISTRY = Table(
    key="security_registry", excel_name="tbl_Registry", sheet="MASTER_SECURITY_REGISTRY",
    csv_path="data/canonical/security_registry.csv", producer="01-data",
    consumers=("02-valuation", "03-nav", "04-charts", "05-qa"),
    primary_key=("Security_ID",),
    notes="spec <security_registry>. ISIN is the import matching key; Security_ID is the join key.",
    columns=(
        C("Security_ID", required=True, description="S00001 style, stable forever"),
        C("Entity_ID", required=True, description="Issuer; C001..C007 are the seed companies"),
        C("ISIN", description="Blank only for non-ISIN lines; unique when present"),
        C("Exchange_Ticker"), C("Company_Name", required=True),
        C("Sector", required=True, enum=E.Sector), C("Industry"),
        C("Business_Model", required=True, enum=E.BusinessModel),
        C("Asset_Class", required=True, enum=E.AssetClass),
        C("Country_or_Market", required=True), C("Trading_Currency", required=True),
        C("Reporting_Currency"), C("Ownership_Type", required=True, enum=E.OwnershipType),
        C("Listing_Status", required=True, description="Listed / Suspended / Delisted / Unlisted"),
        C("Primary_Valuation_Method", enum=E.ValuationMethod),
        C("Secondary_Valuation_Method", enum=E.ValuationMethod),
        C("Dedicated_Sheet", description="VAL_* sheet name if one exists"),
        C("Current_Market_Price", "float", "INR", origin="workbook_link", description="<- tbl_MarketPrices at in_Price_Date"),
        C("Market_Price_Date", "date", origin="workbook_link"),
        C("Base_Fair_Value", "float", "INR", origin="workbook_link", description="<- tbl_ValuationOutputs"),
        C("Bear_Fair_Value", "float", "INR", origin="workbook_link"),
        C("Bull_Fair_Value", "float", "INR", origin="workbook_link"),
        C("Valuation_Date", "date", origin="workbook_link"),
        C("Valuation_Coverage_Status", enum=E.CoverageStatus, origin="workbook_link"),
        C("Source_Status", required=True, enum=_DS),
        C("Source_ID", description="Source of identifiers/classification"),
    ),
)

RAW_FINANCIALS = Table(
    key="raw_financials", excel_name="tbl_RawFinancials", sheet="RAW_FINANCIAL_DATA",
    csv_path="data/canonical/raw_financials.csv", producer="01-data",
    consumers=("02-valuation", "04-charts", "05-qa"),
    primary_key=("Observation_ID",), append_only=True,
    notes="Long format. Revisions add a row with Supersedes_Observation_ID; nothing is overwritten. "
          "Known_As_Of supports point-in-time backtests.",
    columns=(
        C("Observation_ID", required=True), C("Entity_ID", required=True),
        C("Metric_ID", required=True, description="FK -> metric_dictionary"),
        C("Period_Type", required=True, enum=E.PeriodType),
        C("Period_End", "date", required=True), C("Fiscal_Label", required=True),
        C("Accounting_Basis", required=True, enum=E.AccountingBasis),
        C("Value", "float", required=True, description="Converted to canonical unit"),
        C("Unit", required=True, description="Canonical unit (INR_Cr, INR, decimal, count, x)"),
        C("Raw_Value", required=True), C("Raw_Unit", required=True),
        C("Source_ID", required=True), C("Data_Status", required=True, enum=_DS),
        C("Import_Batch_ID", required=True),
        C("Known_As_Of", "date", required=True, description="Date the value became public"),
        C("Supersedes_Observation_ID"), C("Normalisation_Note"),
    ),
)

MARKET_PRICES = Table(
    key="market_prices", excel_name="tbl_MarketPrices", sheet="MARKET_PRICES",
    csv_path="data/canonical/market_prices.csv", producer="01-data",
    consumers=("02-valuation", "03-nav", "04-charts", "05-qa"),
    primary_key=("Security_ID", "Price_Date"), append_only=True,
    columns=(
        C("Security_ID", required=True), C("Price_Date", "date", required=True),
        C("Close_LCY", "float", "LCY", required=True), C("Currency", required=True),
        C("FX_Rate_to_INR", "float", "INR per LCY", required=True, description="1.0 for INR"),
        C("FX_Date", "date", required=True),
        C("Close_INR", "float", "INR", required=True, description="Close_LCY * FX_Rate_to_INR"),
        C("Local_Close_Timestamp", description="Exchange close time with timezone"),
        C("Corporate_Action_Adjusted", "bool", required=True),
        C("Source_ID", required=True), C("Data_Status", required=True, enum=_DS),
    ),
)

CORPORATE_ACTIONS = Table(
    key="corporate_actions", excel_name="tbl_CorporateActions", sheet="RAW_FINANCIAL_DATA",
    csv_path="data/canonical/corporate_actions.csv", producer="01-data", consumers=("02-valuation", "05-qa"),
    primary_key=("Action_ID",), append_only=True,
    columns=(
        C("Action_ID", required=True), C("Security_ID", required=True),
        C("Action_Type", required=True, description="Split / Bonus / Rights / Dividend / Merger / Demerger"),
        C("Ex_Date", "date", required=True), C("Record_Date", "date"),
        C("Ratio_or_Amount", required=True, description="e.g. '1:1' bonus, '19.5' INR dividend"),
        C("Source_ID", required=True),
        C("Data_Status", required=True, enum=_DS),
    ),
)

# --------------------------------------------------------------------------- funds
FUND_PLANS = Table(
    key="fund_plans", excel_name="tbl_FundPlans", sheet="MF_NAV_CALCULATOR",
    csv_path="data/canonical/fund_plans.csv", producer="01-data", consumers=("03-nav", "04-charts", "05-qa"),
    primary_key=("Plan_ID",),
    columns=(
        C("Plan_ID", required=True, description="MF001-DIR-GR"), C("Fund_ID", required=True),
        C("Scheme_Name", required=True), C("AMC", required=True),
        C("Plan", required=True, description="Direct / Regular"), C("Option", required=True, description="Growth / IDCW"),
        C("AMFI_Scheme_Code", required=True), C("Benchmark_Name", required=True),
        C("Benchmark_Is_TRI", "bool", required=True), C("Source_ID", required=True),
        C("Data_Status", required=True, enum=_DS),
    ),
)

FUND_HOLDINGS = Table(
    key="fund_holdings", excel_name="tbl_Holdings_<FUND_ID>", sheet="<per-fund holdings sheet>",
    csv_path="data/canonical/fund_holdings.csv", producer="01-data",
    consumers=("03-nav", "04-charts", "05-qa"), primary_key=("Holding_Line_ID",), append_only=True,
    notes="One CSV for all funds; the workbook splits it into one table per Fund_ID "
          "(tbl_Holdings_MF001 on PPFAS_FLEXICAP_HOLDINGS, tbl_Holdings_MF002 on HDFC_MIDCAP_HOLDINGS). "
          "Holdings are scheme-level (shared by all plans), keyed by Fund_ID not Plan_ID.",
    columns=(
        C("Holding_Line_ID", required=True, description="MF001-2026-09-30-0001"),
        C("Fund_ID", required=True), C("Portfolio_Date", "date", required=True),
        C("Line_Role", required=True, enum=E.LineRole),
        C("Security_ID", description="Required for POSITION lines; blank for ONA lines"),
        C("ISIN"), C("Instrument_Name_As_Disclosed", required=True),
        C("Company_Name"), C("Sector", required=True, enum=E.Sector), C("Industry"),
        C("Asset_Class", required=True, enum=E.AssetClass),
        C("Country_or_Market"), C("Trading_Currency"),
        C("FX_Rate_to_INR", "float", "INR per LCY", description="As used in the disclosure, if stated"),
        C("Quantity_Held", "float", "count", description="Required for POSITION lines"),
        C("Market_Value_INR_Cr", "float", "INR_Cr", required=True, description="ONA_LIABILITY lines negative"),
        C("Raw_Market_Value", required=True), C("Raw_Market_Value_Unit", required=True, description="e.g. 'INR lakh'"),
        C("Weight_Pct_of_Scheme_NAV", "float", "decimal", required=True),
        C("Source_ID", required=True), C("Import_Batch_ID", required=True),
        C("Data_Status", required=True, enum=_DS),
        C("Current_Market_Price", "float", "INR", origin="workbook_link"),
        C("Selected_Scenario_Price", "float", "INR", origin="workbook_link"),
        C("Base_Fair_Value", "float", "INR", origin="workbook_link"),
        C("Scenario_Fair_Value", "float", "INR", origin="workbook_link"),
        C("Holdings_Match_Status", enum=E.HoldingsMatchStatus, origin="workbook_calc",
          description="contract §7.5a: POSITION lines only; blank for ONA lines"),
        C("Financials_As_Of", "date", origin="workbook_link",
          description="tbl_ValuationOutputs[Latest_Results_Period_End]; MODEL_VALUED lines only (§7.5c)"),
        C("Valuation_Coverage_Status", enum=E.CoverageStatus, origin="workbook_calc"),
        C("Adj_Base", "float", "decimal", origin="workbook_calc", description="contract §7.2 Adj_i"),
        C("Adj_Bear", "float", "decimal", origin="workbook_calc"),
        C("Adj_Bull", "float", "decimal", origin="workbook_calc"),
        C("Adj_Selected", "float", "decimal", origin="workbook_calc"),
        C("MV_Mkt_INR_Cr", "float", "INR_Cr", origin="workbook_calc", description="q * P / 1e7"),
        C("MV_Fair_Base_INR_Cr", "float", "INR_Cr", origin="workbook_calc"),
        C("MV_Scenario_INR_Cr", "float", "INR_Cr", origin="workbook_calc"),
    ),
)

FUND_SCHEME_TOTALS = Table(
    key="fund_scheme_totals", excel_name="tbl_SchemeTotals", sheet="MF_NAV_CALCULATOR",
    csv_path="data/canonical/fund_scheme_totals.csv", producer="01-data", consumers=("03-nav", "05-qa"),
    primary_key=("Fund_ID", "Portfolio_Date"),
    columns=(
        C("Fund_ID", required=True), C("Portfolio_Date", "date", required=True),
        C("Reported_Scheme_Net_Assets_INR_Cr", "float", "INR_Cr", required=True),
        C("Source_ID", required=True), C("Data_Status", required=True, enum=_DS),
    ),
)

OFFICIAL_NAV = Table(
    key="official_nav", excel_name="tbl_OfficialNAV", sheet="MF_NAV_CALCULATOR",
    csv_path="data/canonical/official_nav.csv", producer="01-data", consumers=("03-nav", "04-charts", "05-qa"),
    primary_key=("Plan_ID", "NAV_Date"), append_only=True,
    columns=(
        C("Plan_ID", required=True), C("NAV_Date", "date", required=True),
        C("NAV_INR", "float", "INR", required=True),
        C("Source_ID", required=True), C("Data_Status", required=True, enum=_DS),
    ),
)

BENCHMARK_TRI = Table(
    key="benchmark_tri", excel_name="tbl_BenchmarkTRI", sheet="FUND_PERFORMANCE",
    csv_path="data/canonical/benchmark_tri.csv", producer="01-data", consumers=("03-nav", "04-charts"),
    primary_key=("Benchmark_Name", "Date"), append_only=True,
    columns=(
        C("Benchmark_Name", required=True), C("Date", "date", required=True),
        C("Index_Value", "float", "index points", required=True), C("Is_TRI", "bool", required=True),
        C("Source_ID", required=True),
        C("Data_Status", required=True, enum=_DS),
    ),
)

# --------------------------------------------------------------------------- valuation
GLOBAL_INPUTS = Table(
    key="global_inputs", excel_name="tbl_GlobalInputs", sheet="GLOBAL_ASSUMPTIONS",
    csv_path="data/reference/global_inputs.csv", producer="00-main", consumers=("02-valuation", "03-nav", "04-charts", "05-qa"),
    primary_key=("Name",),
    notes="Each row's Value cell is exposed as the defined name in Name (in_*). Blank Value = not yet set; "
          "dependent outputs stay blank rather than using a hidden default.",
    columns=(
        C("Name", required=True, description="in_* defined name"),
        C("Value", description="Typed per Value_Type"),
        C("Value_Type", required=True, description="date | decimal | int | text"),
        C("Unit", required=True), C("Description", required=True),
        C("Allowed_Values", description="Semicolon list for dropdowns"),
        C("Assumption_Source_Type", required=True, enum=_DS), C("Source_ID"),
        C("Rationale", required=True),
    ),
)

ASSUMPTIONS = Table(
    key="assumptions", excel_name="tbl_Assumptions", sheet="VALUATION_ASSUMPTIONS",
    csv_path="data/canonical/assumptions.csv", producer="02-valuation", consumers=("03-nav", "05-qa"),
    primary_key=("Assumption_ID",),
    notes="Per-security valuation drivers and case sets (contract §3.6-3.8). Global inputs are in global_inputs.",
    columns=(
        C("Assumption_ID", required=True), C("Scope", required=True, description="GLOBAL or a Security_ID"),
        C("Case", required=True, description="Bear | Base | Bull | All"),
        C("Parameter", required=True), C("Period", required=True, description="FY label or ALL"),
        C("Value", "float", required=True), C("Unit", required=True),
        C("Assumption_Source_Type", required=True, enum=_DS),
        C("Source_ID"), C("Rationale", required=True),
    ),
)

VALUATION_OUTPUTS = Table(
    key="valuation_outputs", excel_name="tbl_ValuationOutputs", sheet="VALUATION_OUTPUTS",
    csv_path=None, producer="02-valuation", consumers=("03-nav", "04-charts", "05-qa"),
    primary_key=("Security_ID",),
    notes="THE interface between valuation and NAV. Workbook rows link (green) to VAL_* named outputs. "
          "The Python reference run writes the same columns to build/out/reference_valuation_outputs.csv for QA.",
    columns=(
        C("Security_ID", required=True), C("Valuation_Date", "date", required=True),
        C("Anchor_Date", "date", required=True,
          description="A: period end of the reported balance sheet behind BV_0 (contract §3.1)"),
        C("Latest_Results_Period_End", "date",
          description="R: end of the latest reported earnings period, interim included (§3.1a)"),
        C("Price_Date", "date", required=True, description="in_Price_Date of the market price compared"),
        C("BV_Reported_At_Anchor_INR", "float", "INR",
          description="Historical: reported BVPS at Anchor_Date. Never relabelled as current"),
        C("BV_Estimated_At_Valuation_INR", "float", "INR",
          description="Estimate: equity bridge A -> V (§3.1a)"),
        C("Interim_EPS_Deviation_Pct", "float", "decimal", description="§3.1a; blank when no interim results after A"),
        C("Forecast_Update_Flag", enum=E.CheckResult, description="§3.1a"),
        C("Financials_Age_Days", "int", "days", description="Valuation_Date - Latest_Results_Period_End"),
        C("Anchor_Age_Days", "int", "days", description="Valuation_Date - Anchor_Date"),
        C("Freshness_Status", enum=E.CheckResult, description="§3.1b"),
        C("Primary_Method", required=True, enum=E.ValuationMethod),
        C("Secondary_Methods", description="Semicolon-separated ValuationMethod values"),
        C("FV_Base_INR", "float", "INR"), C("FV_Bear_INR", "float", "INR"), C("FV_Bull_INR", "float", "INR"),
        C("Terminal_Value_Share_Base", "float", "decimal"),
        C("Terminal_Flag", enum=E.CheckResult), C("Peer_Flag", enum=E.CheckResult),
        C("Valuation_Coverage_Status", required=True, enum=E.CoverageStatus),
        C("Model_Sheet", required=True), C("Methodology_Version", required=True),
        C("Data_Confidence_Note", required=True, description="Coverage/freshness components, no composite score"),
    ),
)

PEER_MEMBERSHIP = Table(
    key="peer_membership", excel_name="tbl_PeerMembership", sheet="PEER_GROUPS",
    csv_path="data/canonical/peer_membership.csv", producer="04-charts", consumers=("02-valuation", "05-qa"),
    primary_key=("Peer_Group_ID", "Security_ID"),
    columns=(
        C("Peer_Group_ID", required=True), C("Peer_Group_Name", required=True),
        C("Security_ID", required=True), C("Included", "bool", required=True),
        C("Inclusion_Rationale", required=True), C("As_Of_Date", "date", required=True),
    ),
)

PEER_METRICS = Table(
    key="peer_metrics", excel_name="tbl_PeerMetrics", sheet="PEER_GROUPS",
    csv_path="data/canonical/peer_metrics.csv", producer="04-charts", consumers=("02-valuation", "05-qa"),
    primary_key=("Security_ID", "Metric_ID", "Price_Date"),
    columns=(
        C("Security_ID", required=True), C("Metric_ID", required=True),
        C("Value", "float"), C("Is_Meaningful", "bool", required=True),
        C("Period", required=True), C("Price_Date", "date", required=True),
        C("Source_ID", required=True), C("Data_Status", required=True, enum=_DS),
    ),
)

PEER_SUMMARY = Table(
    key="peer_summary", excel_name="tbl_PeerSummary", sheet="PEER_GROUPS",
    csv_path=None, producer="04-charts", consumers=("02-valuation",),
    primary_key=("Peer_Group_ID", "Metric_ID", "Exclude_Security_ID"),
    columns=(
        C("Peer_Group_ID", required=True), C("Metric_ID", required=True),
        C("Exclude_Security_ID", description="Subject company excluded from its own median"),
        C("Median", "float", origin="workbook_calc"), C("N_Valid", "int", origin="workbook_calc"),
        C("N_Excluded", "int", origin="workbook_calc"),
        C("Min", "float", origin="workbook_calc"), C("Max", "float", origin="workbook_calc"),
    ),
)

HISTORICAL_METRICS = Table(
    key="historical_metrics", excel_name="tbl_HistoricalMetrics", sheet="HISTORICAL_METRICS",
    csv_path=None, producer="02-valuation", consumers=("04-charts", "05-qa"),
    primary_key=("Entity_ID", "Metric_ID", "Fiscal_Label"),
    notes="Calculated history (formulas over tbl_RawFinancials) and forecast rows from the VAL_* models; "
          "the chart feed for G/V/B charts. Is_Forecast separates actuals from forecasts.",
    columns=(
        C("Entity_ID", required=True), C("Metric_ID", required=True), C("Fiscal_Label", required=True),
        C("Period_End", "date", required=True), C("Value", "float", origin="workbook_calc"),
        C("Unit", required=True), C("Kind", required=True, enum=E.MetricKind),
        C("Is_Forecast", "bool", required=True), C("Source_or_Formula", required=True),
    ),
)

# --------------------------------------------------------------------------- scenarios
SECTOR_SHOCKS = Table(
    key="sector_shocks", excel_name="tbl_SectorShocks", sheet="SCENARIO_ANALYSIS",
    csv_path=None, producer="03-nav", consumers=("04-charts",), primary_key=("Sector",),
    columns=(C("Sector", required=True, enum=E.Sector),
             C("Sector_Price_Shock_Pct", "float", "decimal", description="input, default 0")),
)

PRICE_CONTROLS = Table(
    key="price_controls", excel_name="tbl_PriceControls", sheet="SCENARIO_ANALYSIS",
    csv_path=None, producer="03-nav", consumers=("03-nav", "04-charts", "05-qa"),
    primary_key=("Security_ID",), notes="contract §6. One row per registry security.",
    columns=(
        C("Security_ID", required=True), C("Sector", origin="workbook_link"),
        C("Original_Market_Price", "float", "INR", origin="workbook_link"),
        C("Model_FV_Base", "float", "INR", origin="workbook_link"),
        C("Model_FV_Bear", "float", "INR", origin="workbook_link"),
        C("Model_FV_Bull", "float", "INR", origin="workbook_link"),
        C("Market_Price_Scenario_Mode", enum=E.MarketPriceMode, description="input"),
        C("Market_Price_Shock_Pct", "float", "decimal", description="input"),
        C("Absolute_Scenario_Price", "float", "INR", description="input"),
        C("Fair_Value_Scenario_Mode", enum=E.FairValueMode, description="input"),
        C("Fundamental_Case", enum=E.Case, description="input"),
        C("Fair_Value_Bias_Pct", "float", "decimal", description="input"),
        C("Required_Margin_of_Safety_Pct", "float", "decimal", description="input"),
        C("Effective_Shock_Pct", "float", "decimal", origin="workbook_calc"),
        C("Market_Price_After_Shock", "float", "INR", origin="workbook_calc"),
        C("Selected_Scenario_Market_Price", "float", "INR", origin="workbook_calc"),
        C("Fair_Value_After_Bias", "float", "INR", origin="workbook_calc"),
        C("Fundamental_Case_FV", "float", "INR", origin="workbook_calc"),
        C("Selected_Scenario_Fair_Value", "float", "INR", origin="workbook_calc"),
        C("Implied_Upside_To_Fair_Value", "float", "decimal", origin="workbook_calc"),
        C("Fair_Value_Gap", "float", "decimal", origin="workbook_calc"),
        C("Target_Purchase_Price", "float", "INR", origin="workbook_calc",
          description="Selected_Scenario_Fair_Value x (1 - margin of safety); the only TPP (D-023)"),
        C("FV_Label", origin="workbook_calc"),
        C("Control_Status", origin="workbook_calc"),
        C("Control_Warning", origin="workbook_calc",
          description="Names inputs that are set but ignored by the selected mode (§6.2); blank otherwise"),
    ),
)

CUSTOM_ALLOCATION = Table(
    key="custom_allocation", excel_name="tbl_CustomAllocation", sheet="PORTFOLIO_REBALANCING",
    csv_path="data/scenarios/custom_allocation.csv", producer="03-nav", consumers=("04-charts", "05-qa"),
    primary_key=("Line_ID",), notes="Hypothetical only (R011). Never referenced by actual-holdings formulas.",
    columns=(
        C("Line_ID", required=True), C("Sector", required=True, enum=E.Sector),
        C("Security_ID", description="Blank for an explicit cash / unallocated line"),
        C("Sector_Weight_Pct", "float", "decimal", required=True),
        C("Constituent_Weight_Pct", "float", "decimal", required=True),
        C("Assumed_Buy_Price_INR", "float", "INR"), C("Quantity_Override", "float", "count"),
        C("Effective_Weight_Pct", "float", "decimal", origin="workbook_calc"),
    ),
)

NAV_SUMMARY = Table(
    key="nav_summary", excel_name="tbl_NAVSummary", sheet="MF_NAV_CALCULATOR",
    csv_path=None, producer="03-nav", consumers=("00-main", "04-charts", "05-qa"), primary_key=("Plan_ID",),
    notes="One row per Plan_ID. Headline fair NAV = Method 1 (contract §7.2); Method 2 shown alongside with drift D2.",
    columns=(
        C("Plan_ID", required=True), C("Fund_ID", required=True), C("Portfolio_Date", "date"),
        C("NAV_Date", "date"), C("Official_NAV", "float", "INR"),
        C("Fair_NAV_Base", "float", "INR"), C("Fair_NAV_Bear", "float", "INR"), C("Fair_NAV_Bull", "float", "INR"),
        C("Fair_NAV_Selected", "float", "INR"), C("Fair_NAV_M2_Base", "float", "INR"),
        C("Scenario_Market_NAV", "float", "INR"),
        C("Diff_vs_Official_INR", "float", "INR"), C("Diff_vs_Official_Pct", "float", "decimal"),
        C("Price_Date", "date"), C("Valuation_Date", "date"),
        # (1) holdings coverage, §7.5a
        C("Holdings_Value_Coverage_Pct", "float", "decimal"), C("Holdings_Match_Pct", "float", "decimal"),
        C("Unmatched_Count", "int"), C("Recon_Gap_Pct", "float", "decimal"),
        C("Recon_Status", enum=E.CheckResult), C("Holdings_Coverage_Status", enum=E.CheckResult),
        # (2) valuation coverage, §7.5b
        C("Valuation_Coverage_Total_Pct", "float", "decimal"), C("Valuation_Coverage_Equity_Pct", "float", "decimal"),
        C("Unvalued_Weight_Pct", "float", "decimal"), C("Unvalued_Count", "int"),
        C("Unvalued_Value_INR_Cr", "float", "INR_Cr"),
        C("Valuation_Coverage_Status", enum=E.CheckResult), C("Coverage_Caption"),
        # (3) data freshness, §7.5c
        C("Holdings_Age_Days", "int", "days"), C("NAV_Date_Gap_Days", "int", "days"),
        C("Max_Financials_Age_Days", "int", "days"), C("Stale_Valued_Weight_Pct", "float", "decimal"),
        C("Freshness_Status", enum=E.CheckResult),
        C("Method_Drift_INR", "float", "INR"),
    ),
)

# --------------------------------------------------------------------------- governance
GOVERNANCE_LOG = Table(
    key="governance_log", excel_name="tbl_Governance", sheet="MODEL_GOVERNANCE",
    csv_path="data/canonical/governance_log.csv", producer="00-main", consumers=("05-qa",),
    primary_key=("Change_ID",), append_only=True, notes="spec <model_governance><fields> plus change metadata.",
    columns=(
        C("Change_ID", required=True), C("Change_Type", required=True, description="Formula | Peer group | Source data | Assumption | Override"),
        C("Model_Version", required=True), C("Valuation_Date", "date"), C("Source_Data_Cutoff", "date"),
        C("Methodology_Version", required=True), C("Assumption_ID"),
        C("Assumption_Source_Type", enum=_DS), C("Override_Original_Value"), C("Override_New_Value"),
        C("Override_Reason"), C("Override_Date", "date"), C("Last_Formula_Test_Date", "date"),
        C("Test_Status", enum=E.CheckResult), C("Last_Validated_Date", "date"), C("Changed_By", required=True),
    ),
)

VALIDATION_RESULTS = Table(
    key="validation_results", excel_name="tbl_ValidationChecks", sheet="VALIDATION_CHECKS",
    csv_path="build/out/validation_results.csv", producer="05-qa", consumers=("00-main",),
    primary_key=("Check_ID", "Executed_At"),
    notes="Only executed checks may carry PASS/WARNING/FAIL; everything else is NOT RUN.",
    columns=(
        C("Check_ID", required=True), C("Category", required=True), C("Description", required=True),
        C("Executed", "bool", required=True), C("Executed_At", required=True),
        C("Result", required=True, enum=E.CheckResult), C("Evidence", required=True),
        C("Tool", required=True, description="pytest node id, recalc harness, manual"),
    ),
)

ALL_TABLES: tuple[Table, ...] = (
    SOURCE_MANIFEST, SOURCE_LOG, DATASET_INVENTORY, MISSING_DATA, METRIC_DICTIONARY,
    SECURITY_REGISTRY, RAW_FINANCIALS, MARKET_PRICES, CORPORATE_ACTIONS,
    FUND_PLANS, FUND_HOLDINGS, FUND_SCHEME_TOTALS, OFFICIAL_NAV, BENCHMARK_TRI,
    GLOBAL_INPUTS, ASSUMPTIONS, VALUATION_OUTPUTS, HISTORICAL_METRICS,
    PEER_MEMBERSHIP, PEER_METRICS, PEER_SUMMARY,
    SECTOR_SHOCKS, PRICE_CONTROLS, NAV_SUMMARY, CUSTOM_ALLOCATION, GOVERNANCE_LOG, VALIDATION_RESULTS,
)

TABLES = {t.key: t for t in ALL_TABLES}
