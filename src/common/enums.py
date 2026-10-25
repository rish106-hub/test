"""Controlled vocabularies shared by every module.

Owner: 00-main. Workers import these; they never redefine them locally. The string
values are what appears in CSVs, Excel dropdowns and status cells, so changing a
value is a contract change (spec/change_requests/).
"""
from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # so f-strings and csv writers emit the value
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


class DataStatus(StrEnum):
    """spec <data_statuses>, plus the quarantined synthetic status (D-013)."""
    RETRIEVED_VERIFIED = "Retrieved and verified"
    IMPORTED_UNRECONCILED = "Imported but not yet reconciled"
    CALCULATED_FROM_SOURCE = "Calculated from cited source data"
    THIRD_PARTY_ESTIMATE = "Third-party estimate"
    USER_ASSUMPTION = "User assumption"
    UNAVAILABLE = "Unavailable"
    STALE = "Stale"
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC TEST FIXTURE"


class SourceTier(StrEnum):
    """spec <source_priority>."""
    T1_COMPANY_FILING = "1"
    T2_REGULATOR_EXCHANGE_AMC = "2"
    T3_MARKET_DATA_PROVIDER = "3"
    T4_SECONDARY = "4"


class AssetClass(StrEnum):
    """spec <supported_asset_classes>."""
    INDIAN_EQUITY = "Indian listed equity"
    FOREIGN_EQUITY = "Foreign listed equity"
    DEBT = "Debt securities"
    CASH = "Cash and cash equivalents"
    MONEY_MARKET = "Money-market instruments"
    DERIVATIVE = "Derivatives"
    REIT_INVIT = "REITs and InvITs"
    OTHER = "Other eligible investments"


EQUITY_ASSET_CLASSES = frozenset({AssetClass.INDIAN_EQUITY, AssetClass.FOREIGN_EQUITY})


class LineRole(StrEnum):
    """How a holdings line enters net assets. Prevents double counting (contract §7.3)."""
    POSITION = "POSITION"            # security with quantity and price
    ONA_ASSET = "ONA_ASSET"          # cash, TREPS, receivables, accrued income
    ONA_LIABILITY = "ONA_LIABILITY"  # payables, accrued expenses (stored as negative value)


class CoverageStatus(StrEnum):
    """contract §7.0."""
    MODEL_VALUED = "MODEL_VALUED"
    CARRYING_VALUE = "CARRYING_VALUE"
    MARKET_PASS_THROUGH = "MARKET_PASS_THROUGH"
    UNVALUED = "UNVALUED"


class HoldingsMatchStatus(StrEnum):
    """contract §7.5a. Whether a disclosed POSITION line can be marked at in_Price_Date."""
    MATCHED = "MATCHED"            # registry Security_ID and a price at in_Price_Date
    UNMATCHED = "UNMATCHED"        # no registry Security_ID for the disclosed ISIN
    NO_PRICE = "NO_PRICE"          # Security_ID known, no price at in_Price_Date


class Sector(StrEnum):
    """spec <future_sector_coverage>. PSU is *not* a sector (spec <classification_rule>)."""
    FINANCIAL_SERVICES = "Financial Services"
    IT = "Information Technology"
    TECH_HARDWARE = "Technology Hardware and Electronics"
    CONSUMER_DURABLES = "Consumer Durables"
    CONSUMER_STAPLES = "Consumer Staples"
    METALS_MINING = "Metals and Mining"
    DEFENCE = "Defence and Aerospace"
    INDUSTRIALS = "Industrials and Capital Goods"
    INFRA = "Infrastructure and Construction"
    HEALTHCARE = "Healthcare and Pharmaceuticals"
    AUTO = "Automobiles and Auto Components"
    ENERGY = "Energy and Utilities"
    TELECOM = "Telecommunications"
    CHEMICALS = "Chemicals and Materials"
    REAL_ESTATE = "Real Estate"
    OTHER = "Other Sectors"
    NOT_APPLICABLE = "Not applicable"  # cash, TREPS, receivables


class OwnershipType(StrEnum):
    PRIVATE = "Private"
    GOVERNMENT_PSU = "Government-owned (PSU)"
    FOREIGN_PROMOTER = "Foreign promoter"
    OTHER = "Other"


class BusinessModel(StrEnum):
    """Drives method selection (R004/R005). Extend via change request."""
    BANK = "Deposit-taking bank"
    SMALL_FINANCE_BANK = "Small finance bank"
    INSURANCE_HOLDCO = "Insurance holding company"
    LIFE_INSURER = "Life insurer"
    NBFC = "Non-bank lender"
    NON_FINANCIAL = "Non-financial operating company"
    OTHER = "Other"


BANK_MODELS = frozenset({BusinessModel.BANK, BusinessModel.SMALL_FINANCE_BANK})


class ValuationMethod(StrEnum):
    RESIDUAL_INCOME = "Residual Income"
    DDM = "Dividend Discount"
    JUSTIFIED_PB = "Justified P/B"
    PEER_PB = "Peer-relative P/B"
    PEER_PABV = "Peer-relative P/ABV"
    PEER_PE = "Peer-relative P/E"
    INSURANCE_SOTP = "Insurance SOTP"
    FCFF_DCF = "FCFF DCF (WACC)"
    FCFE = "FCFE"
    EV_MULTIPLE = "EV multiple"
    NONE = "None"


class Case(StrEnum):
    BEAR = "Bear"
    BASE = "Base"
    BULL = "Bull"


class MarketPriceMode(StrEnum):
    """contract §6. Exact strings are the Excel dropdown values."""
    ORIGINAL = "Original Market Price"
    SHOCK = "Market Price Shock"
    ABSOLUTE = "Absolute Scenario Market Price"


class FairValueMode(StrEnum):
    MODEL_BASE = "Model Base Fair Value"
    FUNDAMENTAL = "Fundamental Assumption Scenario"
    MANUAL_BIAS = "Manual Fair-Value Bias"


class CheckResult(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    MISSING = "MISSING"
    STALE = "STALE"
    NOT_RUN = "NOT RUN"  # a test that has not executed is never reported as PASS


class PeriodType(StrEnum):
    FY = "FY"
    QUARTER = "Q"
    TTM = "TTM"
    POINT = "POINT"  # balance-sheet or market observation at a date


class AccountingBasis(StrEnum):
    STANDALONE = "Standalone"
    CONSOLIDATED = "Consolidated"


class MetricKind(StrEnum):
    REPORTED = "Reported"
    CALCULATED = "Calculated"
    MODELLED = "Modelled"
    CONSENSUS = "Third-party consensus"


class OutputLabel(StrEnum):
    """contract §1. Fixed captions; the five value outputs never share a label."""
    OFFICIAL_NAV = "Official NAV (published)"
    FAIR_NAV = "Modelled Intrinsic Value per Unit (estimate, not official NAV)"
    SCENARIO_MARKET_NAV = "Scenario Market NAV (hypothetical prices, not official NAV)"
    HYPOTHETICAL_PORTFOLIO = "Hypothetical Rebalanced Portfolio Value (not an existing fund)"
    TARGET_PURCHASE_PRICE = "Target Purchase Price (selected fair value less margin of safety; not a price forecast)"
