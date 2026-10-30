#!/usr/bin/env python3
"""Standalone CLI for the Python 3.9 / stdlib-only rule (manual T8 gate).

Same rule as CH15 (both call checks.py39_rules — no second copy):

    python3 tools/check_py39.py            # scan the whole repo
    python3 tools/check_py39.py some/dir   # scan a subtree

Prints every violation and exits 1 if any file fails the 3.9 syntax check or
imports a non-stdlib, non-local module; prints ``PY39 OK`` otherwise.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from checks.py39_rules import REPO as RULES_REPO, scan_tree  # noqa: E402


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else RULES_REPO
    violations = scan_tree(target)
    if violations:
        for line in violations:
            print(line)
        print(f"PY39 FAILED ({len(violations)} violations)")
        return 1
    print(f"PY39 OK (all .py files parse as Python 3.9; imports stdlib/local only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
