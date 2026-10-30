"""Unit tests for ctxnsc.prefix (strict prefixes, discounts, M3 hook)."""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nsc
from ctxnsc.adapter import spec_from_config
from ctxnsc.prefix import (cumulative_ratios, discount_factors,
                           position_ratios, s0_from_terms)
from ctxnsc.terms import per_layer_terms

REPO = Path(__file__).resolve().parents[1]


def sample_configs(n=10):
    """Deterministic sample of archive configs for bitwise comparisons."""
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    keys = sorted(configs)
    return [configs[k] for k in keys[:: max(1, len(keys) // n)][:n]]


class S0Tests(unittest.TestCase):
    def test_bitwise_matches_original_nsc(self):
        for cfg in sample_configs():
            spec = spec_from_config(cfg)
            terms = per_layer_terms(spec)
            self.assertEqual(s0_from_terms(terms), nsc.original_nsc(cfg))


class CumulativeRatiosTests(unittest.TestCase):
    def test_first_ratio_is_exact_zero(self):
        for cfg in sample_configs(5):
            terms = per_layer_terms(spec_from_config(cfg))
            self.assertEqual(cumulative_ratios(terms)[0], 0.0)

    def test_ratios_strictly_increasing(self):
        for cfg in sample_configs():
            ratios = cumulative_ratios(per_layer_terms(spec_from_config(cfg)))
            for a, b in zip(ratios, ratios[1:]):
                self.assertLess(a, b)

    def test_last_ratio_below_one(self):
        for cfg in sample_configs(5):
            ratios = cumulative_ratios(per_layer_terms(spec_from_config(cfg)))
            self.assertLess(ratios[-1], 1.0)

    def test_last_ratio_identity(self):
        # ratios[-1] == 1 - (A_L + F_L)/S0 up to 1e-15 (CH07's tolerance).
        for cfg in sample_configs(5):
            terms = per_layer_terms(spec_from_config(cfg))
            ratios = cumulative_ratios(terms)
            expected = 1.0 - (terms[-1].attn + terms[-1].ffn) / s0_from_terms(terms)
            self.assertLessEqual(abs(ratios[-1] - expected), 1e-15)

    def test_matches_manual_prefix_convention(self):
        cfg = {"d_model": 128, "n_layer": 3, "n_head": [4, 8, 2],
               "d_inner": [256, 512, 1024], "weight_init_std": 0.02}
        spec = spec_from_config(cfg)
        terms = per_layer_terms(spec)
        caps = [t.attn + t.ffn for t in terms]
        s0 = math.fsum(caps)
        manual, prefix = [], []
        for cap in caps:
            manual.append(math.fsum(prefix) / s0)
            prefix.append(cap)
        self.assertEqual(cumulative_ratios(terms), manual)  # bitwise

    def test_rejects_empty(self):
        from ctxnsc.specs import ArchitectureSpec, LayerSpec
        spec = ArchitectureSpec(layers=(LayerSpec(64, 1, 128),))
        with self.assertRaises(ValueError):
            cumulative_ratios([])


class DiscountFactorsTests(unittest.TestCase):
    def test_first_factor_is_one_for_any_alpha(self):
        cfg = sample_configs(1)[0]
        ratios = cumulative_ratios(per_layer_terms(spec_from_config(cfg)))
        for alpha in (0.0, 0.25, 0.5, 1.0, 2.0, 1e12):
            self.assertEqual(discount_factors(ratios, alpha)[0], 1.0)

    def test_matches_formula(self):
        cfg = sample_configs(1)[0]
        ratios = cumulative_ratios(per_layer_terms(spec_from_config(cfg)))
        alpha = 0.5
        self.assertEqual(discount_factors(ratios, alpha),
                         [1.0 / (1.0 + alpha * c) for c in ratios])

    def test_rejects_negative_and_nan(self):
        ratios = [0.0, 0.5]
        with self.assertRaises(ValueError):
            discount_factors(ratios, -0.1)
        with self.assertRaises(ValueError):
            discount_factors(ratios, math.nan)
        with self.assertRaises(ValueError):
            discount_factors(ratios, math.inf)


class PositionRatiosTests(unittest.TestCase):
    def test_values_are_i_plus_one_over_L(self):
        self.assertEqual(position_ratios(4), [0.25, 0.5, 0.75, 1.0])

    def test_matches_position_example_weights(self):
        # nsc.position_example uses weight (i+1)/L with i starting at 0.
        cfg = {"d_model": 128, "n_layer": 3, "n_head": 4, "d_inner": 256,
               "weight_init_std": 0.02}
        weights = position_ratios(cfg["n_layer"])
        caps = nsc.layer_capacities(cfg)
        expected = math.fsum(w * v for w, v in zip(weights, caps))
        self.assertEqual(expected, nsc.position_example(cfg))

    def test_rejects_non_positive_length(self):
        with self.assertRaises(ValueError):
            position_ratios(0)
        with self.assertRaises(ValueError):
            position_ratios(-3)


if __name__ == "__main__":
    unittest.main()
