#!/usr/bin/env python3
"""Docs-vs-reality count gate (self-review SR-3 follow-up).

Fails when the human-facing docs drift from the live numbers:

1. stale-count blacklist: ``51 tests`` / ``51 unit`` / ``51 OK`` / ``31/31``
   must not appear in README.md or docs/*.md (they were the pre-self-review
   counts);
2. current-count presence: the LIVE unittest test count and the LIVE .py
   file count (CH15's n) must appear in README.md, docs/HANDOFF_A.md and
   docs/reproduction.md, and reproduction.md must carry ``CH15 <n>/<n>``.

Run from anywhere: ``python3 tools/check_docs_counts.py``
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from checks.py39_rules import iter_repo_py_files  # noqa: E402

BLACKLIST = re.compile(r"\b51 tests\b|\b51 unit\b|\b51 OK\b|\b31/31\b")
SCAN_FILES = [REPO / "README.md"] + sorted((REPO / "docs").glob("*.md"))
COUNT_FILES = [REPO / "README.md", REPO / "docs" / "HANDOFF_A.md",
               REPO / "docs" / "reproduction.md"]


def live_test_count():
    return sum(Path(p).read_text(encoding="utf-8").count("    def test_")
               for p in sorted((REPO / "tests").glob("test_*.py")))


def live_py_file_count():
    return sum(1 for _ in iter_repo_py_files())


def main():
    failures = []
    n_tests = live_test_count()
    n_files = live_py_file_count()
    for path in SCAN_FILES:
        text = path.read_text(encoding="utf-8")
        for match in BLACKLIST.finditer(text):
            failures.append(f"{path.relative_to(REPO)}: stale count "
                            f"{match.group(0)!r}")
    for path in COUNT_FILES:
        text = path.read_text(encoding="utf-8")
        if f"{n_tests} tests" not in text:
            failures.append(f"{path.relative_to(REPO)}: does not state the "
                            f"current test count ({n_tests} tests)")
    repro = (REPO / "docs" / "reproduction.md").read_text(encoding="utf-8")
    if f"CH15 {n_files}/{n_files}" not in repro:
        failures.append(f"docs/reproduction.md: does not state the current "
                        f"CH15 count (CH15 {n_files}/{n_files})")
    print(f"live counts: {n_tests} tests, CH15 {n_files}/{n_files} .py files")
    if failures:
        for line in failures:
            print("DOC COUNT FAILURE:", line)
        return 1
    print("DOC COUNTS OK (no stale counts; current counts present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
