"""Tests for the strengthened docs-count gate (tools/check_docs_counts.py)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import check_docs_counts as gate  # noqa: E402


class DocCountGateTests(unittest.TestCase):
    def run_gate(self, readme, handoff, repro, n_tests=80, n_files=46):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            files = [root / "README.md", root / "docs" / "HANDOFF_A.md",
                     root / "docs" / "reproduction.md"]
            for path, text in zip(files, (readme, handoff, repro)):
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(gate, "REPO", root), \
                    mock.patch.object(gate, "SCAN_FILES", files), \
                    mock.patch.object(gate, "COUNT_FILES", files):
                failures = gate.count_failures(n_tests, n_files)
                fixed = gate.fix_counts(n_tests, n_files)
                after = gate.count_failures(n_tests, n_files)
        return failures, fixed, after

    def test_current_counts_pass(self):
        ok = "Ran 80 tests ... OK"
        failures, _fixed, _after = self.run_gate(ok, ok, ok + "\nCH15 46/46")
        self.assertEqual(failures, [])

    def test_any_stale_live_count_fails_and_fix_repairs_it(self):
        stale = "Ran 72 tests ... OK and 72 stdlib unit tests"
        failures, fixed, after = self.run_gate(stale, "80 tests", "80 tests CH15 44/44")
        self.assertTrue(any("stale test count 72" in f for f in failures))
        self.assertTrue(any("stale CH15 count 44/44" in f for f in failures))
        self.assertTrue(fixed)
        self.assertEqual(after, [])

    def test_history_wording_is_not_flagged(self):
        text = "80 tests (history: 51 at A2, 72 at a-scorer-final)"
        failures, _fixed, _after = self.run_gate(text, text, text + " CH15 46/46")
        self.assertEqual(failures, [])

    def test_n_ok_form_is_a_test_count(self):
        failures, _fixed, after = self.run_gate("Ran 80 tests | 72 OK |", "80 tests",
                                                "80 tests CH15 46/46")
        self.assertTrue(any("stale test count 72" in f for f in failures))
        self.assertEqual(after, [])

    def test_shell_transcripts_are_verbatim(self):
        transcript = "```\n$ python3 x.py\nlive counts: 72 tests, CH15 44/44\n```\n"
        repro = "80 tests CH15 46/46\n" + transcript
        failures, _fixed, _after = self.run_gate("80 tests", "80 tests", repro)
        self.assertEqual(failures, [])  # pasted output is exempt from the check
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reproduction.md"
            path.write_text(repro, encoding="utf-8")
            with mock.patch.object(gate, "REPO", Path(tmp)), \
                    mock.patch.object(gate, "COUNT_FILES", [path]):
                gate.fix_counts(80, 46)
            self.assertIn("live counts: 72 tests, CH15 44/44", path.read_text())

    def test_blacklisted_counts_fail(self):
        text = "80 tests; old line says 31/31"
        failures, _fixed, _after = self.run_gate(text, "80 tests", "80 tests CH15 46/46")
        self.assertTrue(any("'31/31'" in f for f in failures))


if __name__ == "__main__":
    unittest.main()
