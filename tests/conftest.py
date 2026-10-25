"""Test-suite policy (owner: 00-main).

Contract tests call interfaces that workers implement. Until an owner implements a
function it raises NotImplementedError, which is reported as SKIPPED with the owner
named, so each worker sees exactly what remains. `--strict-impl` turns those skips into
failures. 00-main uses it as the merge gate for an owner's tests, and 05-qa always uses it.
"""
import pytest


def pytest_addoption(parser):
    parser.addoption("--strict-impl", action="store_true",
                     help="treat NotImplementedError as failure (merge / QA gate)")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if (call.when == "call" and call.excinfo is not None
            and call.excinfo.errisinstance(NotImplementedError)
            and not item.config.getoption("--strict-impl")):
        rep.outcome = "skipped"
        rep.longrepr = (str(item.fspath), item.location[1] or 0, f"not implemented: {call.excinfo.value}")
