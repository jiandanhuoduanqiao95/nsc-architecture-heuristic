"""Tests for the shared parity comparator (D0-1 rule, version gate,
post-freeze filtering) — the ONE comparator behind CH03 and
tools/compare_expected.py."""
import copy
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import checks as checks_mod  # noqa: E402
from checks.parity import (compare_payloads, post_freeze_violations,  # noqa: E402
                           sd_tolerance_allowed)

REPO = Path(__file__).resolve().parents[1]


def expected_fixture():
    return json.loads((REPO / "expected_development.json").read_text())


def bump_ulps(x, n):
    for _ in range(n):
        x = math.nextafter(x, math.inf)
    return x


class D0_1RuleTests(unittest.TestCase):
    def test_sd_field_1ulp_tolerated_when_gate_on(self):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        key = "$.selection[2].methods.random.sd_best_ppl"
        node = actual["selection"][2]["methods"]["random"]
        node["sd_best_ppl"] = bump_ulps(node["sd_best_ppl"], 1)
        violations, tolerated, checked = compare_payloads(expected, actual,
                                                          allow_d0_1=True)
        self.assertEqual(violations, [])
        self.assertEqual(len(tolerated), 1)
        self.assertIn("(ULP=1)", tolerated[0])
        self.assertEqual(checked, 8)

    def test_sd_field_1ulp_fails_when_gate_off(self):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        node = actual["selection"][2]["methods"]["random"]
        node["sd_best_ppl"] = bump_ulps(node["sd_best_ppl"], 1)
        violations, tolerated, checked = compare_payloads(expected, actual,
                                                          allow_d0_1=False)
        self.assertEqual(len(violations), 1)
        self.assertEqual(tolerated, [])

    def test_sd_field_2ulp_fails_even_when_gate_on(self):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        node = actual["selection"][2]["methods"]["random"]
        node["sd_best_ppl"] = bump_ulps(node["sd_best_ppl"], 2)
        violations, _t, _n = compare_payloads(expected, actual, allow_d0_1=True)
        self.assertEqual(len(violations), 1)

    def test_other_field_1ulp_always_fails(self):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        rho = actual["ranking"]["original_nsc"]["spearman_rho"]
        actual["ranking"]["original_nsc"]["spearman_rho"] = bump_ulps(rho, 1)
        for gate in (True, False):
            violations, _t, _n = compare_payloads(expected, actual, allow_d0_1=gate)
            self.assertEqual(len(violations), 1)

    def test_default_gate_follows_interpreter(self):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        node = actual["selection"][2]["methods"]["random"]
        node["sd_best_ppl"] = bump_ulps(node["sd_best_ppl"], 1)
        violations, tolerated, _n = compare_payloads(expected, actual)
        if sd_tolerance_allowed():
            self.assertEqual(violations, [])
            self.assertEqual(len(tolerated), 1)
        else:
            self.assertEqual(len(violations), 1)


class PostFreezeFilterTests(unittest.TestCase):
    def violations_by_path(self, mutate):
        expected = expected_fixture()
        actual = copy.deepcopy(expected)
        mutate(actual)
        violations, _t, _n = compare_payloads(expected, actual,
                                              allow_d0_1=False)
        return violations

    def test_student_and_ablation_diffs_are_filtered(self):
        def mutate(actual):
            actual["ranking"]["student"]["spearman_rho"] = 0.123456
            actual["ranking"]["ablation"]["spearman_rho"] = 0.654321
            actual["selection"][0]["methods"]["student"]["mean_best_ppl"] = 1.0
            actual["selection"][3]["methods"]["ablation"]["mean_regret"] = 9.0
        remaining = post_freeze_violations(self.violations_by_path(mutate))
        self.assertEqual(remaining, [])

    def test_baseline_selection_diffs_survive_the_filter(self):
        def mutate(actual):
            actual["selection"][0]["eligible"] += 1            # structural
            actual["selection"][1]["oracle_ppl"] = 1.0         # oracle
            actual["selection"][0]["methods"]["random"]["mean_best_ppl"] = 2.0
            actual["ranking"]["original_nsc"]["spearman_rho"] = 0.5
        remaining = post_freeze_violations(self.violations_by_path(mutate))
        self.assertEqual(len(remaining), 4)

    def test_ch03_post_freeze_end_to_end(self):
        expected = expected_fixture()

        def student_only(actual):
            actual["ranking"]["student"]["spearman_rho"] = 0.9
            actual["selection"][0]["methods"]["ablation"]["mean_regret"] = 7.0

        def baseline_too(actual):
            student_only(actual)
            actual["selection"][0]["oracle_ppl"] = 3.0

        # ALPHA=0.5: only student/ablation diffs -> CH03 passes.
        actual = copy.deepcopy(expected)
        student_only(actual)
        failures, _v, _t, _n = checks_mod.parity_failure_entries(
            expected, actual, alpha=0.5)
        self.assertEqual(failures, [])
        # ALPHA=0.5: a baseline selection diff -> CH03 must FAIL.
        actual = copy.deepcopy(expected)
        baseline_too(actual)
        failures, _v, _t, _n = checks_mod.parity_failure_entries(
            expected, actual, alpha=0.5)
        self.assertEqual(len(failures), 1)
        # ALPHA=0.0: student diffs are violations too.
        actual = copy.deepcopy(expected)
        student_only(actual)
        failures, _v, _t, _n = checks_mod.parity_failure_entries(
            expected, actual, alpha=0.0)
        self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
