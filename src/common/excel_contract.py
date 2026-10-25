"""Excel formula interface rules (spec/workbook_interface.md, D-002).

Core calculation formulas may only use FUNCTION_WHITELIST: functions that evaluate
identically in Microsoft Excel 365 and in LibreOffice 24.2, the recalculation engine
of the QA harness. XLOOKUP and LET return #NAME? in LibreOffice 24.2 (verified
2026-10-25), so a workbook using them could not be verified independently.
"""
from __future__ import annotations

import re

FUNCTION_WHITELIST = frozenset({
    # logic / errors
    "IF", "IFERROR", "IFNA", "IFS", "AND", "OR", "NOT", "NA", "ISNUMBER", "ISBLANK",
    "ISERROR", "ISNA", "ISTEXT",
    # lookup (INDEX/MATCH only)
    "INDEX", "MATCH", "CHOOSE", "ROWS", "COLUMNS",
    # aggregation
    "SUM", "SUMIF", "SUMIFS", "SUMPRODUCT", "COUNT", "COUNTA", "COUNTIF", "COUNTIFS",
    "COUNTBLANK", "AVERAGE", "AVERAGEIFS", "MEDIAN", "MIN", "MAX", "MINIFS", "MAXIFS",
    "PRODUCT", "STDEV.S", "LARGE", "SMALL", "RANK.EQ",
    # maths
    "ABS", "ROUND", "ROUNDDOWN", "ROUNDUP", "INT", "POWER", "SQRT", "EXP", "LN", "SIGN",
    # finance / dates
    "XIRR", "XNPV", "NPV", "IRR", "DATE", "EDATE", "EOMONTH", "YEARFRAC", "DAYS", "YEAR",
    "MONTH", "DAY", "TODAY",
    # text
    "TEXT", "CONCATENATE", "LEFT", "RIGHT", "LEN", "TRIM", "VALUE", "UPPER", "HYPERLINK",
})

# Explicitly banned, with the reason a worker will see in the failure message.
FUNCTION_BANNED = {
    "XLOOKUP": "not evaluated by LibreOffice 24.2; use INDEX/MATCH",
    "XMATCH": "not evaluated by LibreOffice 24.2; use MATCH",
    "LET": "not evaluated by LibreOffice 24.2; use a helper column",
    "LAMBDA": "not evaluated by LibreOffice 24.2",
    "FILTER": "dynamic arrays are not used; use helper columns",
    "SORT": "dynamic arrays are not used", "UNIQUE": "dynamic arrays are not used",
    "SEQUENCE": "dynamic arrays are not used",
    "INDIRECT": "volatile and invisible to dependency tracing; reference tables directly",
    "OFFSET": "volatile and fragile; use INDEX",
}

# Workbook naming conventions
TABLE_PREFIX = "tbl_"   # Excel tables
INPUT_PREFIX = "in_"    # single-cell user inputs (GLOBAL_ASSUMPTIONS etc.)
OUTPUT_PREFIX = "out_"  # single-cell outputs other modules may link to
NAME_RE = re.compile(r"^(in|out)_[A-Za-z0-9_]+$")
TABLE_RE = re.compile(r"^tbl_[A-Za-z0-9_]+$")

_FUNC_TOKEN = re.compile(r"(?<![A-Za-z0-9_.\[])([A-Z][A-Z0-9.]*)\s*\(")
_TABLE_REF = re.compile(r"\b(tbl_[A-Za-z0-9_]+)\[")
_NAME_REF = re.compile(r"(?<![A-Za-z0-9_\[])((?:in|out)_[A-Za-z0-9_]+)\b")
_STRING = re.compile(r'"(?:[^"]|"")*"')


def _strip_strings(formula: str) -> str:
    return _STRING.sub('""', formula)


def functions_used(formula: str) -> set[str]:
    body = _strip_strings(formula).replace("_xlfn.", "")
    return set(_FUNC_TOKEN.findall(body))


def tables_referenced(formula: str) -> set[str]:
    return set(_TABLE_REF.findall(_strip_strings(formula)))


def names_referenced(formula: str) -> set[str]:
    return set(_NAME_REF.findall(_strip_strings(formula)))


def output_name(security_id: str, field: str) -> str:
    """Named output a VAL_* sheet exposes, e.g. out_S00001_FV_Base."""
    return f"{OUTPUT_PREFIX}{security_id}_{field}"


def check_formula(formula: str) -> list[str]:
    problems = []
    for fn in sorted(functions_used(formula)):
        if fn in FUNCTION_BANNED:
            problems.append(f"{fn} is banned: {FUNCTION_BANNED[fn]}")
        elif fn not in FUNCTION_WHITELIST:
            problems.append(f"{fn} is not on the whitelist (src/common/excel_contract.py)")
    return problems
