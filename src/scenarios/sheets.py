"""Builds SCENARIO_ANALYSIS (tbl_PriceControls, tbl_SectorShocks). Owner: 03-nav.

Called from src/fund_nav/sheets.py::build_sheets so 03-nav has one entry point.

Contract section 6. Inputs are blue and validated, links green, outputs black. The price shocks are read in
exactly one column, Effective_Shock_Pct (W-17); every holding, NAV method and chart reads
Selected_Scenario_Market_Price. The Reset_* defaults and the Controls_At_Default check live in the private
tables tbl_Nav_PriceDefaults and tbl_Nav_ControlsStatus, because tbl_PriceControls has exactly the columns of
schema.PRICE_CONTROLS (module contract D-027).
"""
from __future__ import annotations

from src.common import link_patterns as L
from src.common import schema as S
from src.common.enums import Case, FairValueMode as F, MarketPriceMode as M, Sector
from src.common.workbook import TableColumn, WorkbookContext
from src.fund_nav import xl

OWNER = xl.OWNER
SHEET = "SCENARIO_ANALYSIS"
PC, SS = "tbl_PriceControls", "tbl_SectorShocks"
DEF, STATUS = "tbl_Nav_PriceDefaults", "tbl_Nav_ControlsStatus"
xl.register_private_table(DEF, SHEET)
xl.register_private_table(STATUS, SHEET)

# Test hooks (empty in every production build): {(Security_ID, column): value} and {Sector: shock}.
# tests/fund_nav use them to build a workbook whose controls are away from default.
PRICE_CONTROL_OVERRIDES: dict[tuple[str, str], object] = {}
SECTOR_SHOCK_OVERRIDES: dict[str, float] = {}

DEFAULTS = {
    "Market_Price_Scenario_Mode": M.ORIGINAL.value, "Market_Price_Shock_Pct": 0.0, "Absolute_Scenario_Price": None,
    "Fair_Value_Scenario_Mode": F.MODEL_BASE.value, "Fair_Value_Bias_Pct": 0.0,
}

TOP_SECTOR, TOP_STATUS, TOP_PC = 4, 24, 29       # 0-based header rows of the three tables
DEFAULTS_LEFT = 27


def _q(text: str) -> str:
    return '"' + text + '"'


