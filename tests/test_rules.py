"""Unit tests for the frozen selection rules (C4 tie-break, 1,000/200 prefix).

These mirror the tool self-tests (`tools/select_alpha.py --self-test`,
`tools/selection_ext.py --self-test`) inside the unittest suite so the rules
are covered by `python3 -m unittest discover` as well.
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evaluate  # noqa: E402
from tools.select_alpha import canonical_rho, select_from_rho  # noqa: E402
from tools.selection_ext import select_trials_ext  # noqa: E402


class SelectFromRhoTests(unittest.TestCase):
    """C4: max dev rho; ties at 12 significant digits pick the smaller alpha."""

    def test_plain_argmax(self):
        picked, tied = select_from_rho({0.0: 0.90, 0.25: 0.95, 0.5: 0.93})
        self.assertEqual((picked, tied), (0.25, False))

    def test_twelve_digit_tie_picks_smaller(self):
        base = 0.12345678901234
        wobble = _nextafter(base)
        self.assertEqual(format(base, ".12g"), format(wobble, ".12g"))
        picked, tied = select_from_rho({0.5: wobble, 2.0: base})
        self.assertEqual((picked, tied), (0.5, True))

    def test_none_rho_is_worst(self):
        picked, tied = select_from_rho({0.0: None, 0.25: 0.4, 0.5: None})
        self.assertEqual((picked, tied), (0.25, False))

    def test_two_none_rhos_tie_to_smaller(self):
        picked, tied = select_from_rho({0.0: None, 0.25: None})
        self.assertEqual((picked, tied), (0.0, True))

    def test_canonical_rho_minus_inf_for_constant_scores(self):
        # canonical_rho maps evaluate.correlation's None to -inf so that
        # select_from_rho can treat constant scores as worst uniformly.
        import math
        rho = canonical_rho([1.0, 1.0, 1.0], [30.0, 20.0, 10.0])
        self.assertEqual(rho, -math.inf)


def _nextafter(x):
    import math
    return math.nextafter(x, 1.0)


class SelectionExtTests(unittest.TestCase):
    """TA 2: repeats=1000 main protocol; the 200 runs are its exact prefix."""

    def test_prefix_property(self):
        pool = list(range(30))
        scores = [round(random.Random(7).uniform(50, 500), 6) for _ in range(30)]
        ppl = [round(random.Random(8).uniform(20, 80), 6) for _ in range(30)]
        long_run = select_trials_ext(pool, scores, 3, ppl, 202627, repeats=1000,
                                     return_trials=True)
        short_run = select_trials_ext(pool, scores, 3, ppl, 202627, repeats=200,
                                      return_trials=True)
        self.assertEqual(long_run["best_ppl_trials"][:200],
                         short_run["best_ppl_trials"])
        self.assertEqual(long_run["trials"], 1000)

    def test_parity_with_harness_on_fixed_case(self):
        pool = [0, 1, 2, 3, 4]
        scores = [5.0, 3.0, 4.0, 1.0, 2.0]
        ppl = [40.0, 55.0, 48.0, 70.0, 61.0]
        for k in (1, 3):
            for seed in (1, 202627):
                mine = select_trials_ext(pool, scores, k, ppl, seed, repeats=200)
                theirs = evaluate.select_trials(pool, scores, k, ppl, seed)
                self.assertEqual(mine, theirs)  # exact float equality, all keys

    def test_parity_random_baseline(self):
        pool = [0, 1, 2, 3]
        ppl = [40.0, 55.0, 48.0, 70.0]
        mine = select_trials_ext(pool, None, 2, ppl, 42, repeats=200)
        theirs = evaluate.select_trials(pool, None, 2, ppl, 42)
        self.assertEqual(mine, theirs)


if __name__ == "__main__":
    unittest.main()
