"""Tests for the Python 3.9 / stdlib-only rule (checks/py39_rules.py, CH15)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import py39_rules  # noqa: E402

NEEDED = {"inspect", "fractions", "unittest", "builtins", "json", "xml", "html",
          "statistics", "csv", "math", "sqlite3", "argparse", "importlib"}
THIRD_PARTY = {"numpy", "pandas", "scipy", "pytest", "sklearn"}


class StdlibNamesTests(unittest.TestCase):
    def test_derived_names_cover_the_stdlib_and_skip_site_packages(self):
        names = py39_rules.interpreter_stdlib_names()
        self.assertTrue(NEEDED <= names, NEEDED - names)
        self.assertFalse(THIRD_PARTY & names, THIRD_PARTY & names)

    def test_forced_py39_path_accepts_stdlib_rejects_third_party(self):
        names = py39_rules.stdlib_names(module_names=None)  # 3.9 code path
        self.assertTrue(NEEDED <= names)
        self.assertFalse(THIRD_PARTY & names)

    def test_scan_file_still_flags_third_party_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "probe.py"
            path.write_text("import json\nimport numpy\nfrom pytest import fixture\n",
                            encoding="utf-8")
            syntax, imports = py39_rules.scan_file(path)
        self.assertEqual(syntax, [])
        self.assertEqual(len(imports), 2)
        self.assertTrue(any("'numpy'" in v for v in imports))
        self.assertTrue(any("'pytest'" in v for v in imports))

    def test_scan_file_rejects_post_39_syntax(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "probe.py"
            path.write_text("match 1:\n    case 1:\n        pass\n", encoding="utf-8")
            syntax, _imports = py39_rules.scan_file(path)
        self.assertEqual(len(syntax), 1)

    def test_repository_is_clean(self):
        self.assertEqual(py39_rules.scan_tree(), [])


if __name__ == "__main__":
    unittest.main()