def _price_control_formulas() -> dict[str, str]:
    mode, fvm = "[@Market_Price_Scenario_Mode]", "[@Fair_Value_Scenario_Mode]"
    sel_price = (f'=IF({mode}={_q(M.ORIGINAL.value)},IF(ISNUMBER([@Original_Market_Price]),[@Original_Market_Price],NA()),'
                 f'IF({mode}={_q(M.SHOCK.value)},IF(ISNUMBER([@Market_Price_After_Shock]),[@Market_Price_After_Shock],NA()),'
                 f'IF({mode}={_q(M.ABSOLUTE.value)},IF(ISNUMBER([@Absolute_Scenario_Price]),[@Absolute_Scenario_Price],NA()),'
                 "NA())))")
    sel_fv = (f'=IF({fvm}={_q(F.MODEL_BASE.value)},[@Model_FV_Base],'
              f'IF({fvm}={_q(F.FUNDAMENTAL.value)},[@Fundamental_Case_FV],'
              f'IF({fvm}={_q(F.MANUAL_BIAS.value)},[@Fair_Value_After_Bias],NA())))')
    c1 = f'AND(ROUND([@Effective_Shock_Pct],10)<>0,{mode}<>{_q(M.SHOCK.value)})'
    c2 = f'AND([@Absolute_Scenario_Price]<>"",{mode}<>{_q(M.ABSOLUTE.value)})'
    c3 = f'AND([@Fair_Value_Bias_Pct]<>0,{fvm}<>{_q(F.MANUAL_BIAS.value)})'
    t1 = f'"Price shocks set but ignored (mode: "&{mode}&")"'
    t2 = f'"Absolute price set but ignored (mode: "&{mode}&")"'
    t3 = f'"Fair-value bias set but ignored (mode: "&{fvm}&")"'
    warning = f'=IF({c1},{t1},"")&IF({c2},IF({c1},"; ","")&{t2},"")&IF({c3},IF(OR({c1},{c2}),"; ","")&{t3},"")'
    return {
        "Sector": "=" + xl.lookup("tbl_Registry", "Sector", "[@Security_ID]", "Security_ID"),
        # Original price at in_Price_Date: blank (not 0) when the security has no price that day (R009).
        "Original_Market_Price": (
            '=IF(in_Price_Date="","",IF(COUNTIFS(tbl_MarketPrices[Security_ID],[@Security_ID],'
            'tbl_MarketPrices[Price_Date],in_Price_Date,tbl_MarketPrices[Close_INR],"<>")=0,"",'
            'AVERAGEIFS(tbl_MarketPrices[Close_INR],tbl_MarketPrices[Security_ID],[@Security_ID],'
            "tbl_MarketPrices[Price_Date],in_Price_Date)))"),
        "Model_FV_Base": L.PC_MODEL_FV["Base"], "Model_FV_Bear": L.PC_MODEL_FV["Bear"],
        "Model_FV_Bull": L.PC_MODEL_FV["Bull"],
        "Fundamental_Case": "=in_Global_Case",
        "Required_Margin_of_Safety_Pct": "=in_Default_MoS",
        # The only place the three shock inputs are read (W-17). Multiplicative, from the original price (6.1).
        "Effective_Shock_Pct": ("=(1+in_Global_Price_Shock_Pct)*(1+" + xl.lookup(SS, "Sector_Price_Shock_Pct", "[@Sector]", "Sector")
                                + ")*(1+[@Market_Price_Shock_Pct])-1"),
        "Market_Price_After_Shock": '=IF([@Original_Market_Price]="","",[@Original_Market_Price]*(1+[@Effective_Shock_Pct]))',
        "Selected_Scenario_Market_Price": sel_price,
        "Fair_Value_After_Bias": '=IF([@Model_FV_Base]="","",[@Model_FV_Base]*(1+[@Fair_Value_Bias_Pct]))',
        "Fundamental_Case_FV": ('=IF([@Fundamental_Case]="Base",[@Model_FV_Base],IF([@Fundamental_Case]="Bear",[@Model_FV_Bear],'
                                'IF([@Fundamental_Case]="Bull",[@Model_FV_Bull],NA())))'),
        "Selected_Scenario_Fair_Value": sel_fv,
        "Implied_Upside_To_Fair_Value": ('=IF(OR([@Selected_Scenario_Fair_Value]="",NOT(ISNUMBER([@Selected_Scenario_Market_Price]))),"",'
                                         "[@Selected_Scenario_Fair_Value]/[@Selected_Scenario_Market_Price]-1)"),
        "Fair_Value_Gap": ('=IF(OR([@Fair_Value_After_Bias]="",[@Original_Market_Price]=""),"",'
                           "[@Fair_Value_After_Bias]/[@Original_Market_Price]-1)"),
        # D-023: the one Target Purchase Price reads only the selected fair value.
        "Target_Purchase_Price": ('=IF([@Selected_Scenario_Fair_Value]="","",'
                                  "[@Selected_Scenario_Fair_Value]*(1-[@Required_Margin_of_Safety_Pct]))"),
        "FV_Label": (f'=IF({fvm}={_q(F.MODEL_BASE.value)},"Model output (unmodified)",'
                     f'IF({fvm}={_q(F.FUNDAMENTAL.value)},"Model output – fundamental case "&[@Fundamental_Case],'
                     f'IF({fvm}={_q(F.MANUAL_BIAS.value)},"MANUALLY BIASED fair value ("&ROUND([@Fair_Value_Bias_Pct]*100,2)&"%)","")))'),
        "Control_Status": ('=IF(NOT(ISNUMBER([@Selected_Scenario_Market_Price])),'
                           f'IF({mode}={_q(M.ABSOLUTE.value)},"FAIL: absolute scenario price missing",'
                           '"FAIL: no market price at the price date"),'
                           'IF([@Selected_Scenario_Fair_Value]="","UNVALUED","OK"))'),
        "Control_Warning": warning,
    }


def _input_roles() -> dict[str, str]:
    return {c: "input" for c in ("Market_Price_Scenario_Mode", "Market_Price_Shock_Pct", "Absolute_Scenario_Price",
                                 "Fair_Value_Scenario_Mode", "Fair_Value_Bias_Pct")}


