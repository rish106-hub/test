"""Proves the recalculation harness works and every whitelisted function evaluates in
LibreOffice (D-002). Without this the QA comparison could pass on cached zeros."""
import shutil

import pytest
import xlsxwriter

from build.recalc import read_values, recalc
from src.common.excel_contract import FUNCTION_WHITELIST

pytestmark = [pytest.mark.workbook,
              pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")]

SAMPLES = {
    "IF": "=IF(1>0,1,0)", "IFERROR": '=IFERROR(1/0,7)', "IFNA": "=IFNA(NA(),7)", "IFS": '=IFS(1>2,0,TRUE,7)',
    "AND": "=AND(TRUE,TRUE)", "OR": "=OR(FALSE,TRUE)", "NOT": "=NOT(FALSE)", "NA": "=ISNA(NA())",
    "ISNUMBER": "=ISNUMBER(1)", "ISBLANK": "=ISBLANK(Z99)", "ISERROR": "=ISERROR(1/0)", "ISNA": "=ISNA(NA())",
    "ISTEXT": '=ISTEXT("a")', "INDEX": "=INDEX(A1:A3,2)", "MATCH": "=MATCH(2,A1:A3,0)",
    "CHOOSE": "=CHOOSE(2,5,7)", "ROWS": "=ROWS(A1:A3)", "COLUMNS": "=COLUMNS(A1:B1)", "SUM": "=SUM(A1:A3)",
    "SUMIF": '=SUMIF(A1:A3,">1")', "SUMIFS": '=SUMIFS(A1:A3,A1:A3,">1")', "SUMPRODUCT": "=SUMPRODUCT(A1:A3,A1:A3)",
    "COUNT": "=COUNT(A1:A3)", "COUNTA": "=COUNTA(A1:A3)", "COUNTIF": '=COUNTIF(A1:A3,">1")',
    "COUNTIFS": '=COUNTIFS(A1:A3,">1")', "COUNTBLANK": "=COUNTBLANK(Z1:Z3)", "AVERAGE": "=AVERAGE(A1:A3)",
    "AVERAGEIFS": '=AVERAGEIFS(A1:A3,A1:A3,">1")', "MEDIAN": "=MEDIAN(A1:A3)", "MIN": "=MIN(A1:A3)",
    "MAX": "=MAX(A1:A3)", "MINIFS": '=MINIFS(A1:A3,A1:A3,">1")', "MAXIFS": '=MAXIFS(A1:A3,A1:A3,"<3")',
    "PRODUCT": "=PRODUCT(A1:A3)", "STDEV.S": "=STDEV.S(A1:A3)", "LARGE": "=LARGE(A1:A3,1)",
    "SMALL": "=SMALL(A1:A3,1)", "RANK.EQ": "=RANK.EQ(2,A1:A3)", "ABS": "=ABS(-1)", "ROUND": "=ROUND(1.26,1)",
    "ROUNDDOWN": "=ROUNDDOWN(1.29,1)", "ROUNDUP": "=ROUNDUP(1.21,1)", "INT": "=INT(1.9)", "POWER": "=POWER(2,3)",
    "SQRT": "=SQRT(4)", "EXP": "=EXP(0)", "LN": "=LN(1)", "SIGN": "=SIGN(-3)",
    "XIRR": "=XIRR(B1:B2,C1:C2)", "XNPV": "=XNPV(0.1,B1:B2,C1:C2)", "NPV": "=NPV(0.1,1,1)",
    "IRR": "=IRR(B1:B2)", "DATE": "=DATE(2026,3,31)", "EDATE": "=EDATE(DATE(2026,1,31),1)",
    "EOMONTH": "=EOMONTH(DATE(2026,1,15),0)", "YEARFRAC": "=YEARFRAC(DATE(2026,1,1),DATE(2027,1,1))",
    "DAYS": "=DAYS(DATE(2026,1,2),DATE(2026,1,1))", "YEAR": "=YEAR(DATE(2026,1,1))", "MONTH": "=MONTH(DATE(2026,2,1))",
    "DAY": "=DAY(DATE(2026,2,3))", "TODAY": "=TODAY()>0", "TEXT": '=TEXT(0.833,"0.0%")',
    "CONCATENATE": '=CONCATENATE("a","b")', "LEFT": '=LEFT("abc",1)', "RIGHT": '=RIGHT("abc",1)',
    "LEN": '=LEN("abc")', "TRIM": '=TRIM(" a ")', "VALUE": '=VALUE("3")', "UPPER": '=UPPER("a")',
    "HYPERLINK": '=HYPERLINK("#A1","go")',
}


def test_every_whitelisted_function_has_a_sample():
    assert set(SAMPLES) == set(FUNCTION_WHITELIST)


def test_whitelist_evaluates_in_libreoffice(tmp_path):
    path = tmp_path / "whitelist.xlsx"
    wb = xlsxwriter.Workbook(str(path), {"use_future_functions": True})
    ws = wb.add_worksheet("S")
    ws.write_column("A1", [1, 2, 3])
    ws.write_column("B1", [-100, 110])
    ws.write_column("C1", [46023, 46388])   # 2026-01-01, 2027-01-01
    order = sorted(SAMPLES)
    for i, fn in enumerate(order):
        ws.write_formula(i, 4, SAMPLES[fn])
    wb.close()
    values = read_values(recalc(path, tmp_path / "out"))["S"]
    bad = {fn: values.get(f"E{i + 1}") for i, fn in enumerate(order)
           if values.get(f"E{i + 1}") is None or str(values.get(f"E{i + 1}")).startswith("#")}
    assert bad == {}
    assert values[f"E{order.index('XIRR') + 1}"] == pytest.approx(0.10, abs=1e-6)
