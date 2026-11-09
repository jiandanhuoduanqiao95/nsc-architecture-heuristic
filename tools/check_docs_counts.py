#!/usr/bin/env python3
"""Docs-vs-reality count gate (self-review SR-3 follow-up, strengthened at handoff).

Fails when the human-facing docs drift from the live numbers:

1. stale-count blacklist: ``51 tests`` / ``51 unit`` / ``51 OK`` / ``31/31``
   must not appear in README.md or docs/*.md (they were the pre-self-review
   counts);
2. current-state docs (README.md, docs/HANDOFF_A.md, docs/reproduction.md):
   EVERY ``<n> tests`` / ``<n> unit tests`` / ``<n> stdlib unit tests``
   mention must equal the LIVE unittest count, and every ``CH15 <a>/<b>``
   mention must equal the LIVE .py file count (CH15's n); historical notes
   in these files must be worded without those patterns;
3. current-count presence: the live test count must appear in all three
   files and ``CH15 <n>/<n>`` in reproduction.md.

The live test count comes from unittest discovery itself (identical to the
``Ran N tests`` line), not from grepping source text.

Run from anywhere: ``python3 tools/check_docs_counts.py``
``--fix`` rewrites only the live-count mentions (rule 2 patterns) in the three
current-state docs to the live values, then re-checks.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from checks.py39_rules import iter_repo_py_files  # noqa: E402

BLACKLIST = re.compile(r"\b51 tests\b|\b51 unit\b|\b51 OK\b|\b31/31\b"
                       r"|\b66 cited\b|\b42 re-resolved\b|\b108 tests\b")
TEST_COUNT = re.compile(r"\b(\d+) (?:stdlib )?(?:unit )?tests\b|\b(\d+) OK\b")
CH15_COUNT = re.compile(r"\bCH15 (\d+)/(\d+)\b")
SCAN_FILES = [REPO / "README.md"] + sorted((REPO / "docs").glob("*.md"))
COUNT_FILES = [REPO / "README.md", REPO / "docs" / "HANDOFF_A.md",
               REPO / "docs" / "reproduction.md"]


def live_test_count():
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(REPO / "tests"), top_level_dir=str(REPO))
    return suite.countTestCases()


def live_py_file_count():
    return sum(1 for _ in iter_repo_py_files())


TRANSCRIPT = re.compile(r"^```[^\n]*\n\$ .*?^```", re.M | re.S)


def _segments(text):
    """Split into (is_transcript, chunk): fenced blocks whose first line starts
    with '$ ' are pasted shell transcripts — exempt from checking and --fix so
    they stay verbatim; every other region (incl. instruction blocks) counts."""
    out, pos = [], 0
    for match in TRANSCRIPT.finditer(text):
        out.append((False, text[pos:match.start()]))
        out.append((True, match.group(0)))
        pos = match.end()
    out.append((False, text[pos:]))
    return out


def _checked_text(text):
    """Text with transcripts blanked (same length/newlines, so line numbers hold)."""
    return "".join(re.sub(r"[^\n]", " ", chunk) if is_t else chunk
                   for is_t, chunk in _segments(text))


def _number(groups):
    return next(g for g in groups if g is not None)


def count_failures(n_tests, n_files):
    failures = []
    for path in SCAN_FILES:
        text = _checked_text(path.read_text(encoding="utf-8"))
        for match in BLACKLIST.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start: line_end if line_end != -1 else len(text)]
            if "historical" in line.lower():
                continue  # pasted/historical captures carry an explicit marker
            failures.append(f"{path.relative_to(REPO)}: stale count "
                            f"{match.group(0)!r}")
    for path in COUNT_FILES:
        text = _checked_text(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO)
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in _matches_with_lines(TEST_COUNT, text):
            if int(_number(number)) != n_tests and \
                    not _is_historical(raw_lines, line):
                failures.append(f"{rel}:{line}: stale test count "
                                f"{_number(number)} (live {n_tests})")
        for number, line in _matches_with_lines(CH15_COUNT, text):
            if (int(number[0]), int(number[1])) != (n_files, n_files) and \
                    not _is_historical(raw_lines, line):
                failures.append(f"{rel}:{line}: stale CH15 count "
                                f"{number[0]}/{number[1]} (live {n_files}/{n_files})")
        if f"{n_tests} tests" not in text:
            failures.append(f"{rel}: does not state the current test count "
                            f"({n_tests} tests)")
    repro = _checked_text((REPO / "docs" / "reproduction.md").read_text(encoding="utf-8"))
    if f"CH15 {n_files}/{n_files}" not in repro:
        failures.append(f"docs/reproduction.md: does not state the current "
                        f"CH15 count (CH15 {n_files}/{n_files})")
    return failures


def _is_historical(raw_lines, line_number):
    """A stale count on a line explicitly marked 'historical' is allowed (the
    annotated section-12 capture in docs/reproduction.md)."""
    return "historical" in raw_lines[line_number - 1].lower()


def _matches_with_lines(pattern, text):
    for match in pattern.finditer(text):
        yield match.groups(), text.count("\n", 0, match.start()) + 1


def fix_counts(n_tests, n_files):
    """Rewrite every live-count mention in the current-state docs (--fix)."""
    changed = []
    for path in COUNT_FILES:
        text = path.read_text(encoding="utf-8")
        raw_lines = text.splitlines()
        parts = []
        for is_transcript, chunk in _segments(text):
            if not is_transcript:
                offset = sum(len(c) + 1 for c in parts[:len(parts)])
                for match in TEST_COUNT.finditer(chunk):
                    line = raw_lines[offset + text.count("\n", 0, match.start(0))]
                    if _is_historical(raw_lines, offset
                                      + text.count("\n", 0, match.start(0)) + 1):
                        continue
                    chunk = chunk.replace(match.group(0),
                                          match.group(0).replace(
                                              _number(match.groups()), str(n_tests), 1),
                                          1)
                chunk = CH15_COUNT.sub(f"CH15 {n_files}/{n_files}", chunk)
            parts.append(chunk)
        new = "".join(parts)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(str(path.relative_to(REPO)))
    return changed


def main():
    n_tests = live_test_count()
    n_files = live_py_file_count()
    if "--fix" in sys.argv[1:]:
        changed = fix_counts(n_tests, n_files)
        print(f"--fix: rewrote live counts in {changed or 'no files'}")
    failures = count_failures(n_tests, n_files)
    print(f"live counts: {n_tests} tests, CH15 {n_files}/{n_files} .py files")
    if failures:
        for line in failures:
            print("DOC COUNT FAILURE:", line)
        return 1
    print("DOC COUNTS OK (no stale counts; current counts present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
