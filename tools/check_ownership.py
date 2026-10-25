"""Fail if a worker's branch touches files it does not own.

usage: python tools/check_ownership.py <worker-id> [<base-ref>]
  e.g. python tools/check_ownership.py 02-valuation origin/claude/financial-modeling-architecture-o2xiwz

Run by every worker before pushing, and by 00-main before merging a worker branch.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.ownership import path_owner, load  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in load()["workers"]:
        print(__doc__)
        return 2
    worker = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "HEAD~1"
    changed = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                             capture_output=True, text=True, check=True).stdout.split()
    changed += subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                              check=True).stdout.splitlines()
    files = sorted({c.split()[-1] for c in changed if c.strip()})
    # 00-main may also change frozen paths (after an accepted change request).
    allowed = {worker, "shared", "frozen"} if worker == "00-main" else {worker, "shared"}
    bad = [(f, path_owner(f)) for f in files if path_owner(f) not in allowed]
    for f, owner in bad:
        print(f"OWNERSHIP VIOLATION: {f} is owned by {owner or 'nobody'}, not {worker}")
    if not bad:
        print(f"ownership OK for {worker}: {len(files)} file(s) checked")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
