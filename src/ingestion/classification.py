"""AMFI/AMC industry label -> model Sector vocabulary (spec <classification_rule>).

The AMCs print the AMFI industry classification (and NASDAQ's for foreign shares). The model's Sector list
(src/common/enums.py::Sector) is coarser. This table is an analyst mapping, not a reported fact: it is
listed on SECTOR_CLASSIFICATION and every registry row that uses it carries Source_Status
"Imported but not yet reconciled". Sector is never "PSU": ownership is a separate field.
"""
from __future__ import annotations

import re

from src.common.enums import AssetClass, BusinessModel, Sector

S = Sector
INDUSTRY_TO_SECTOR: dict[str, Sector] = {
    "banks": S.FINANCIAL_SERVICES, "finance": S.FINANCIAL_SERVICES, "insurance": S.FINANCIAL_SERVICES,
    "capital markets": S.FINANCIAL_SERVICES, "financial technology (fintech)": S.FINANCIAL_SERVICES,
    "it - software": S.IT,
    "computer software: prepackaged software": S.IT,
    "computer software: programming, data processing": S.IT,
    "telecom - services": S.TELECOM,
    "pharmaceuticals & biotechnology": S.HEALTHCARE, "healthcare services": S.HEALTHCARE,
    "automobiles": S.AUTO, "auto components": S.AUTO, "agricultural, commercial & construction vehicles": S.AUTO,
    "power": S.ENERGY, "gas": S.ENERGY, "consumable fuels": S.ENERGY, "oil": S.ENERGY, "petroleum products": S.ENERGY,
    "diversified fmcg": S.CONSUMER_STAPLES, "food products": S.CONSUMER_STAPLES, "personal products": S.CONSUMER_STAPLES,
    "beverages": S.CONSUMER_STAPLES, "agricultural food & other products": S.CONSUMER_STAPLES,
    "household products": S.CONSUMER_STAPLES,
    "consumer durables": S.CONSUMER_DURABLES,
    "ferrous metals": S.METALS_MINING, "non - ferrous metals": S.METALS_MINING,
    "aerospace & defense": S.DEFENCE,
    "industrial products": S.INDUSTRIALS, "commercial services & supplies": S.INDUSTRIALS,
    "construction": S.INFRA, "transport services": S.INFRA,
    "realty": S.REAL_ESTATE,
    "chemicals & petrochemicals": S.CHEMICALS, "fertilizers & agrochemicals": S.CHEMICALS,
    "cement & cement products": S.CHEMICALS,
    "retailing": S.OTHER, "leisure services": S.OTHER, "media": S.OTHER, "textiles & apparels": S.OTHER,
    "catalog/specialty distribution": S.OTHER,
}


def _key(industry: str) -> str:
    return re.sub(r"\s+", " ", (industry or "").strip().lower())


def sector_of(industry: str, asset_class: str = "") -> str:
    """Sector value for an AMC industry label; unknown labels map to 'Other Sectors' (never guessed finer)."""
    return INDUSTRY_TO_SECTOR.get(_key(industry), S.OTHER).value


def is_mapped(industry: str) -> bool:
    return _key(industry) in INDUSTRY_TO_SECTOR


def business_model_of(industry: str, asset_class: str) -> str:
    """Coarse business model from the AMC industry label. Only 'Banks' maps to a deposit-taking bank;
    other financials are 'Other'; every non-financial operating company is 'Non-financial operating company'."""
    k = _key(industry)
    if asset_class == AssetClass.REIT_INVIT.value:
        return BusinessModel.OTHER.value
    if k == "banks":
        return BusinessModel.BANK.value
    if INDUSTRY_TO_SECTOR.get(k) == S.FINANCIAL_SERVICES:
        return BusinessModel.OTHER.value
    return BusinessModel.NON_FINANCIAL.value
