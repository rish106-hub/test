"""Bank valuation sheet template: one VAL_* sheet per bank security (brief item 2).

Every number on the sheet is a formula over interface tables (tbl_RawFinancials,
tbl_MarketPrices, tbl_CorporateActions, tbl_PeerSummary, tbl_Registry), the module's own
tbl_Assumptions and the in_* global inputs, except the few blue controls (grid steps,
reinvestment mode and rate, scenario probabilities). Every calculation is guarded so a missing
input gives a blank and a MISSING status, never 0 and never an error value. The Python reference
for the same sheet is src/valuations/bank_model.py; the test is
tests/valuations/test_sheet_matches_reference.py.

Layout (rows top to bottom): results (reserved at the top, written last), identity and dates,
cost of equity, anchor inputs, forecast calendar, interim results, dividends and share-count
actions after the anchor, equity bridge A -> V, freshness, roll-forward, blend weights,
peer-relative, expected-return settings, then one block per case (drivers, projection, RI, DDM,
justified P/B, values at V, expected return), sensitivity grids, history, chart zones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.common.enums import CheckResult as CR, CoverageStatus, ValuationMethod as M
from src.common.link_patterns import blank_safe
from src.common.units import DAYS_PER_YEAR_DISCOUNT, DAYS_PER_YEAR_XIRR, INR_PER_CRORE
from src.valuations import history as H
from src.valuations import parameters as P
from src.valuations.bank_model import (BRIDGE_HORIZON_FAIL, ER_HORIZON_FAIL, ER_NO_EXIT_PB, ER_NO_PRICE,
                                       EXIT_HORIZON_MONTHS, GROWTH_STEPS, NOT_REINVESTED, PROBABILITIES_NOT_ENTERED,
                                       RATE_STEPS, REINVESTED, REINVESTMENT_MODES, ROE_STEPS)
from src.valuations.blend import WEIGHT_SUM_TOL
from src.valuations.expected_return import PROBABILITY_SUM_TOL
from src.valuations.inputs import (ANCHOR_METRICS, HISTORY_FY_METRICS, HISTORY_Q_METRICS, PRIMARY_METHOD,
                                   SECONDARY_METHODS, BankSpec)
from src.valuations.layout import Grid, add_status_highlighting

MONTHS_PER_YEAR = 12          # EDATE step between fiscal year ends
MONTHS_PER_QUARTER = 3
NA_G_GE_R = "n/a (g ≥ r)"    # contract §10 TV-5
NM_TEXT = "Not Meaningful"
NM_REASON = ("Deposit-taking bank: deposits are funding raw material, not financing, so enterprise value and "
             "EBITDA/revenue are not defined consistently (spec <multiple_validity>). Not computed.")

N = P.FORECAST_YEARS
C_LABEL, C_TAG, C0 = 0, 1, 2           # label, unit/tag, anchor / scalar value
C_SRC, C_RAT, C_STAT = 3 + N, 4 + N, 5 + N   # source type, rationale, status (after year columns)
RESULTS_ROWS = 44                       # reserved at the top of the sheet
CHART_IDS = {
    "G001": "Operating income (NII + non-interest income): annual and quarterly trend",
    "G002": "Operating income growth: YoY and CAGR",
    "G003": "Net profit and earnings growth",
    "G004": "EPS history and Base-case forecast EPS (Modelled, not consensus)",
    "G005": "Book value per share (history and Base-case forecast)",
    "G006": "Five-year historical versus projected performance",
    "G007": "Actual versus forecast trends, forecast transition marked at the anchor",
    "V002": "Current price vs Base, Bear and Bull fair value at the valuation date",
    "V003": "Historical P/E trend and current P/E (on FY EPS at the anchor)",
    "V004": "Forward P/E on modelled EPS (label Modelled, never consensus)",
    "V005": "Historical P/B trend",
    "V006": "Historical P/ABV trend (needs net NPA; missing-data notice until supplied)",
    "V007": "EV/EBITDA: Not Meaningful for deposit-taking banks; render the NM notice, no chart",
    "V008": "EV/Revenue: Not Meaningful for deposit-taking banks; render the NM notice, no chart",
    "V009": "EPS trend vs share-price performance",
    "V010": "Modelled earnings growth and implied valuation multiples",
    "V011": "Valuation sensitivity heatmap (r_e x g and r_e x ROE_T grids on this sheet)",
    "V012": "Bull, Base and Bear valuation comparison",
    "B001": "NIM history (reported) and forecast (driver)",
    "B002": "RoA and RoE history and forecast",
    "B003": "Gross and net NPA trends",
    "B004": "Credit cost and slippage trends",
    "B005": "Credit growth vs deposit growth",
    "B006": "CASA ratio and cost of deposits (proxy)",
    "B007": "Capital adequacy and CET1 trends",
    "B008": "P/B, P/ABV and P/E vs comparable banks (tbl_PeerSummary, 04-charts)",
    "B009": "Historical vs projected earnings and book value per share",
}


def q(text: str) -> str:
    """Excel string literal."""
    return '"' + str(text).replace('"', '""') + '"'


def obs_link(observation_id: str, col: str = "Value") -> str:
    return blank_safe("tbl_RawFinancials", col, key=q(observation_id), key_col="Observation_ID")


def assumption_link(assumption_id: str, col: str = "Value") -> str:
    return blank_safe("tbl_Assumptions", col, key=q(assumption_id), key_col="Assumption_ID")


def action_link(action_id: str, col: str) -> str:
    return blank_safe("tbl_CorporateActions", col, key=q(action_id), key_col="Action_ID")


@dataclass
class BuiltSheet:
    spec: BankSpec
    grid: Grid
    history_cells: dict[tuple[str, str, str], str] = field(default_factory=dict)   # (block, metric, label) -> cell
    forecast_cells: dict[tuple[str, int], str] = field(default_factory=dict)        # (metric, t) -> cell (Base)

    def ext(self, key: str) -> str:
        return self.grid.ext(key)


class BankSheetBuilder:
    def __init__(self, ctx, spec: BankSpec, link_peers: bool = True):
        self.ctx, self.s, self.link_peers = ctx, spec, link_peers
        self.g = Grid(ctx, spec.sheet)
        self.built = BuiltSheet(spec, self.g)
        self.row = RESULTS_ROWS + 4

    # ------------------------------------------------------------------ helpers
    def r(self, key: str) -> str:
        return self.g.ref(key)

    def yr(self, key: str, t: int) -> str:
        return self.g.ref(f"{key}.{t}")

    def year_range(self, key: str, first: int = 1, last: int = N) -> str:
        return f"{self.yr(key, first)}:{self.yr(key, last)}"

    def section(self, title: str, note: str = ""):
        self.row += 1
        self.g.label(self.row, C_LABEL, title, "h1")
        for c in range(1, C_STAT + 1):
            self.g.label(self.row, c, "", "h1")
        if note:
            self.row += 1
            self.g.label(self.row, C_LABEL, note, "note")
        self.row += 1

    def line(self, label: str, tag: str = "") -> int:
        self.g.label(self.row, C_LABEL, label)
        if tag:
            self.g.label(self.row, C_TAG, tag, "tag")
        r = self.row
        self.row += 1
        return r

    def year_header(self, title: str = "", with_anchor: bool = True):
        r = self.row
        if title:
            self.g.label(r, C_LABEL, title, "h2")
        if with_anchor:
            self.g.label(r, C0, f"{self.s.anchor_date and 'FY' + str(self.s.anchor_date.year) or 'Anchor'} (A)", "colhead")
        for t in range(1, N + 1):
            lab = self.s.fy_labels[t - 1] + "E" if self.s.fy_labels else f"Year {t}"
            self.g.label(r, C0 + t, lab, "colhead")
        self.row += 1

    # ------------------------------------------------------------------ build
    def build(self) -> BuiltSheet:
        s, g = self.s, self.g
        ws = g.ws
        ws.set_column(C_LABEL, C_LABEL, 58)
        ws.set_column(C_TAG, C_TAG, 13)
        ws.set_column(C0, C0 + N, 14)
        ws.set_column(C_SRC, C_SRC, 26)
        ws.set_column(C_RAT, C_RAT, 60)
        ws.set_column(C_STAT, C_STAT, 16)
        g.label(1, C_LABEL, f"{s.sheet}: {s.company_name} ({s.security_id}). Bank valuation, Residual Income primary "
                            "(R004)", "title")
        g.label(2, C_LABEL, "Every number is a formula. Drivers are edited in tbl_Assumptions on VALUATION_ASSUMPTIONS "
                            "(blue); this sheet links to them (green). A blank is a missing input, shown as MISSING, "
                            "never 0.", "note")
        self.identity()
        self.cost_of_equity()
        self.anchor_inputs()
        self.calendar()
        self.interims()
        self.dividends()
        self.share_actions()
        self.weights()
        self.peers()
        self.er_settings()
        for case in P.CASES:
            self.case_block(case)
        self.bridge()          # needs the Base EPS row
        self.freshness_and_roll()
        for case in P.CASES:
            self.case_values(case)   # needs the roll-forward
        self.sensitivity()
        self.results()
        self.history()
        self.chart_zones()
        add_status_highlighting(self.ctx, ws, 0, C0, self.row + 200, C_STAT + 30)
        return self.built

    # ------------------------------------------------------------------ identity
    def identity(self):
        s, g = self.s, self.g
        self.section("Identity and the five model dates (contract §0.1)",
                     "A = reported fiscal-year balance sheet (historical). V = valuation date. They are never merged.")
        sid_cell = g.value(self.line("Security_ID (join key)"), C0, s.security_id, key="sid")
        reg = lambda col: blank_safe("tbl_Registry", col, key=sid_cell)  # noqa: E731
        g.formula(self.line("Entity_ID"), C0, reg("Entity_ID"), role="link", key="entity")
        g.formula(self.line("Company name"), C0, reg("Company_Name"), role="link")
        g.formula(self.line("ISIN"), C0, reg("ISIN"), role="link")
        g.formula(self.line("Business model"), C0, reg("Business_Model"), role="link")
        g.formula(self.line("Registry primary valuation method"), C0, reg("Primary_Valuation_Method"), role="link")
        g.value(self.line("Primary method (this template)"), C0, PRIMARY_METHOD, key="method")
        g.value(self.line("Secondary methods (cross-checks)"), C0, "; ".join(SECONDARY_METHODS))
        g.value(self.line("R004 method check"), C0, s.method_check, key="method_check")
        g.value(self.line("Accounting basis (one basis per valuation)"), C0, s.basis, key="basis")
        anchor = s.anchor_obs.get("COMMON_EQUITY")
        r = self.line("Anchor date A: reported balance sheet (historical)", "Reported")
        if anchor:
            g.formula(r, C0, obs_link(anchor.observation_id, "Period_End"), role="link", number="date", key="A")
        else:
            g.value(r, C0, None, number="date", key="A")
            g.label(r, C_RAT, "No fiscal-year COMMON_EQUITY observation on or before V: model cannot run", "note")
        g.formula(self.line("Valuation date V (in_Valuation_Date)"), C0,
                  'IF(in_Valuation_Date="","",in_Valuation_Date)', role="link", number="date", key="V")
        g.formula(self.line("Price date (in_Price_Date)"), C0, 'IF(in_Price_Date="","",in_Price_Date)', role="link",
                  number="date", key="PD")
        A, V = self.r("A"), self.r("V")
        g.formula(self.line("Dates valid: A and V present, A <= V"), C0,
                  f"IF(AND(ISNUMBER({A}),ISNUMBER({V})),{A}<={V},FALSE)", key="ok_dates")
        self.R_row = self.line("Latest results period end R (interim included)", "Reported")
        crit = (f"tbl_MarketPrices[Security_ID],{sid_cell},tbl_MarketPrices[Price_Date],{self.r('PD')}")
        g.formula(self.line("Current market price at the price date", "INR"), C0,
                  f'IF(COUNTIFS({crit})=1,SUMIFS(tbl_MarketPrices[Close_INR],{crit}),"")', role="link", number="inr",
                  key="price")
        g.formula(self.line("Market price status"), C0, f'IF({self.r("price")}="","MISSING","PASS")',
                  key="price_status")

    def assumption_cell(self, row: int, col: int, arow: P.AssumptionRow | None, number: str, key: str) -> str:
        if arow is None:
            return self.g.value(row, col, None, role="link", number=number, key=key)
        return self.g.formula(row, col, assumption_link(arow.assumption_id), role="link", number=number, key=key)

    def provenance(self, row: int, arow: P.AssumptionRow | None, note: str = ""):
        """Source type and rationale of the resolved assumption row, linked from tbl_Assumptions."""
        if arow is None:
            self.g.label(row, C_SRC, "MISSING", "label_b")
            self.g.label(row, C_RAT, "No row in tbl_Assumptions: input blank, dependent outputs blank", "note")
            return
        self.g.formula(row, C_SRC, assumption_link(arow.assumption_id, "Assumption_Source_Type"), role="link")
        self.g.formula(row, C_RAT, assumption_link(arow.assumption_id, "Rationale"), role="link")
        if note:
            self.g.label(row, C_STAT, note, "note")

    def cost_of_equity(self):
        g = self.g
        self.section("Cost of equity (contract §2): r_e = Rf + beta x ERP",
                     "Rf and ERP are global inputs; beta is a per-security assumption. Blank -> r_e blank.")
        g.formula(self.line("Risk-free rate Rf (in_Risk_Free_Rate)", "decimal"), C0,
                  'IF(in_Risk_Free_Rate="","",in_Risk_Free_Rate)', role="link", number="pct", key="rf")
        g.formula(self.line("Equity risk premium ERP (in_Equity_Risk_Premium)", "decimal"), C0,
                  'IF(in_Equity_Risk_Premium="","",in_Equity_Risk_Premium)', role="link", number="pct", key="erp")
        arow = self.s.security_inputs.get("BETA")
        r = self.line(P.BETA.label, "x")
        self.assumption_cell(r, C0, arow, "multiple", "beta")
        self.provenance(r, arow)
        rf, beta, erp = self.r("rf"), self.r("beta"), self.r("erp")
        g.formula(self.line("Cost of equity r_e", "decimal"), C0,
                  f'IF(COUNT({rf},{beta},{erp})=3,{rf}+{beta}*{erp},"")', number="pct", key="re")

    # ------------------------------------------------------------------ anchor
    def anchor_inputs(self):
        s, g = self.s, self.g
        self.section("Anchor-year inputs at A (reported, as of A; contract §3.1, §3.6)",
                     "Linked by Observation_ID from tbl_RawFinancials. Columns: value, Observation_ID, Source_ID, "
                     "period end, basis, status.")
        labels = {"COMMON_EQUITY": ("Common equity", "INR_Cr", "inr_cr"),
                  "DILUTED_SHARES": ("Diluted shares", "count", "count"),
                  "BANK_NET_ADVANCES": ("Net advances", "INR_Cr", "inr_cr"),
                  "BANK_NON_II": ("Non-interest income, FY at A", "INR_Cr", "inr_cr"),
                  "BANK_OPEX": ("Operating expenses, FY at A", "INR_Cr", "inr_cr"),
                  "EPS_DILUTED": ("Diluted EPS, FY at A (for trailing P/E)", "INR", "inr")}
        keys = {"COMMON_EQUITY": "eq0", "DILUTED_SHARES": "sh0", "BANK_NET_ADVANCES": "adv0", "BANK_NON_II": "nonii0",
                "BANK_OPEX": "opex0", "EPS_DILUTED": "epsA"}
        for m in ANCHOR_METRICS:
            lab, unit, number = labels[m]
            r = self.line(f"{lab} [{m}]", unit)
            ob = s.anchor_obs.get(m)
            if ob is None:
                g.value(r, C0, None, role="link", number=number, key=keys[m])
                g.label(r, C0 + 1, "MISSING", "label_b")
                continue
            g.formula(r, C0, obs_link(ob.observation_id), role="link", number=number, key=keys[m])
            g.value(r, C0 + 1, ob.observation_id)
            g.formula(r, C0 + 2, obs_link(ob.observation_id, "Source_ID"), role="link")
            g.formula(r, C0 + 3, obs_link(ob.observation_id, "Period_End"), role="link", number="date")
            g.formula(r, C0 + 4, obs_link(ob.observation_id, "Accounting_Basis"), role="link")
            g.formula(r, C0 + 5, f'IF({g.addr(r, C0)}="","MISSING","PASS")')
        arow = s.security_inputs.get("IEA_TO_ADV_ANCHOR")
        r = self.line(P.IEA_TO_ADV_ANCHOR.label, "x")
        self.assumption_cell(r, C0, arow, "multiple", "iea0")
        self.provenance(r, arow)
        eq, sh = self.r("eq0"), self.r("sh0")
        r = self.line("Book value per diluted share at A, BV_0", "INR")
        g.formula(r, C0, f'IF(AND(COUNT({eq},{sh})=2,{sh}<>0),{eq}*{INR_PER_CRORE}/{sh},"")', number="inr", key="bv0")
        g.formula(r, C0 + 1, f'IF(ISNUMBER({self.r("A")}),"Reported BVPS as of "&TEXT({self.r("A")},"yyyy-mm-dd"),'
                             f'"Reported BVPS as of A (missing)")', key="bv0_caption")
        base = [self.r(k) for k in ("eq0", "sh0", "adv0", "nonii0", "opex0", "iea0")]
        g.formula(self.line("Anchor inputs complete (5 reported + IEA ratio)"), C0,
                  f"COUNT({','.join(base)})=6", key="base_ready")

    def calendar(self):
        g = self.g
        self.section("Forecast calendar: fiscal year ends after A (contract §2: year t cash flows at FYE_t)")
        self.year_header()
        r = self.line("Fiscal year end FYE_t", "date")
        g.formula(r, C0, f'IF(ISNUMBER({self.r("A")}),{self.r("A")},"")', number="date", key="fye.0")
        for t in range(1, N + 1):
            prev = g.addr(r, C0 + t - 1)
            g.formula(r, C0 + t, f'IF(ISNUMBER({prev}),EDATE({prev},{MONTHS_PER_YEAR}),"")', number="date",
                      key=f"fye.{t}")
        r = self.line("Year index t")
        for t in range(1, N + 1):
            g.formula(r, C0 + t, f'IF(ISNUMBER({self.yr("fye", t)}),YEAR({self.yr("fye", t)})-YEAR({self.r("A")}),"")',
                      key=f"t.{t}")
        r = self.line("Days in fiscal year t")
        for t in range(1, N + 1):
            g.formula(r, C0 + t, f'IF(ISNUMBER({self.yr("fye", t)}),{self.yr("fye", t)}-{self.yr("fye", t - 1)},"")',
                      key=f"days.{t}")

    # ------------------------------------------------------------------ after-anchor events
    def _slots(self, n: int) -> list[int]:
        rows = list(range(self.row, self.row + max(n, 1)))
        self.row += max(n, 1)
        return rows

    def interims(self):
        s, g = self.s, self.g
        self.section("Reported interim results after A (discrete quarters; contract §3.1a)",
                     "Columns: period end, diluted EPS (reported), Observation_ID, Source_ID, in (A, V].")
        rows = self._slots(len(s.interims))
        A, V = self.r("A"), self.r("V")
        for i, r in enumerate(rows):
            if i < len(s.interims):
                ob = s.interims[i]
                g.label(r, C_LABEL, f"{ob.fiscal_label or ob.period_end.isoformat()} diluted EPS")
                g.label(r, C_TAG, "Reported", "tag")
                g.formula(r, C0, obs_link(ob.observation_id, "Period_End"), role="link", number="date")
                g.formula(r, C0 + 1, obs_link(ob.observation_id), role="link", number="inr")
                g.value(r, C0 + 2, ob.observation_id)
                g.formula(r, C0 + 3, obs_link(ob.observation_id, "Source_ID"), role="link")
            else:
                g.label(r, C_LABEL, "No interim results reported after A")
            pe = g.addr(r, C0)
            g.formula(r, C0 + 4, f"IF(AND(ISNUMBER({pe}),ISNUMBER({A}),ISNUMBER({V})),AND({pe}>{A},{pe}<={V}),FALSE)")
        self.int_pe = g.rng(rows[0], C0, rows[-1], C0)
        self.int_eps = g.rng(rows[0], C0 + 1, rows[-1], C0 + 1)
        ok = self.r("ok_dates")
        g.formula(self.R_row, C0, f'IF({ok},MAX({A},MAXIFS({self.int_pe},{self.int_pe},">"&{A},{self.int_pe},'
                                  f'"<="&{V})),"")', number="date", key="R")

    def dividends(self):
        s, g = self.s, self.g
        self.section("Dividends with ex-date after A (tbl_CorporateActions; contract §3.1)",
                     "Columns: ex-date, DPS (reported), Action_ID, Source_ID, in (A, V], amount deducted (0 outside).")
        rows = self._slots(len(s.dividends))
        A, V = self.r("A"), self.r("V")
        for i, r in enumerate(rows):
            if i < len(s.dividends):
                d = s.dividends[i]
                g.label(r, C_LABEL, f"Dividend ex {d.ex_date.isoformat()}")
                g.label(r, C_TAG, "Reported", "tag")
                g.formula(r, C0, action_link(d.action_id, "Ex_Date"), role="link", number="date")
                if d.dps is None:
                    g.value(r, C0 + 1, None, role="link", number="inr")
                    g.label(r, C_RAT, f"FAIL: amount {d.raw!r} is not a number; not deducted", "label_b")
                else:
                    g.formula(r, C0 + 1, f"VALUE({action_link(d.action_id, 'Ratio_or_Amount')})", role="link",
                              number="inr")
                g.value(r, C0 + 2, d.action_id)
                g.formula(r, C0 + 3, action_link(d.action_id, "Source_ID"), role="link")
            else:
                g.label(r, C_LABEL, "No dividend with ex-date after A")
            ex, dps = g.addr(r, C0), g.addr(r, C0 + 1)
            g.formula(r, C0 + 4, f"IF(AND(ISNUMBER({ex}),ISNUMBER({A}),ISNUMBER({V})),AND({ex}>{A},{ex}<={V}),FALSE)")
            g.formula(r, C0 + 5, f"IF(AND({g.addr(r, C0 + 4)},ISNUMBER({dps})),{dps},0)", number="inr")
        self.div_ex = g.rng(rows[0], C0, rows[-1], C0)
        self.div_dps = g.rng(rows[0], C0 + 1, rows[-1], C0 + 1)
        self.div_incl = g.rng(rows[0], C0 + 5, rows[-1], C0 + 5)

    def share_actions(self):
        s, g = self.s, self.g
        self.section("Share-count actions after A (split, bonus, rights, merger)",
                     "One inside (A, V] means per-share anchor values need normalising first: FAIL.")
        rows = self._slots(len(s.share_actions))
        A, V = self.r("A"), self.r("V")
        for i, r in enumerate(rows):
            if i < len(s.share_actions):
                aid, kind, ex = s.share_actions[i]
                g.label(r, C_LABEL, f"{kind} ex {ex.isoformat()}")
                g.formula(r, C0, action_link(aid, "Ex_Date"), role="link", number="date")
                g.formula(r, C0 + 1, action_link(aid, "Ratio_or_Amount"), role="link")
                g.value(r, C0 + 2, aid)
            else:
                g.label(r, C_LABEL, "No share-count action after A")
            ex = g.addr(r, C0)
            g.formula(r, C0 + 4, f"IF(AND(ISNUMBER({ex}),ISNUMBER({A}),ISNUMBER({V})),AND({ex}>{A},{ex}<={V}),FALSE)")
        flags = g.rng(rows[0], C0 + 4, rows[-1], C0 + 4)
        g.formula(self.line("Share-count check"), C0, f'IF(SUMPRODUCT(({flags}=TRUE)*1)>0,"FAIL","PASS")',
                  key="share_status")

    # ------------------------------------------------------------------ common settings
    def weights(self):
        g = self.g
        self.section("Blend weights (contract §3.8, D-009)",
                     "Default: 100% Residual Income; other methods are cross-checks. Weights >= 0 and sum to 1.")
        keys = []
        for p in P.WEIGHT_PARAMETERS:
            arow = self.s.weights.get(p.code)
            r = self.line(p.label, "decimal")
            self.assumption_cell(r, C0, arow, "pct", f"w.{P.METHOD_OF_WEIGHT[p.code]}")
            self.provenance(r, arow)
            keys.append(self.r(f"w.{P.METHOD_OF_WEIGHT[p.code]}"))
        rng = f"{keys[0]}:{keys[-1]}"
        g.formula(self.line("Weights check"), C0,
                  f'IF(COUNT({rng})=4,IF(AND(ABS(SUM({rng})-1)<={WEIGHT_SUM_TOL},MIN({rng})>=0),"PASS","FAIL"),"FAIL")',
                  key="w_status")
        g.formula(self.line("Weights valid"), C0, f'{self.r("w_status")}="PASS"', key="w_ok")

    def peers(self):
        s, g = self.s, self.g
        self.section("Peer-relative P/B (contract §3.5; tbl_PeerSummary from 04-charts)",
                     "Median P/B of the peer group excluding this security, times BV per share at A (on BV at A). "
                     "Stated at the price date, not rolled forward. N_Valid = 0 -> blank, MISSING.")
        g.value(self.line("Peer group"), C0, s.peer_group_id or "(none)", key="peer_group")
        if not self.link_peers:
            note = ("tbl_PeerSummary not linked: 04-charts delivers peer groups after gate G1 (D-028). Cross-check "
                    "blank, weight 0 (D-009).")
            for label, key in (("Matching tbl_PeerSummary rows", "peer_rows"), ("N_Valid (peers with a valid P/B)",
                                                                                 "peer_n"),
                               ("Peer median P/B", "peer_median")):
                r = self.line(label)
                g.value(r, C0, None, role="link", key=key)
                g.label(r, C_RAT, note, "note")
            g.formula(self.line("Peer flag"), C0, '"MISSING"', key="peer_flag")
            g.formula(self.line("Peer-relative value (on BV at A, at the price date)", "INR"), C0, '""', number="inr",
                      key="peer_v")
            return
        grp, sid = self.r("peer_group"), self.r("sid")
        crit = (f"tbl_PeerSummary[Peer_Group_ID],{grp},tbl_PeerSummary[Metric_ID],{q('PB')},"
                f"tbl_PeerSummary[Exclude_Security_ID],{sid}")
        g.formula(self.line("Matching tbl_PeerSummary rows"), C0, f"COUNTIFS({crit})", role="link", key="peer_rows")
        rows = self.r("peer_rows")
        g.formula(self.line("N_Valid (peers with a valid P/B)"), C0,
                  f"IF({rows}=1,SUMIFS(tbl_PeerSummary[N_Valid],{crit}),0)", role="link", key="peer_n")
        num = (f"SUMPRODUCT((tbl_PeerSummary[Peer_Group_ID]={grp})*(tbl_PeerSummary[Metric_ID]={q('PB')})"
               f"*(tbl_PeerSummary[Exclude_Security_ID]={sid})*ISNUMBER(tbl_PeerSummary[Median]))")
        g.formula(self.line("Peer median P/B", "x"), C0,
                  f'IF(AND({rows}=1,{num}=1),SUMIFS(tbl_PeerSummary[Median],{crit}),"")', role="link",
                  number="multiple", key="peer_median")
        med, n, bv0 = self.r("peer_median"), self.r("peer_n"), self.r("bv0")
        g.formula(self.line("Peer flag"), C0,
                  f'IF(OR({n}=0,{med}="",{bv0}=""),"MISSING",IF({n}<in_Peer_Min_N,"WARNING","PASS"))', key="peer_flag")
        g.formula(self.line("Peer-relative value (on BV at A, at the price date)", "INR"), C0,
                  f'IF({self.r("peer_flag")}="MISSING","",{med}*{bv0})', number="inr", key="peer_v")

    def er_settings(self):
        g = self.g
        self.section("Expected five-year return settings (contract §8)",
                     "Exit at V + 5 years. Probabilities are blank by default and never invented.")
        r = self.line("Reinvestment mode")
        g.value(r, C0, NOT_REINVESTED, role="input", key="er_mode")
        g.ws.data_validation(r, C0, r, C0, {"validate": "list", "source": list(REINVESTMENT_MODES)})
        g.value(self.line("Dividend reinvestment rate r_reinv (blank = not used)", "decimal"), C0, None, role="input",
                number="pct", key="r_reinv")
        for c in P.CASES:
            g.value(self.line(f"Scenario probability p_{c} (user input, blank by default)", "decimal"), C0, None,
                    role="input", number="pct", key=f"p.{c}")
        ok, V, A = self.r("ok_dates"), self.r("V"), self.r("A")
        g.formula(self.line("Exit date T = V + 5 years"), C0,
                  f'IF({ok},EDATE({V},{EXIT_HORIZON_MONTHS}),"")', number="date", key="T")
        T = self.r("T")
        g.formula(self.line("Exit date inside the forecast horizon"), C0,
                  f"IF({ok},AND({T}>={A},{T}<{self.yr('fye', N)}),FALSE)", key="in_horizon")

    # ------------------------------------------------------------------ cases
    def case_block(self, case: str):
        s, g = self.s, self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        self.section(f"{case} case: drivers (contract §3.6, D-008: a complete driver set, never Base x (1 +/- k))",
                     "Each cell links to the resolved tbl_Assumptions row. Columns after the years: source type, "
                     "rationale (year-1 row), status.")
        self.year_header(with_anchor=False)
        required_ranges = []
        for p in P.DRIVER_PARAMETERS:
            r = self.line(p.label, p.unit)
            ids = set()
            for t in range(1, N + 1):
                arow = s.drivers[(case, p.code, t)]
                self.assumption_cell(r, C0 + t, arow, p.number, f"{k('d.' + p.code)}.{t}")
                if arow:
                    ids.add(arow.assumption_id)
            first = s.drivers[(case, p.code, 1)]
            self.provenance(r, first)
            rng = self.year_range(k("d." + p.code))
            if p.required:
                required_ranges.append(rng)
                g.formula(r, C_STAT, f'IF(COUNT({rng})={N},"PROVIDED","MISSING")')
            else:
                g.label(r, C_STAT, "optional: blank = unchanged", "note")
            if len(ids) > 1:
                g.label(r, C_STAT + 1, f"{len(ids)} rows by year: see VALUATION_ASSUMPTIONS", "note")
        self.row += 1
        g.label(self.row, C_LABEL, f"{case} case: terminal and exit assumptions", "h2")
        self.row += 1
        for p in P.TERMINAL_PARAMETERS:
            arow = s.terminal[(case, p.code)]
            r = self.line(p.label, p.unit)
            self.assumption_cell(r, C0, arow, p.number, k("tr." + p.code))
            self.provenance(r, arow)
            g.formula(r, C_STAT, f'IF(ISNUMBER({self.r(k("tr." + p.code))}),"PROVIDED",'
                                 f'{q("MISSING" if p.required else "optional: blank = no expected return")})')
        cnt = "+".join(f"COUNT({x})" for x in required_ranges)
        n_req = sum(1 for p in P.DRIVER_PARAMETERS if p.required) * N
        g.formula(self.line(f"{case}: driver set complete"), C0,
                  f"AND({self.r('base_ready')},{cnt}={n_req})", key=k("ready_proj"))
        g.formula(self.line(f"{case}: ready to value (drivers, r_e, dates)"), C0,
                  f"AND({self.r(k('ready_proj'))},ISNUMBER({self.r('re')}),{self.r('ok_dates')})", key=k("ready"))
        self.projection(case)
        self.residual_income(case)
        self.ddm_and_jpb(case)

    def projection(self, case: str):
        g = self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        rp = self.r(k("ready_proj"))
        self.row += 1
        self.year_header(f"{case}: projection (INR crore; per share in INR)")
        d = lambda code, t: self.yr(k("d." + code), t)  # noqa: E731
        p = lambda name, t: g.addr(rows[name][0], C0 + t)  # noqa: E731  (address known before it is written)
        rows = {}
        for name, label, unit, number in [
                ("adv", "Advances", "INR_Cr", "inr_cr"), ("iea", "Interest-earning assets", "INR_Cr", "inr_cr"),
                ("nii", "Net interest income", "INR_Cr", "inr_cr"), ("nonii", "Non-interest income", "INR_Cr", "inr_cr"),
                ("opex", "Operating expenses", "INR_Cr", "inr_cr"), ("ppop", "Pre-provision operating profit", "INR_Cr",
                                                                     "inr_cr"),
                ("prov", "Provisions (credit cost x average advances)", "INR_Cr", "inr_cr"),
                ("pat", "Profit after tax", "INR_Cr", "inr_cr"), ("sh", "Diluted shares", "count", "count"),
                ("eps", "EPS (Modelled, not consensus)", "INR", "inr"), ("dps", "DPS", "INR", "inr"),
                ("eq", "Common equity", "INR_Cr", "inr_cr"), ("bvps", "BVPS (equity / shares)", "INR", "inr"),
                ("roe", "RoE (PAT / average equity)", "decimal", "pct")]:
            rows[name] = (self.line(label, unit), number)
        base_ready = self.r("base_ready")
        anchors = {"adv": "adv0", "nonii": "nonii0", "opex": "opex0", "sh": "sh0", "eq": "eq0", "bvps": "bv0"}
        for name, (r, number) in rows.items():
            if name in anchors:
                g.formula(r, C0, f'IF({base_ready},{self.r(anchors[name])},"")', number=number, key=f"{k('p.' + name)}.0")
            elif name == "iea":
                g.formula(r, C0, f'IF({base_ready},{self.r("adv0")}*{self.r("iea0")},"")', number=number,
                          key=f"{k('p.iea')}.0")
        for t in range(1, N + 1):
            f = {
                "adv": f"{p('adv', t - 1)}*(1+{d('ADV_GROWTH', t)})",
                "iea": f"{p('adv', t)}*{d('IEA_TO_ADV', t)}",
                "nii": f"{d('NIM', t)}*({p('iea', t - 1)}+{p('iea', t)})/2",
                "nonii": f"{p('nonii', t - 1)}*(1+{d('NONII_GROWTH', t)})",
                "opex": f"{p('opex', t - 1)}*(1+{d('OPEX_GROWTH', t)})",
                "ppop": f"{p('nii', t)}+{p('nonii', t)}-{p('opex', t)}",
                "prov": f"{d('CREDIT_COST', t)}*({p('adv', t - 1)}+{p('adv', t)})/2",
                "pat": f"({p('ppop', t)}-{p('prov', t)})*(1-{d('TAX_RATE', t)})",
                "sh": f"IF({d('DILUTED_SHARES', t)}=\"\",{p('sh', t - 1)},{d('DILUTED_SHARES', t)})",
                "eps": f"{p('pat', t)}*{INR_PER_CRORE}/{p('sh', t)}",
                "dps": f"{p('eps', t)}*{d('PAYOUT', t)}",
                "eq": f"{p('eq', t - 1)}+{p('pat', t)}-{p('dps', t)}*{p('sh', t)}/{INR_PER_CRORE}",
                "bvps": f"{p('eq', t)}*{INR_PER_CRORE}/{p('sh', t)}",
                "roe": f"{p('pat', t)}/(({p('eq', t - 1)}+{p('eq', t)})/2)",
            }
            for name, (r, number) in rows.items():
                g.formula(r, C0 + t, f'IF({rp},{f[name]},"")', number=number, key=f"{k('p.' + name)}.{t}")
        if case == "Base":
            metric_of = {"adv": "BANK_NET_ADVANCES", "nii": "BANK_NII", "nonii": "BANK_NON_II", "opex": "BANK_OPEX",
                         "ppop": "BANK_PPOP", "prov": "BANK_PROVISIONS", "pat": "NET_PROFIT_COMMON",
                         "sh": "DILUTED_SHARES", "eps": "EPS_DILUTED", "dps": "DPS", "eq": "COMMON_EQUITY",
                         "bvps": "BVPS", "roe": "ROE"}
            for name, metric in metric_of.items():
                for t in range(1, N + 1):
                    self.built.forecast_cells[(metric, t)] = self.g.ext(f"{k('p.' + name)}.{t}")
            for t in range(1, N + 1):
                self.built.forecast_cells[("BANK_NIM", t)] = self.g.ext(f"{k('d.NIM')}.{t}")
                self.built.forecast_cells[("BANK_CREDIT_COST", t)] = self.g.ext(f"{k('d.CREDIT_COST')}.{t}")

    def residual_income(self, case: str):
        g = self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        rp, ready, re = self.r(k("ready_proj")), self.r(k("ready")), self.r("re")
        roe_t, gr = self.r(k("tr.TERMINAL_ROE")), self.r(k("tr.TERMINAL_GROWTH"))
        self.row += 1
        self.year_header(f"{case}: Residual Income (contract §3.2)")
        g.formula(self.line("RI computable: inputs ready, ROE_T and g entered, g < r_e (TV-1)"), C0,
                  f"IF({ready},AND(ISNUMBER({roe_t}),ISNUMBER({gr}),{gr}<{re}),FALSE)", key=k("ri_ok"))
        ok = self.r(k("ri_ok"))
        g.formula(self.line("Terminal check (g < r_e)"), C0,
                  f'IF(NOT({ready}),"MISSING",IF(COUNT({roe_t},{gr})<2,"MISSING",IF({gr}<{re},"PASS","FAIL")))',
                  key=k("tv_status"))
        rbv = self.line("Book value per share, clean surplus BV_t = BV_t-1 + EPS - DPS", "INR")
        g.formula(rbv, C0, f'IF({rp},{self.r("bv0")},"")', number="inr", key=f"{k('bv')}.0")
        eps = lambda t: self.yr(k("p.eps"), t)  # noqa: E731
        dps = lambda t: self.yr(k("p.dps"), t)  # noqa: E731
        bv = lambda t: self.yr(k("bv"), t)  # noqa: E731
        for t in range(1, N + 1):
            g.formula(rbv, C0 + t, f'IF({rp},{bv(t - 1)}+{eps(t)}-{dps(t)},"")', number="inr", key=f"{k('bv')}.{t}")
        rri = self.line("Residual income RI_t = EPS_t - r_e x BV_t-1", "INR")
        rdf = self.line("Discount factor (1 + r_e)^-t")
        rpv = self.line("PV of RI_t", "INR")
        rcr = self.line("Capital retention gap |BV_t / BVPS_t - 1| (contract §3.6)", "decimal")
        for t in range(1, N + 1):
            g.formula(rri, C0 + t, f'IF({ok},{eps(t)}-{re}*{bv(t - 1)},"")', number="inr", key=f"{k('ri')}.{t}")
            g.formula(rdf, C0 + t, f'IF({ok},(1+{re})^(-{self.yr("t", t)}),"")', key=f"{k('df')}.{t}")
            g.formula(rpv, C0 + t, f'IF({ok},{self.yr(k("ri"), t)}*{self.yr(k("df"), t)},"")', number="inr",
                      key=f"{k('pvri')}.{t}")
            g.formula(rcr, C0 + t, f'IF({rp},ABS({bv(t)}/{self.yr(k("p.bvps"), t)}-1),"")', number="pct",
                      key=f"{k('crgap')}.{t}")
        g.formula(rcr, C0, f'IF({rp},MAX({self.year_range(k("crgap"))}),"")', number="pct", key=k("crgap_max"))
        g.formula(self.line("Capital retention check (max gap <= in_Clean_Surplus_Tol)"), C0,
                  f'IF({rp},IF({self.r(k("crgap_max"))}<=in_Clean_Surplus_Tol,"PASS","FAIL"),"MISSING")',
                  key=k("cr_status"))
        g.formula(self.line("Sum of PV of RI", "INR"), C0, f'IF({ok},SUM({self.year_range(k("pvri"))}),"")',
                  number="inr", key=k("sum_pvri"))
        g.formula(self.line("Terminal RI_N+1 = (ROE_T - r_e) x BV_N", "INR"), C0,
                  f'IF({ok},({roe_t}-{re})*{bv(N)},"")', number="inr", key=k("ri_n1"))
        g.formula(self.line("Terminal value TV_N = RI_N+1 / (r_e - g)", "INR"), C0,
                  f'IF({ok},{self.r(k("ri_n1"))}/({re}-{gr}),"")', number="inr", key=k("ri_tv"))
        g.formula(self.line("PV of terminal value", "INR"), C0, f'IF({ok},{self.r(k("ri_tv"))}*{self.yr(k("df"), N)},"")',
                  number="inr", key=k("ri_pvtv"))
        g.formula(self.line("RI value at A, V_A = BV_0 + PV(RI) + PV(TV)", "INR"), C0,
                  f'IF({ok},{self.r("bv0")}+{self.r(k("sum_pvri"))}+{self.r(k("ri_pvtv"))},"")', number="inr",
                  key=k("ri_va"))
        va = self.r(k("ri_va"))
        g.formula(self.line("Terminal value share of V_A (TV-2)", "decimal"), C0,
                  f'IF({ok},IF({va}=0,"",{self.r(k("ri_pvtv"))}/{va}),"")', number="pct", key=k("ri_share"))
        g.formula(self.line("Terminal flag (TV-1 FAIL, TV-3 WARNING above in_TV_Share_Warn)"), C0,
                  f'IF(NOT({ready}),"MISSING",IF(COUNT({roe_t},{gr})<2,"MISSING",IF({gr}>={re},"FAIL",'
                  f'IF({self.r(k("ri_share"))}>in_TV_Share_Warn,"WARNING","PASS"))))', key=k("tflag"))

    def ddm_and_jpb(self, case: str):
        g = self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        ok, re = self.r(k("ri_ok")), self.r("re")
        roe_t, gr, po = (self.r(k("tr.TERMINAL_ROE")), self.r(k("tr.TERMINAL_GROWTH")),
                         self.r(k("tr.TERMINAL_PAYOUT")))
        self.row += 1
        g.label(self.row, C_LABEL, f"{case}: Dividend Discount (contract §3.3) and justified P/B (§3.4), "
                                   "cross-checks", "h2")
        self.row += 1
        g.formula(self.line("DDM computable (RI computable and payout_T entered)"), C0, f"AND({ok},ISNUMBER({po}))",
                  key=k("ddm_ok"))
        dok = self.r(k("ddm_ok"))
        g.formula(self.line("PV of forecast DPS", "INR"), C0,
                  f'IF({dok},SUMPRODUCT({self.year_range(k("p.dps"))},{self.year_range(k("df"))}),"")', number="inr",
                  key=k("ddm_pvd"))
        g.formula(self.line("DPS_N+1 = ROE_T x BV_N x payout_T", "INR"), C0,
                  f'IF({dok},{roe_t}*{self.yr(k("bv"), N)}*{po},"")', number="inr", key=k("ddm_d1"))
        g.formula(self.line("DDM terminal value", "INR"), C0, f'IF({dok},{self.r(k("ddm_d1"))}/({re}-{gr}),"")',
                  number="inr", key=k("ddm_tv"))
        g.formula(self.line("PV of DDM terminal value", "INR"), C0,
                  f'IF({dok},{self.r(k("ddm_tv"))}*{self.yr(k("df"), N)},"")', number="inr", key=k("ddm_pvtv"))
        g.formula(self.line("DDM value at A", "INR"), C0, f'IF({dok},{self.r(k("ddm_pvd"))}+{self.r(k("ddm_pvtv"))},"")',
                  number="inr", key=k("ddm_va"))
        g.formula(self.line("DDM terminal value share (TV-2)", "decimal"), C0,
                  f'IF({dok},IF({self.r(k("ddm_va"))}=0,"",{self.r(k("ddm_pvtv"))}/{self.r(k("ddm_va"))}),"")',
                  number="pct", key=k("ddm_share"))
        g.formula(self.line("Justified P/B = (ROE_T - g) / (r_e - g)", "x"), C0,
                  f'IF({ok},({roe_t}-{gr})/({re}-{gr}),"")', number="multiple", key=k("jpb_mult"))
        r = self.line("Justified P/B value at A = P/B x BV_0", "INR")
        g.formula(r, C0, f'IF({ok},{self.r(k("jpb_mult"))}*{self.r("bv0")},"")', number="inr", key=k("jpb_va"))
        g.label(r, C0 + 1, "single-stage: all value beyond BV_0 is terminal (TV share n/a)", "note")

    # ------------------------------------------------------------------ bridge, freshness, roll-forward
    def bridge(self):
        g = self.g
        A, V, R, ok = self.r("A"), self.r("V"), self.r("R"), self.r("ok_dates")
        ready = self.r("Base.ready")
        self.section("Equity bridge A -> V (contract §3.1a, Base-case forecast EPS)",
                     "Reported BV at A is historical. Interim results after A are added as reported; the unreported "
                     "stub to V is forecast; dividends that went ex in (A, V] leave. The result is an estimate.")
        self.year_header("Accrual of forecast EPS by calendar day")
        rrv = self.line("Days of (R, V] in fiscal year t")
        rar = self.line("Days of (A, R] in fiscal year t")
        for t in range(1, N + 1):
            fe, fp = self.yr("fye", t), self.yr("fye", t - 1)
            g.formula(rrv, C0 + t, f'IF({ok},MAX(0,MIN({V},{fe})-MAX({R},{fp})),"")', key=f"ovRV.{t}")
            g.formula(rar, C0 + t, f'IF({ok},MAX(0,MIN({R},{fe})-MAX({A},{fp})),"")', key=f"ovAR.{t}")
        g.formula(self.line("Bridge computable (Base case ready, V <= last forecast year end)"), C0,
                  f"IF({ready},{V}<={self.yr('fye', N)},FALSE)", key="bridge_ok")
        bok = self.r("bridge_ok")
        g.formula(self.line("Bridge status"), C0,
                  f'IF(NOT({ready}),"MISSING",IF({V}<={self.yr("fye", N)},"PASS",{q(BRIDGE_HORIZON_FAIL)}))',
                  key="bridge_status")
        eps_row, days_row = self.year_range("Base.p.eps"), self.year_range("days")
        self.row += 1
        r = self.line("BV per share at A", "Reported")
        g.formula(r, C0, f'IF({bok},{self.r("bv0")},"")', number="inr", key="br_bv0")
        g.formula(r, C0 + 1, f'"as of "&IF(ISNUMBER({A}),TEXT({A},"yyyy-mm-dd"),"A (missing)")')
        g.formula(self.line("+ EPS reported for interim periods in (A, R]", "Reported"), C0,
                  f'IF({bok},SUMIFS({self.int_eps},{self.int_pe},">"&{A},{self.int_pe},"<="&{V}),"")', number="inr",
                  key="br_rep")
        g.formula(self.line("+ forecast EPS for (R, V], accrued by calendar day", "Forecast"), C0,
                  f'IF({bok},SUMPRODUCT({eps_row}*{self.year_range("ovRV")}/{days_row}),"")', number="inr",
                  key="br_stub")
        g.formula(self.line("- dividends with ex-date in (A, V]", "Reported"), C0,
                  f'IF({bok},SUM({self.div_incl}),"")', number="inr", key="br_div")
        r = self.line("= Estimated book value per share at V", "Estimate")
        g.formula(r, C0, f'IF({bok},{self.r("br_bv0")}+{self.r("br_rep")}+{self.r("br_stub")}-{self.r("br_div")},"")',
                  number="inr", key="bv_v")
        g.formula(r, C0 + 1, f'"Estimated book value per share at "&IF(ISNUMBER({V}),TEXT({V},"yyyy-mm-dd"),"V")'
                             f'&" (estimate)"', key="bv_v_caption")
        g.formula(self.line("Forecast EPS for (A, R], accrued the same way", "Forecast"), C0,
                  f'IF({bok},SUMPRODUCT({eps_row}*{self.year_range("ovAR")}/{days_row}),"")', number="inr",
                  key="br_fcAR")
        fc, rep = self.r("br_fcAR"), self.r("br_rep")
        g.formula(self.line("Interim EPS deviation = reported / forecast (A, R] - 1", "decimal"), C0,
                  f'IF(AND({bok},{R}>{A}),IF({fc}=0,"",{rep}/{fc}-1),"")', number="pct", key="dev")
        g.formula(self.line("Forecast_Update_Flag (|deviation| > in_Interim_EPS_Dev_Warn)"), C0,
                  f'IF({bok},IF({R}>{A},IF({fc}=0,"WARNING",IF(ABS({self.r("dev")})>in_Interim_EPS_Dev_Warn,"WARNING",'
                  f'"PASS")),"PASS"),"")', key="fflag")
        g.formula(self.line("Interim quarters reported in (A, R]"), C0,
                  f'IF({ok},COUNTIFS({self.int_pe},">"&{A},{self.int_pe},"<="&{R}),"")', key="int_count")
        g.formula(self.line("Quarters expected in (A, R]"), C0,
                  f'IF({ok},INT(((YEAR({R})-YEAR({A}))*{MONTHS_PER_YEAR}+MONTH({R})-MONTH({A}))/{MONTHS_PER_QUARTER}),"")',
                  key="int_expected")
        g.formula(self.line("Interim coverage check (no gap in reported quarters)"), C0,
                  f'IF({ok},IF({self.r("int_count")}={self.r("int_expected")},"PASS","FAIL"),"MISSING")',
                  key="int_status")

    def freshness_and_roll(self):
        g = self.g
        A, V, R, ok, re = self.r("A"), self.r("V"), self.r("R"), self.r("ok_dates"), self.r("re")
        self.section("Financials freshness (contract §3.1b) and roll-forward A -> V (§3.1)")
        g.formula(self.line("Financials_Age_Days = V - R", "days"), C0, f'IF({ok},{V}-{R},"")', number="count",
                  key="fin_age")
        g.formula(self.line("Anchor_Age_Days = V - A", "days"), C0, f'IF({ok},{V}-{A},"")', number="count",
                  key="anchor_age")
        g.formula(self.line("Freshness_Status (FAIL anchor > in_Anchor_Max_Age_Days, STALE > in_Financials_Stale_Days)"),
                  C0, f'IF({ok},IF({self.r("anchor_age")}>in_Anchor_Max_Age_Days,"FAIL",IF({self.r("fin_age")}>'
                      f'in_Financials_Stale_Days,"STALE","PASS")),"MISSING")', key="fresh")
        g.formula(self.line("tau(A, V) = days / 365.25", "years"), C0, f'IF({ok},({V}-{A})/{DAYS_PER_YEAR_DISCOUNT},"")',
                  key="tau")
        g.formula(self.line("Roll factor (1 + r_e)^tau"), C0, f'IF(AND({ok},ISNUMBER({re})),(1+{re})^{self.r("tau")},"")',
                  key="roll")
        g.formula(self.line("Dividends in (A, V] compounded to V: sum DPS_d (1 + r_e)^tau(d, V)", "INR"), C0,
                  f'IF(AND({ok},ISNUMBER({re})),SUMPRODUCT({self.div_incl}*(1+{re})^(({V}-{self.div_ex})/'
                  f'{DAYS_PER_YEAR_DISCOUNT})),"")', number="inr", key="divfv")

    def case_values(self, case: str):
        g = self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        ok, dok, ready = self.r(k("ri_ok")), self.r(k("ddm_ok")), self.r(k("ready"))
        roll, divfv = self.r("roll"), self.r("divfv")
        self.section(f"{case} case: values at the valuation date V and fair value (contract §3.1, §3.8)")
        g.formula(self.line("Residual Income at V = V_A x roll - dividends compounded", "INR"), C0,
                  f'IF({ok},{self.r(k("ri_va"))}*{roll}-{divfv},"")', number="inr", key=k("v.RI"))
        g.formula(self.line("Dividend Discount at V", "INR"), C0, f'IF({dok},{self.r(k("ddm_va"))}*{roll}-{divfv},"")',
                  number="inr", key=k("v.DDM"))
        g.formula(self.line("Justified P/B at V", "INR"), C0, f'IF({ok},{self.r(k("jpb_va"))}*{roll}-{divfv},"")',
                  number="inr", key=k("v.JPB"))
        g.formula(self.line("Peer-relative P/B (price date)", "INR"), C0, f'IF({self.r("peer_v")}="","",'
                                                                           f'{self.r("peer_v")})',
                  number="inr", key=k("v.PEER_PB"))
        methods = ("RI", "DDM", "JPB", "PEER_PB")
        missing = ",".join(f'AND({self.r("w." + m)}>0,{self.r(k("v." + m))}="")' for m in methods)
        total = "+".join(f'IF({self.r("w." + m)}>0,{self.r("w." + m)}*{self.r(k("v." + m))},0)' for m in methods)
        r = self.line(f"{case} fair value per share at V (blend)", "INR")
        g.formula(r, C0, f'IF(AND({ready},{self.r("w_ok")}),IF(OR({missing}),"",{total}),"")', number="inr",
                  key=k("fv"))
        g.formula(r, C0 + 1, f'"Modelled fair value at "&IF(ISNUMBER({self.r("V")}),TEXT({self.r("V")},"yyyy-mm-dd"),'
                             f'"V")&" (estimate)"')
        self.expected_return(case)

    def expected_return(self, case: str):
        g = self.g
        k = lambda name: f"{case}.{name}"  # noqa: E731
        ready, V, T, price = self.r(k("ready")), self.r("V"), self.r("T"), self.r("price")
        self.row += 1
        self.year_header(f"{case}: expected five-year return (contract §8)", with_anchor=False)
        rrec = self.line("Dividend received in (V, T] at FYE_t, net of dividends already ex in the year", "INR")
        for t in range(1, N + 1):
            fe, fp = self.yr("fye", t), self.yr("fye", t - 1)
            already = f'SUMIFS({self.div_dps},{self.div_ex},">"&{fp},{self.div_ex},"<="&{V})'
            g.formula(rrec, C0 + t, f'IF({ready},IF(AND({fe}>{V},{fe}<={T}),MAX(0,{self.yr(k("p.dps"), t)}-{already}),0),"")',
                      number="inr", key=f"{k('rec')}.{t}")
        prev_fye = f"{self.yr('fye', 0)}:{self.yr('fye', N - 1)}"
        prev_bv = f"{self.yr(k('bv'), 0)}:{self.yr(k('bv'), N - 1)}"
        bvt = (f"SUMPRODUCT(({prev_fye}<={T})*({self.year_range('fye')}>{T})*({prev_bv}+{self.year_range(k('p.eps'))}"
               f"*({T}-{prev_fye})/{self.year_range('days')}))")
        g.formula(self.line("BVPS at exit T (clean surplus, accrued within the year)", "INR"), C0,
                  f'IF(AND({ready},{self.r("in_horizon")}),{bvt},"")', number="inr", key=k("bvT"))
        pb = self.r(k("tr.EXIT_PB"))
        g.formula(self.line("Exit value = Exit_PB x BVPS_T", "INR"), C0,
                  f'IF(AND(ISNUMBER({self.r(k("bvT"))}),ISNUMBER({pb}),ISNUMBER({price})),{pb}*{self.r(k("bvT"))},"")',
                  number="inr", key=k("exit"))
        ex = self.r(k("exit"))
        g.formula(self.line("Expected-return status"), C0,
                  f'IF(NOT({ready}),"MISSING",IF(NOT({self.r("in_horizon")}),{q(ER_HORIZON_FAIL)},IF(NOT(ISNUMBER({pb})),'
                  f'{q(ER_NO_EXIT_PB)},IF(NOT(ISNUMBER({price})),{q(ER_NO_PRICE)},"PASS"))))', key=k("er_status"))
        rd = self.line("Cash-flow dates: V, max(FYE_t, V), T")
        rf = self.line("Cash flows: -price, dividends, exit value", "INR")
        last = C0 + N + 1
        g.formula(rd, C0, f'IF({ready},{V},"")', number="date", key=f"{k('cfd')}.0")
        g.formula(rf, C0, f'IF(ISNUMBER({ex}),-{price},"")', number="inr", key=f"{k('cf')}.0")
        for t in range(1, N + 1):
            g.formula(rd, C0 + t, f'IF({ready},MAX({self.yr("fye", t)},{V}),"")', number="date", key=f"{k('cfd')}.{t}")
            g.formula(rf, C0 + t, f'IF(ISNUMBER({ex}),{self.yr(k("rec"), t)},"")', number="inr", key=f"{k('cf')}.{t}")
        g.formula(rd, last, f'IF({ready},{T},"")', number="date", key=f"{k('cfd')}.{N + 1}")
        g.formula(rf, last, f'IF(ISNUMBER({ex}),{ex},"")', number="inr", key=f"{k('cf')}.{N + 1}")
        flows = f"{self.yr(k('cf'), 0)}:{self.yr(k('cf'), N + 1)}"
        dates = f"{self.yr(k('cfd'), 0)}:{self.yr(k('cfd'), N + 1)}"
        g.formula(self.line("Annualised total return, dividends not reinvested (XIRR, days/365)", "decimal"), C0,
                  f'IF(ISNUMBER({ex}),XIRR({flows},{dates}),"")', number="pct", key=k("xirr"))
        rr = self.r("r_reinv")
        g.formula(self.line("Annualised total return, dividends reinvested at r_reinv", "decimal"), C0,
                  f'IF(AND(ISNUMBER({ex}),ISNUMBER({rr})),(({ex}+SUMPRODUCT({self.year_range(k("rec"))}*(1+{rr})^(({T}-'
                  f'{self.year_range("fye")})/{DAYS_PER_YEAR_XIRR})))/{price})^({DAYS_PER_YEAR_XIRR}/({T}-{V}))-1,"")',
                  number="pct", key=k("reinv"))
        g.formula(self.line("Expected return (selected reinvestment mode)", "decimal"), C0,
                  f'IF({self.r("er_mode")}={q(REINVESTED)},{self.r(k("reinv"))},{self.r(k("xirr"))})', number="pct",
                  key=k("er"))

    # ------------------------------------------------------------------ sensitivity
    def sensitivity(self):
        g = self.g
        ok = self.r("Base.ri_ok")
        self.section("Sensitivity of the Base-case RI value per share at V (contract §10 TV-4, TV-5)",
                     "Blue cells are the grid steps. Drivers and EPS stay at Base; r_e also changes the roll-forward. "
                     f"A cell with g >= r_e shows {NA_G_GE_R}.")
        eps = self.year_range("Base.p.eps")
        bvprev = f"{self.yr('Base.bv', 0)}:{self.yr('Base.bv', N - 1)}"
        trow, bvn, tau, V = self.year_range("t"), self.yr("Base.bv", N), self.r("tau"), self.r("V")

        def value(rate: str, roe: str, gr: str) -> str:
            return (f"({self.r('bv0')}+SUMPRODUCT(({eps}-{rate}*{bvprev})*(1+{rate})^(-{trow}))+({roe}-{rate})*{bvn}/"
                    f"({rate}-{gr})*(1+{rate})^(-{self.yr('t', N)}))*(1+{rate})^{tau}-SUMPRODUCT({self.div_incl}*"
                    f"(1+{rate})^(({V}-{self.div_ex})/{DAYS_PER_YEAR_DISCOUNT}))")

        roe_b, g_b, re = self.r("Base.tr.TERMINAL_ROE"), self.r("Base.tr.TERMINAL_GROWTH"), self.r("re")
        for name, steps, axis_base, label in (("rg", GROWTH_STEPS, g_b, "g"), ("rroe", ROE_STEPS, roe_b, "ROE_T")):
            r = self.line(f"r_e x {label}: {label} step")
            for j, st in enumerate(steps):
                g.value(r, C0 + 1 + j, st, role="input", number="pct", key=f"grid.{name}.cstep.{j}")
            r = self.line(f"r_e step | r_e  \\  {label}")
            for j in range(len(steps)):
                g.formula(r, C0 + 1 + j, f'IF(ISNUMBER({axis_base}),{axis_base}+{self.r(f"grid.{name}.cstep.{j}")},"")',
                          number="pct", key=f"grid.{name}.col.{j}")
            for i, st in enumerate(RATE_STEPS):
                r = self.row
                self.row += 1
                g.value(r, C_TAG, st, role="input", number="pct", key=f"grid.{name}.rstep.{i}")
                g.formula(r, C0, f'IF(ISNUMBER({re}),{re}+{self.r(f"grid.{name}.rstep.{i}")},"")', number="pct",
                          key=f"grid.{name}.row.{i}")
                rate = self.r(f"grid.{name}.row.{i}")
                for j in range(len(steps)):
                    col = self.r(f"grid.{name}.col.{j}")
                    if name == "rg":
                        f = f'IF(NOT({ok}),"",IF({col}>={rate},{q(NA_G_GE_R)},{value(rate, roe_b, col)}))'
                    else:
                        f = f'IF(NOT({ok}),"",IF({g_b}>={rate},{q(NA_G_GE_R)},{value(rate, col, g_b)}))'
                    g.formula(r, C0 + 1 + j, f, number="inr", key=f"grid.{name}.{i}.{j}")
            self.row += 1

    # ------------------------------------------------------------------ results
    def results(self):
        g, s = self.g, self.s
        row = 4
        g.label(row, C_LABEL, "RESULTS (estimates at the valuation date; inputs and checks below)", "h1")
        for c in range(1, C_STAT + 1):
            g.label(row, c, "", "h1")
        row += 1
        V = self.r("V")

        def put(label, formula, number="general", key=None, tag="", caption=None, role="calc"):
            nonlocal row
            g.label(row, C_LABEL, label)
            if tag:
                g.label(row, C_TAG, tag, "tag")
            g.formula(row, C0, formula, number=number, key=key, role=role)
            if caption:
                g.formula(row, C0 + 1, caption)
            row += 1
            return g.addr(row - 1, C0)

        cap_v = f'"at "&IF(ISNUMBER({V}),TEXT({V},"yyyy-mm-dd"),"V")&" (estimate)"'
        for c in ("Base", "Bear", "Bull"):
            cell = put(f"{c} fair value per share", f'IF({self.r(c + ".fv")}="","",{self.r(c + ".fv")})', "inr",
                       key=f"out.FV_{c}", tag="INR", caption=cap_v)
            self.ctx.define_name("02-valuation", f"out_{s.security_id}_FV_{c}", s.sheet, cell)
        cell = put("Terminal value share, Base RI (out_*_TV_Share)",
                   f'IF({self.r("Base.ri_share")}="","",{self.r("Base.ri_share")})', "pct", key="out.TV_Share")
        self.ctx.define_name("02-valuation", f"out_{s.security_id}_TV_Share", s.sheet, cell)
        put("Terminal flag (Base)", f"{self.r('Base.tflag')}", key="out.tflag")
        fvs = [self.r(f"out.FV_{c}") for c in ("Base", "Bear", "Bull")]
        put("Valuation coverage status", f'IF(AND({",".join(f"ISNUMBER({x})" for x in fvs)}),'
                                         f'{q(CoverageStatus.MODEL_VALUED.value)},{q(CoverageStatus.UNVALUED.value)})',
            key="out.coverage")
        price, bv0, bvv, base_fv = self.r("price"), self.r("bv0"), self.r("bv_v"), self.r("out.FV_Base")
        put("Current market price", f'IF({price}="","",{price})', "inr", tag="INR",
            caption=f'"at price date "&IF(ISNUMBER({self.r("PD")}),TEXT({self.r("PD")},"yyyy-mm-dd"),"(missing)")')
        put("Upside of Base fair value vs price", f'IF(COUNT({price},{base_fv})=2,{base_fv}/{price}-1,"")', "pct",
            key="m.upside", caption='"valuation gap, not a return forecast"')
        put("Market capitalisation (price x diluted shares at A)",
            f'IF(COUNT({price},{self.r("sh0")})=2,{price}*{self.r("sh0")}/{INR_PER_CRORE},"")', "inr_cr", key="m.mcap",
            tag="INR_Cr")
        put("P/B on reported BV at A", f'IF(COUNT({price},{bv0})=2,{price}/{bv0},"")', "multiple", key="m.pb_A",
            caption=f'"on BV at A ("&IF(ISNUMBER({self.r("A")}),TEXT({self.r("A")},"yyyy-mm-dd"),"missing")&")"')
        put("P/B on estimated BV at V", f'IF(COUNT({price},{bvv})=2,{price}/{bvv},"")', "multiple", key="m.pb_V",
            caption='"on estimated BV at V (estimate)"')
        put("Implied P/B of Base fair value at V", f'IF(COUNT({base_fv},{bvv})=2,{base_fv}/{bvv},"")', "multiple",
            key="m.ipb_V", caption='"V_V / BV_V_est (estimate)"')
        put("Trailing P/E on FY diluted EPS at A", f'IF(COUNT({price},{self.r("epsA")})=2,{price}/{self.r("epsA")},"")',
            "multiple", key="m.pe_trailing", caption='"Calculated: reported FY EPS at A"')
        eps1 = self.yr("Base.p.eps", 1)
        put("Forward P/E on Base-case EPS for year 1", f'IF(AND(ISNUMBER({price}),ISNUMBER({eps1})),{price}/{eps1},"")',
            "multiple", key="m.pe_fwd",
            caption=q(f"Modelled {s.fy_labels[0] + 'E' if s.fy_labels else 'year 1'} EPS; not consensus"))
        for lab in ("EV/EBITDA", "EV/Revenue"):
            g.label(row, C_LABEL, lab)
            g.label(row, C0, NM_TEXT, "label_b")
            g.label(row, C0 + 1, NM_REASON, "note")
            row += 1
        for c in ("Base", "Bear", "Bull"):
            put(f"Expected five-year return, {c} (selected mode)", f'IF({self.r(c + ".er")}="","",{self.r(c + ".er")})',
                "pct", caption=f'{self.r(c + ".er_status")}')
        ps = [self.r(f"p.{c}") for c in P.CASES]
        ers = [self.r(f"{c}.er") for c in P.CASES]
        prange = f"{ps[0]}:{ps[-1]}"
        miss = ",".join(f'AND({p}>0,{e}="")' for p, e in zip(ps, ers))
        put("Probability status (sum to 1, each in [0, 1])",
            f'IF(COUNT({prange})<3,{q(PROBABILITIES_NOT_ENTERED)},IF(OR(MIN({prange})<0,MAX({prange})>1,'
            f'ABS(SUM({prange})-1)>{PROBABILITY_SUM_TOL}),"FAIL",IF(OR({miss}),"MISSING","PASS")))', key="p_status")
        tot = "+".join(f'IF({p}>0,{p}*{e},0)' for p, e in zip(ps, ers))
        put("Probability-weighted expected return (shown only when probabilities are entered)",
            f'IF({self.r("p_status")}="PASS",{tot},"")', "pct", key="p_er")
        checks = [("Freshness_Status (§3.1b)", "fresh"), ("Forecast_Update_Flag (§3.1a)", "fflag"),
                  ("Interim coverage", "int_status"), ("Bridge status", "bridge_status"),
                  ("Share-count check", "share_status"), ("Weights check", "w_status"), ("Peer flag", "peer_flag"),
                  ("Capital retention, Bear", "Bear.cr_status"), ("Capital retention, Base", "Base.cr_status"),
                  ("Capital retention, Bull", "Bull.cr_status"), ("Market price status", "price_status")]
        for lab, key in checks:
            put(lab, self.r(key))
        g.label(row, C_LABEL, "R004 method check")
        g.formula(row, C0, self.r("method_check"))
        row += 1
        put("Missing critical inputs (count)", self.missing_formula(), key="missing", tag="count")
        put("Data_Confidence_Note (components, no composite score)",
            f'"Freshness: "&{self.r("fresh")}&"; financials age "&{self.r("fin_age")}&"d; anchor age "&'
            f'{self.r("anchor_age")}&"d; forecast check: "&{self.r("fflag")}&"; terminal: "&{self.r("Base.tflag")}'
            f'&"; missing critical inputs: "&{self.r("missing")}', key="note")
        if row > RESULTS_ROWS + 3:
            raise RuntimeError(f"results block overflows its reserved rows ({row})")

    def missing_formula(self) -> str:
        parts = [f"6-COUNT({','.join(self.r(k) for k in ('eq0', 'sh0', 'adv0', 'nonii0', 'opex0', 'iea0'))})",
                 f"3-COUNT({self.r('rf')},{self.r('erp')},{self.r('beta')})", f"1-COUNT({self.r('price')})",
                 f"4-COUNT({self.r('w.RI')}:{self.r('w.PEER_PB')})",
                 f"2-COUNT({self.r('A')},{self.r('V')})"]
        for c in P.CASES:
            for p in P.DRIVER_PARAMETERS:
                if p.required:
                    parts.append(f"{N}-COUNT({self.year_range(f'{c}.d.{p.code}')})")
            parts.append(f"3-COUNT({','.join(self.r(f'{c}.tr.{x}') for x in ('TERMINAL_ROE', 'TERMINAL_GROWTH', 'TERMINAL_PAYOUT'))})")
        return "+".join(parts)

    # ------------------------------------------------------------------ history
    def history(self):
        s, g = self.s, self.g
        for block, metrics, periods, calcs, title in (
                ("FY", HISTORY_FY_METRICS, s.history_fy, H.FY_CALCS, "Annual history: 10 fiscal years to A"),
                ("Q", HISTORY_Q_METRICS, s.history_q, H.Q_CALCS, "Quarterly history: 20 quarters to V (discrete)")):
            self.section(f"{title} (reported rows link tbl_RawFinancials by Observation_ID; calc. rows are formulas)",
                         "Blank = no observation (counted in the last column); never 0. Feeds tbl_HistoricalMetrics.")
            r = self.row
            g.label(r, C_LABEL, "Metric [Metric_ID]", "colhead")
            g.label(r, C_TAG, "Unit", "colhead")
            for j, (lab, _) in enumerate(periods):
                g.label(r, C0 + j, lab, "colhead")
            cnt_col = C0 + len(periods)
            g.label(r, cnt_col, "Observations", "colhead")
            self.row += 1
            cells: dict[str, list[str]] = {}
            for m in metrics:
                unit, number = H.metric_units(m)
                r = self.line(f"{H.metric_label(m)} [{m}]", unit)
                cells[m] = []
                for j, (lab, _) in enumerate(periods):
                    ob = s.history.get((m, lab))
                    if ob is None:
                        a = g.value(r, C0 + j, None, role="link", number=number)
                    else:
                        a = g.formula(r, C0 + j, obs_link(ob.observation_id), role="link", number=number)
                    cells[m].append(a)
                    self.built.history_cells[(block, m, lab)] = f"'{s.sheet}'!{a}"
                if periods:
                    g.formula(r, cnt_col, f'COUNT({cells[m][0]}:{cells[m][-1]})&" of {len(periods)}"')
            for c in calcs:
                r = self.line(c.label + (f" [{c.key}]" if c.export else ""), c.unit)
                cells[c.key] = []
                for j, (lab, _) in enumerate(periods):
                    lags = [lag for _, lag in c.inputs]
                    if j - max(lags) < 0:
                        a = g.value(r, C0 + j, None, number=c.number)
                    else:
                        refs = [cells[mm][j - lag] for mm, lag in c.inputs]
                        a = g.formula(r, C0 + j, H.excel_calc(c, refs), number=c.number)
                    cells[c.key].append(a)
                    self.built.history_cells[(block, c.key, lab)] = f"'{s.sheet}'!{a}"
                if periods:
                    g.formula(r, cnt_col, f'COUNT({cells[c.key][0]}:{cells[c.key][-1]})&" of {len(periods)}"')

    # ------------------------------------------------------------------ charts
    def chart_zones(self):
        s = self.s
        base_col = C0 + N_HIST_COLS + 3
        for i, (cid, purpose) in enumerate(CHART_IDS.items()):
            col = base_col + (i % 2) * 9
            row = 4 + (i // 2) * 18
            anchor = f"{Grid.col(col)}{row + 1}"
            self.ctx.reserve_chart_zone("02-valuation", f"{s.sheet}_{cid}", s.sheet, anchor,
                                        f"{cid}: {purpose}. Series: tbl_HistoricalMetrics (Entity_ID {s.entity_id}) "
                                        f"and the {s.sheet} result cells; history and forecast styled apart.")


N_HIST_COLS = 20   # widest history block (quarters)


def build_bank_sheet(ctx, spec: BankSpec, link_peers: bool = True) -> BuiltSheet:
    """Lay out one bank VAL_* sheet (R004: the template's primary method is validated in gather_bank_spec)."""
    return BankSheetBuilder(ctx, spec, link_peers).build()
