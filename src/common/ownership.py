"""Loads spec/ownership.toml and answers 'who owns this path / sheet?'."""
from __future__ import annotations

import fnmatch
import tomllib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_FILE = ROOT / "spec" / "ownership.toml"


@lru_cache(maxsize=1)
def load() -> dict:
    with OWNERSHIP_FILE.open("rb") as fh:
        return tomllib.load(fh)


def _match(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return fnmatch.fnmatch(path, pattern)


def _specificity(pattern: str) -> int:
    """Length of the literal part of a pattern: the most specific matching pattern wins."""
    return len(pattern.split("*", 1)[0])


def path_owner(path: str) -> str | None:
    data = load()
    if any(_match(path, p) for p in data["shared"]["paths"]):
        return "shared"
    if any(_match(path, p) for p in data["frozen"]["paths"]):
        return "frozen"
    best: tuple[int, str] | None = None
    for worker, spec in data["workers"].items():
        for p in spec["paths"]:
            if _match(path, p) and (best is None or _specificity(p) > best[0]):
                best = (_specificity(p), worker)
    return best[1] if best else None


def sheet_owner(sheet: str) -> str | None:
    workers = load()["workers"]
    for worker, spec in workers.items():
        if sheet in spec["sheets"]:
            return worker
    for worker, spec in workers.items():
        if any(sheet.startswith(p) for p in spec.get("sheet_prefixes", [])):
            return worker
    return None


def all_sheets() -> list[str]:
    return [s for spec in load()["workers"].values() for s in spec["sheets"]]
