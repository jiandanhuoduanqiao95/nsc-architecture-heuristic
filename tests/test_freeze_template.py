"""Tests for docs/freeze_template.json (C's starting point for freeze.json)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import checks as checks_mod  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "docs" / "freeze_template.json"
FIXTURES = REPO / "tests" / "fixtures"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FreezeTemplateTests(unittest.TestCase):
    def test_template_keys_are_exactly_the_ch18_schema(self):
        self.assertEqual(set(load(TEMPLATE)), checks_mod.FREEZE_KEYS)

    def test_placeholders_are_rejected_by_ch18(self):
        template = load(TEMPLATE)
        self.assertEqual(template["alpha_star"], "<ALPHA_STAR>")
        self.assertEqual(template["beta_star"], "<BETA_STAR>")
        problems = checks_mod.validate_freeze(
            template, load(FIXTURES / "dev_grid_cumulative_example.json"),
            load(FIXTURES / "dev_grid_position_example.json"), False)
        self.assertIn("alpha_star is not a number", problems)
        self.assertIn("beta_star is not a number", problems)

    def test_filled_template_passes_ch18_validation(self):
        grid_cum = load(FIXTURES / "dev_grid_cumulative_example.json")
        grid_pos = load(FIXTURES / "dev_grid_position_example.json")
        filled = load(TEMPLATE)
        filled["alpha_star"] = grid_cum["selected"]
        filled["beta_star"] = grid_pos["selected"]
        self.assertEqual(checks_mod.validate_freeze(filled, grid_cum, grid_pos,
                                                    False), [])

    def test_template_is_not_where_ch18_strict_looks(self):
        # CH18 strict reads the repository-root freeze.json only; the template
        # lives under docs/ so it can never be mistaken for the real freeze.
        self.assertNotEqual(TEMPLATE.resolve(), (REPO / "freeze.json").resolve())
        self.assertFalse((REPO / "freeze.json").exists())
        result = checks_mod.run_checks(only={"CH18"})[0]
        self.assertTrue(result.passed)
        self.assertIn("dry-run", result.detail)


if __name__ == "__main__":
    unittest.main()
