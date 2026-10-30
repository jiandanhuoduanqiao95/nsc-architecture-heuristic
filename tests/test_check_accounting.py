"""Accounting tests: n_failed counts failing CASES, never failure messages.

Forces the seeded bugs from checks/mutations.py onto individual checks and
asserts the case counts: CH08 32/32, CH10 200/200, CH16 100/100 (MU3, multi
contribution) and 80/100 (MU4 — mathematically forced: at alpha=0 the uniform
factor 1/(1+0) is bit-identical to the correct factor, so exactly the 20
alpha=0 cases pass).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import checks as checks_mod  # noqa: E402
from checks import mutations  # noqa: E402


def run_check_under_mutation(check_fn, mutation_id):
    muts = {m[0]: m for m in mutations.build_mutations()}
    undo = mutations.apply(muts[mutation_id][2])
    try:
        dataset = checks_mod.load_dataset()
        return check_fn(dataset, {"freeze_mode": "dry-run"})
    finally:
        undo()


class AccountingInvariantTests(unittest.TestCase):
    def test_plain_run_accounting_holds(self):
        results = checks_mod.run_checks()
        for r in results:
            self.assertTrue(0 <= r.n_failed <= r.n_cases,
                            f"{r.id}: n_failed={r.n_failed} outside "
                            f"[0, {r.n_cases}]")

    def test_ch08_counts_each_config_once_under_mu4(self):
        result = run_check_under_mutation(checks_mod.ch08_single_layer, "MU4")
        self.assertEqual((result.n_failed, result.n_cases), (32, 32))

    def test_ch10_counts_each_config_once_under_mu2(self):
        result = run_check_under_mutation(checks_mod.ch10_alpha_limit, "MU2")
        self.assertEqual((result.n_failed, result.n_cases), (200, 200))

    def test_ch16_counts_each_pair_once_under_mu3(self):
        # MU3 corrupts every layer, so all 100 (config, alpha) cases fail.
        result = run_check_under_mutation(checks_mod.ch16_breakdown_consistency,
                                          "MU3")
        self.assertEqual((result.n_failed, result.n_cases), (100, 100))

    def test_ch16_under_mu4_is_exactly_80_of_100(self):
        # alpha=0 is immune to uniform discounting (1/(1+0) == 1/(1+0*c)),
        # so exactly the 4 non-zero alphas x 20 configs fail.
        result = run_check_under_mutation(checks_mod.ch16_breakdown_consistency,
                                          "MU4")
        self.assertEqual((result.n_failed, result.n_cases), (80, 100))


if __name__ == "__main__":
    unittest.main()
