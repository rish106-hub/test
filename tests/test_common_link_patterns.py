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
                  [["S90001", 500.0, 400.0, 600.0], ["S90003", None, None, None],      # S90003 unvalued
                   ["S90007", 50.0, 40.0, 60.0]])                                   # S90007 valued but unpriced
    ctx.sheet("03-nav", "SCENARIO_ANALYSIS")
    ctx.add_table("03-nav", "SCENARIO_ANALYSIS", 2, 0, "tbl_PriceControls",
                  [TableColumn("Security_ID"), TableColumn("Original_Market_Price"),
                   TableColumn("Model_FV_Base", formula=L.PC_MODEL_FV["Base"], role="link"),
                   TableColumn("Model_FV_Bear", formula=L.PC_MODEL_FV["Bear"], role="link")],
                  [["S90001", 750.0], ["S90003", 100.0], ["S90009", 50.0],            # S90009 has no row at all
                   ["S90007", None]])                                                # no price at in_Price_Date
    ctx.sheet("03-nav", "PPFAS_FLEXICAP_HOLDINGS")
    ctx.add_table("03-nav", "PPFAS_FLEXICAP_HOLDINGS", 2, 0, "tbl_Holdings_MF001",
                  [TableColumn("Holding_Line_ID"), TableColumn("Line_Role"), TableColumn("Security_ID"),
                   TableColumn("Asset_Class"), TableColumn("Quantity_Held"), TableColumn("Market_Value_INR_Cr"),
                   TableColumn("Weight_Pct_of_Scheme_NAV"),
                   TableColumn("Current_Market_Price", formula=L.H_CURRENT_PRICE, role="link"),
                   TableColumn("Base_Fair_Value", formula=L.H_BASE_FV, role="link"),
                   TableColumn("Holdings_Match_Status", formula=L.H_MATCH_STATUS, role="calc"),
                   TableColumn("Valuation_Coverage_Status", formula=L.H_COVERAGE_STATUS, role="calc"),
                   TableColumn("Adj_Base", formula=L.H_ADJ_BASE, role="calc"),
                   TableColumn("MV_Mkt_INR_Cr", formula=L.H_MV_MKT, role="calc"),
                   TableColumn("Adj_Bear", formula=L.H_ADJ["Bear"], role="calc")],
                  [["L1", "POSITION", "S90001", "Indian listed equity", 4_000_000, 300.0, 0.30],
                   ["L3", "POSITION", "S90003", "Indian listed equity", 10_000_000, 100.0, 0.10],
                   ["L4", "ONA_ASSET", None, "Cash and cash equivalents", None, 410.0, 0.41],
                   ["L9", "POSITION", "S90404", "Indian listed equity", 1, 1.0, 0.0],    # not in price controls
                   ["L7", "POSITION", "S90007", "Indian listed equity", 1, 1.0, 0.0],    # has FV, no price
                   ["L10", "POSITION", "S90001", "Indian listed equity", None, 300.0, 0.30],  # quantity missing
                   ["L11", "POSITION", "S90003", "Debt", 5, 7.5, 0.075]])                  # pass-through
    ctx.close()
    v = read_values(recalc(tmp_path / "links.xlsx", tmp_path / "out"))
    pc, h = v["SCENARIO_ANALYSIS"], v["PPFAS_FLEXICAP_HOLDINGS"]
    # tbl_PriceControls data rows start on sheet row 4 (header row 3); column C = Model_FV_Base
    assert pc["C4"] == 500
    assert pc.get("C5") in (None, "")          # blank source -> blank, NOT 0
    assert pc.get("C6") in (None, "")          # absent from valuation outputs -> blank
    # holdings: H price, I FV, J match, K status, L adj, M MV, N Adj_Bear
    assert h["J4"] == "MATCHED" and h["K4"] == "MODEL_VALUED" and h["L4"] == pytest.approx(0.30 * (500 / 750 - 1))
    assert h["J5"] == "MATCHED" and h["K5"] == "UNVALUED" and h["L5"] == 0
    assert h.get("J6") in (None, "") and h["K6"] == "CARRYING_VALUE" and h["M6"] == 410
    assert h["M4"] == pytest.approx(300.0)
    assert str(h["H7"]).startswith("#N/A")     # unknown security stays visibly broken (WI-6)
    assert h["J7"] == "UNMATCHED" and h["K7"] == "UNVALUED"
    assert h["J8"] == "NO_PRICE" and h["K8"] == "UNVALUED" and h["L8"] == 0   # a fair value without a price is not "valued"
    # D-029 (CR-03-nav-001): a position's market value is never a silent 0 or #VALUE!
    assert str(h["M8"]).startswith("#N/A")     # NO_PRICE: was #VALUE! in v1.1
    assert str(h["M9"]).startswith("#N/A")     # blank quantity: was a silent 0 in v1.1
    assert h["K10"] == "MARKET_PASS_THROUGH" and h["M10"] == pytest.approx(7.5)   # disclosed value, not 5 x 100 / 1e7
    # Bear variant, hand-derived: 0.30 x (400 / 750 - 1) = -0.14; no Bear FV or no price -> 0
    assert h["N4"] == pytest.approx(-0.14)
    assert h["N5"] == 0 and h["N8"] == 0
