"""Recalculates the canonical link formulas in LibreOffice (WI-6, WI-7, contract §7.2)."""
import shutil

import pytest

from build.recalc import read_values, recalc
from src.common import link_patterns as L
from src.common.workbook import TableColumn, WorkbookContext

pytestmark = [pytest.mark.workbook,
              pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")]


def test_link_patterns_keep_unvalued_holdings_visible(tmp_path):
    ctx = WorkbookContext(str(tmp_path / "links.xlsx"), test_build=True)
    ctx.create_sheets(["VALUATION_OUTPUTS", "SCENARIO_ANALYSIS", "PPFAS_FLEXICAP_HOLDINGS"])
    ctx.sheet("02-valuation", "VALUATION_OUTPUTS")
    ctx.add_table("02-valuation", "VALUATION_OUTPUTS", 2, 0, "tbl_ValuationOutputs",
                  [TableColumn(c) for c in ("Security_ID", "FV_Base_INR", "FV_Bear_INR", "FV_Bull_INR")],
                  [["S90001", 500.0, 400.0, 600.0], ["S90003", None, None, None]])     # S90003 unvalued
    ctx.sheet("03-nav", "SCENARIO_ANALYSIS")
    ctx.add_table("03-nav", "SCENARIO_ANALYSIS", 2, 0, "tbl_PriceControls",
                  [TableColumn("Security_ID"), TableColumn("Original_Market_Price"),
                   TableColumn("Model_FV_Base", formula=L.PC_MODEL_FV["Base"], role="link")],
                  [["S90001", 750.0], ["S90003", 100.0], ["S90009", 50.0]])           # S90009 has no row at all
    ctx.sheet("03-nav", "PPFAS_FLEXICAP_HOLDINGS")
    ctx.add_table("03-nav", "PPFAS_FLEXICAP_HOLDINGS", 2, 0, "tbl_Holdings_MF001",
                  [TableColumn("Holding_Line_ID"), TableColumn("Line_Role"), TableColumn("Security_ID"),
                   TableColumn("Asset_Class"), TableColumn("Quantity_Held"), TableColumn("Market_Value_INR_Cr"),
                   TableColumn("Weight_Pct_of_Scheme_NAV"),
                   TableColumn("Current_Market_Price", formula=L.H_CURRENT_PRICE, role="link"),
                   TableColumn("Base_Fair_Value", formula=L.H_BASE_FV, role="link"),
                   TableColumn("Valuation_Coverage_Status", formula=L.H_COVERAGE_STATUS, role="calc"),
                   TableColumn("Adj_Base", formula=L.H_ADJ_BASE, role="calc"),
                   TableColumn("MV_Mkt_INR_Cr", formula=L.H_MV_MKT, role="calc")],
                  [["L1", "POSITION", "S90001", "Indian listed equity", 4_000_000, 300.0, 0.30],
                   ["L3", "POSITION", "S90003", "Indian listed equity", 10_000_000, 100.0, 0.10],
                   ["L4", "ONA_ASSET", None, "Cash and cash equivalents", None, 410.0, 0.41],
                   ["L9", "POSITION", "S90404", "Indian listed equity", 1, 1.0, 0.0]])   # not in price controls
    ctx.close()
    v = read_values(recalc(tmp_path / "links.xlsx", tmp_path / "out"))
    pc, h = v["SCENARIO_ANALYSIS"], v["PPFAS_FLEXICAP_HOLDINGS"]
    # tbl_PriceControls data rows start on sheet row 4 (header row 3); column C = Model_FV_Base
    assert pc["C4"] == 500
    assert pc.get("C5") in (None, "")          # blank source -> blank, NOT 0
    assert pc.get("C6") in (None, "")          # absent from valuation outputs -> blank
    # holdings: H price, I FV, J status, K adj, L MV
    assert h["J4"] == "MODEL_VALUED" and h["K4"] == pytest.approx(0.30 * (500 / 750 - 1))
    assert h["J5"] == "UNVALUED" and h["K5"] == 0
    assert h["J6"] == "CARRYING_VALUE" and h["L6"] == 410
    assert h["L4"] == pytest.approx(300.0)
    assert str(h["H7"]).startswith("#N/A")     # unknown security stays visibly broken (WI-6)