def _security_rows(data) -> list[dict]:
    rows = data.rows("security_registry")
    return sorted(rows, key=lambda r: r["Security_ID"]) if rows else []


def _control_value(sid: str, col: str):
    return PRICE_CONTROL_OVERRIDES.get((sid, col), DEFAULTS[col])


def build_scenario_sheet(ctx: WorkbookContext, data) -> None:
    ws = ctx.sheet(OWNER, SHEET)
    secs = [r["Security_ID"] for r in _security_rows(data)]
    n = max(len(secs), 1)
    xl.ws_note(ctx, SHEET, "A2", "Scenario controls (contract section 6). Blue = input, green = link, black = calculated. "
               "Prices and fair values are never overwritten; every scenario value is a separate column.", bold=True)
    xl.ws_note(ctx, SHEET, "A3", "Sector price shocks (default 0). Applied only in 'Market Price Shock' mode, once, from the original price.")

    # ---- tbl_SectorShocks: one row per Sector, default 0, blue input
    sector_rows = [[s.value, SECTOR_SHOCK_OVERRIDES.get(s.value, 0.0)] for s in Sector]
    ctx.add_table(OWNER, SHEET, TOP_SECTOR, 0, SS,
                  [TableColumn("Sector", role="imported"), TableColumn("Sector_Price_Shock_Pct", role="input", number="pct")],
                  sector_rows)
    ws.data_validation(TOP_SECTOR + 1, 1, TOP_SECTOR + len(sector_rows), 1,
                       {"validate": "decimal", "criteria": ">", "value": -1, "error_title": "Sector shock",
                        "error_message": "A decimal greater than -1 (-10% is -0.10)."})

    # ---- tbl_Nav_ControlsStatus: the Controls_At_Default check (placed above the control table)
    xl.ws_note(ctx, SHEET, f"A{TOP_STATUS}", "Reset status. Reset_* defaults sit to the right of tbl_PriceControls; "
               "copy them over the inputs, or regenerate the workbook, to return to default.", bold=True)
    status_cols = [
        TableColumn("Controls_At_Default", formula=(
            f"=AND([@Rows_Not_At_Default]=0,[@Sector_Shocks_Set]=0,in_Global_Price_Shock_Pct=[@Reset_Global_Price_Shock_Pct])")),
        TableColumn("Rows_Not_At_Default", formula=f"=COUNTIFS({DEF}[At_Default],FALSE)"),
        TableColumn("Sector_Shocks_Set", formula=f'=COUNTIFS({SS}[Sector_Price_Shock_Pct],"<>0",{SS}[Sector_Price_Shock_Pct],"<>")'),
        TableColumn("Reset_Global_Price_Shock_Pct", role="imported", number="pct"),
        TableColumn("Controls_With_Warning", formula=f'=COUNTIFS({PC}[Control_Warning],"?*")'),
        TableColumn("Controls_FAIL", formula=f'=COUNTIFS({PC}[Control_Status],"FAIL*")'),
        TableColumn("Controls_UNVALUED", formula=f'=COUNTIFS({PC}[Control_Status],"UNVALUED")'),
    ]
    cols = [TableColumn(c.header, formula=c.formula, role=(xl.role_of(c.formula, SHEET) if c.formula else c.role),
                        number="count" if c.formula and c.header != "Controls_At_Default" else "general") for c in status_cols]
    ctx.add_table(OWNER, SHEET, TOP_STATUS, 0, STATUS, cols, [[0.0]])

    # ---- tbl_PriceControls
    formulas = _price_control_formulas()
    cols = xl.schema_table_columns(S.PRICE_CONTROLS, formulas, _input_roles(), SHEET)
    rows = [[sid, _control_value(sid, "Market_Price_Scenario_Mode"), _control_value(sid, "Market_Price_Shock_Pct"),
             _control_value(sid, "Absolute_Scenario_Price"), _control_value(sid, "Fair_Value_Scenario_Mode"),
             _control_value(sid, "Fair_Value_Bias_Pct")] for sid in secs]
    ctx.add_table(OWNER, SHEET, TOP_PC, 0, PC, cols, rows)
    _validations(ws, cols, n)

    # ---- tbl_Nav_PriceDefaults: Reset_* columns and the per-row default check
    _defaults_table(ctx, secs)
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 28)
    for j, c in enumerate(cols[2:], start=2):
        ws.set_column(j, j, 20 if c.header not in ("FV_Label", "Control_Warning", "Control_Status") else 40)
    ws.freeze_panes(TOP_PC + 1, 1)


