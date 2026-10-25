"""pytest plugin used by qa/run_validation.py: records the outcome of every test phase.

Loaded with `-p qa.pytest_qa_plugin`; writes JSON to the path in $QA_RESULTS_JSON at session end.
"""
from __future__ import annotations

import json
import os

import pytest

_RESULTS: dict[str, dict] = {}


def _entry(nodeid: str) -> dict:
    return _RESULTS.setdefault(nodeid, {"nodeid": nodeid, "phases": {}, "props": {}, "doc": "", "name": ""})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    e = _entry(item.nodeid)
    fn = getattr(item, "function", None)
    e["doc"] = ((fn.__doc__ or "").strip().splitlines() or [""])[0] if fn else ""
    e["name"] = item.name
    if rep.when == "call" and hasattr(item, "callspec"):
        e["param"] = item.callspec.id


def pytest_runtest_logreport(report):
    e = _entry(report.nodeid)
    text = ""
    if report.longrepr is not None:
        if isinstance(report.longrepr, tuple):
            text = str(report.longrepr[2])
        else:
            text = getattr(report, "longreprtext", "") or str(report.longrepr)
    e["phases"][report.when] = {"outcome": report.outcome, "text": text[-2000:],
                                "wasxfail": getattr(report, "wasxfail", None)}
    for k, v in report.user_properties:
        e["props"][k] = str(v)


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("QA_RESULTS_JSON")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(list(_RESULTS.values()), fh, indent=1)
