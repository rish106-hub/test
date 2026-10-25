"""Cell style registry (spec <formatting_and_colour_coding>).

Every sheet builder takes formats from here via WorkbookContext.fmt(name). A cell's
font colour states its provenance, and QA checks the colour against the cell's content:
  input     blue    typed user assumption or scenario control
  calc      black   formula within the same sheet
  link      green   formula referencing another sheet
  imported  grey    immutable source observation
  override  purple  scenario override / hypothetical input
"""
BLUE, BLACK, GREEN, GREY, PURPLE = "#0000FF", "#000000", "#007A33", "#6E6E6E", "#6B2C91"

FONT_BY_ROLE = {"input": BLUE, "calc": BLACK, "link": GREEN, "imported": GREY, "override": PURPLE}

NUMBER_FORMATS = {
    "inr": '"₹"#,##0.00;("₹"#,##0.00)',
    "inr_cr": '#,##0.00" Cr";(#,##0.00" Cr")',
    "pct": "0.00%;(0.00%)",
    "multiple": '0.0"x"',
    "count": "#,##0",
    "date": "yyyy-mm-dd",
    "general": "General",
}

STATUS_FILL = {  # always paired with the status text itself (colour safety)
    "PASS": "#C6EFCE", "WARNING": "#FFEB9C", "FAIL": "#FFC7CE",
    "MISSING": "#F2DCDB", "STALE": "#FFEB9C", "NOT RUN": "#D9D9D9",
}

BASE_FONT = {"font_name": "Calibri", "font_size": 10}


def format_props(role: str, number: str = "general", **extra) -> dict:
    props = dict(BASE_FONT, font_color=FONT_BY_ROLE[role], num_format=NUMBER_FORMATS[number])
    if role == "imported":
        props["bg_color"] = "#F2F2F2"
    if role == "override":
        props["bg_color"] = "#F3EAF7"
    if role == "input":
        props["bg_color"] = "#FFF9E6"
    props.update(extra)
    return props