def _validations(ws, cols, n: int) -> None:
    first, last = TOP_PC + 1, TOP_PC + n
    idx = {c.header: i for i, c in enumerate(cols)}

    def dv(col, spec):
        ws.data_validation(first, idx[col], last, idx[col], spec)

    dv("Market_Price_Scenario_Mode", {"validate": "list", "source": M.values()})
    dv("Fair_Value_Scenario_Mode", {"validate": "list", "source": F.values()})
    dv("Fundamental_Case", {"validate": "list", "source": Case.values()})
    dv("Market_Price_Shock_Pct", {"validate": "decimal", "criteria": ">", "value": -1,
                                  "error_message": "A decimal greater than -1 (-10% is -0.10)."})
    dv("Fair_Value_Bias_Pct", {"validate": "decimal", "criteria": ">", "value": -1,
                               "error_message": "A decimal greater than -1 (-10% is -0.10)."})
    dv("Absolute_Scenario_Price", {"validate": "decimal", "criteria": ">", "value": 0, "ignore_blank": True,
                                   "error_message": "A positive price in INR, or blank."})
    mos = xl.col_name(0, idx["Required_Margin_of_Safety_Pct"])
    dv("Required_Margin_of_Safety_Pct", {"validate": "custom",
                                         "value": f"=AND(ISNUMBER({mos}{first + 1}),{mos}{first + 1}>=0,{mos}{first + 1}<1)",
                                         "error_message": "A decimal from 0 up to (not including) 1."})


def _defaults_table(ctx: WorkbookContext, secs: list[str]) -> None:
    pcm = lambda col: xl.lookup(PC, col, "[@Security_ID]", "Security_ID")      # noqa: E731
    same = [("Market_Price_Scenario_Mode", "Reset_Market_Price_Scenario_Mode"),
            ("Market_Price_Shock_Pct", "Reset_Market_Price_Shock_Pct"),
            ("Fair_Value_Scenario_Mode", "Reset_Fair_Value_Scenario_Mode"),
            ("Fundamental_Case", "Reset_Fundamental_Case"),
            ("Fair_Value_Bias_Pct", "Reset_Fair_Value_Bias_Pct"),
            ("Required_Margin_of_Safety_Pct", "Reset_Required_Margin_of_Safety_Pct")]
    checks = [f"{pcm(a)}=[@{b}]" for a, b in same]
    checks.append(f'{pcm("Absolute_Scenario_Price")}&""=[@Reset_Absolute_Scenario_Price]&""')   # blank = blank, never 0
    at_default = "=AND(" + ",".join(checks) + ")"
    cols = [
        TableColumn("Security_ID", role="imported"),
        TableColumn("Reset_Market_Price_Scenario_Mode", role="imported"),
        TableColumn("Reset_Market_Price_Shock_Pct", role="imported", number="pct"),
        TableColumn("Reset_Absolute_Scenario_Price", role="imported", number="inr"),
        TableColumn("Reset_Fair_Value_Scenario_Mode", role="imported"),
        TableColumn("Reset_Fundamental_Case", formula="=in_Global_Case", role="link"),
        TableColumn("Reset_Fair_Value_Bias_Pct", role="imported", number="pct"),
        TableColumn("Reset_Required_Margin_of_Safety_Pct", formula="=in_Default_MoS", role="link", number="pct"),
        TableColumn("At_Default", formula=at_default, role=xl.role_of(at_default, SHEET)),
    ]
    rows = [[sid, DEFAULTS["Market_Price_Scenario_Mode"], DEFAULTS["Market_Price_Shock_Pct"], None,
             DEFAULTS["Fair_Value_Scenario_Mode"], DEFAULTS["Fair_Value_Bias_Pct"]] for sid in secs]
    ctx.add_table(OWNER, SHEET, TOP_PC, DEFAULTS_LEFT, DEF, cols, rows)
