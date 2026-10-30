"""Unit tests for ctxnsc.score: toy anchors, exactness, limits, M3 primitive."""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nsc
from ctxnsc import (position_ratios, score_config, score_spec,
                    score_with_ratios, scores_for_alphas)
from ctxnsc.adapter import spec_from_config
from ctxnsc.prefix import cumulative_ratios
from ctxnsc.score import score_terms
from ctxnsc.terms import layer_terms
from ctxnsc.specs import ArchitectureSpec, LayerSpec

REPO = Path(__file__).resolve().parents[1]


def toy(order):
    ffn = [256, 512] if order == "late" else [512, 256]
    return {"d_model": 128, "n_layer": 2, "n_head": [4, 4], "d_inner": ffn,
            "weight_init_std": 0.02}


# Plan §1.7 S(alpha) table for the two toy orders (9 decimals). The
# "infinity" row is realized at alpha = 1e12 (discount_factors rejects
# non-finite alpha by design; CH10 uses the same probe).
TOY_TABLE = {
    ("late", 0.0): 121.820169804, ("late", 0.25): 117.487538338,
    ("late", 0.5): 113.889274555, ("late", 1.0): 108.257252069,
    ("late", 2.0): 100.790156278, ("late", 1e12): 75.029376696,
    ("early", 0.0): 121.820169804, ("early", 0.25): 118.672843897,
    ("early", 0.5): 116.244184056, ("early", 1.0): 112.741286801,
    ("early", 2.0): 108.583607933, ("early", 1e12): 97.400699829,
}

ALPHAS = (0.0, 0.25, 0.5, 1.0, 2.0)


def sample_configs(n=10):
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    keys = sorted(configs)
    return [configs[k] for k in keys[:: max(1, len(keys) // n)][:n]]


class ToyAnchorTests(unittest.TestCase):
    def test_toy_table_both_orders(self):
        for (order, alpha), expected in TOY_TABLE.items():
            value = score_config(toy(order), alpha)
            self.assertTrue(math.isclose(value, expected, rel_tol=1e-9),
                            f"{order} alpha={alpha}: {value} vs {expected}")

    def test_toy_orders_tie_at_alpha_zero(self):
        self.assertEqual(score_config(toy("late"), 0.0),
                         score_config(toy("early"), 0.0))

    def test_reordered_pair_prefer_early_large_ffn(self):
        # Direction rule: moving the larger FFN earlier strictly increases
        # S(alpha) for alpha > 0.
        for alpha in ALPHAS[1:]:
            self.assertGreater(score_config(toy("early"), alpha),
                               score_config(toy("late"), alpha))


class ExactnessTests(unittest.TestCase):
    def test_alpha0_bitwise_on_archive_sample(self):
        for cfg in sample_configs():
            self.assertEqual(score_config(cfg, 0.0), nsc.original_nsc(cfg))

    def test_alpha0_bitwise_on_full_panel(self):
        configs = json.loads((REPO / "data" / "architectures.json").read_text())
        for key, cfg in configs.items():
            self.assertEqual(score_config(cfg, 0.0), nsc.original_nsc(cfg),
                             f"alpha=0 mismatch on {key}")

    def test_no_special_case_structure(self):
        # alpha=0 must flow through discount_factors: the factor is exactly 1.0
        # and ffn * 1.0 is exact, so the fsum sees identical addends.
        terms = [layer_terms(LayerSpec(128, 4, 256)),
                 layer_terms(LayerSpec(128, 4, 512))]
        ratios = cumulative_ratios(terms)
        factors = [1.0 / (1.0 + 0.0 * c) for c in ratios]
        self.assertEqual(factors, [1.0, 1.0])
        self.assertEqual(score_terms(terms, 0.0),
                         math.fsum(t.attn + t.ffn * f
                                   for t, f in zip(terms, factors)))


class MonotonicityAndLimitsTests(unittest.TestCase):
    def test_alpha_monotone_decreasing(self):
        cfg = {"d_model": 256, "n_layer": 4, "n_head": [4, 8, 8, 4],
               "d_inner": [512, 1024, 768, 2048], "weight_init_std": 0.02}
        scores = [score_config(cfg, a) for a in ALPHAS]
        for a, b in zip(scores, scores[1:]):
            self.assertLess(b, a)  # strictly decreasing for L >= 2

    def test_single_layer_invariant(self):
        spec = ArchitectureSpec(layers=(LayerSpec(128, 4, 512),))
        s0 = score_spec(spec, 0.0)
        self.assertEqual(s0, nsc.original_nsc(
            {"d_model": 128, "n_layer": 1, "n_head": 4, "d_inner": 512}))
        for alpha in (0.0, 0.25, 0.5, 1.0, 2.0, 100.0):
            self.assertEqual(score_spec(spec, alpha), s0)  # bitwise for all alpha

    def test_limit_is_sum_attn_plus_first_ffn(self):
        for order in ("late", "early"):
            cfg = toy(order)
            spec = spec_from_config(cfg)
            terms = [layer_terms(l) for l in spec.layers]
            expected = (math.fsum(t.attn for t in terms) + terms[0].ffn)
            self.assertTrue(math.isclose(score_config(cfg, 1e12), expected,
                                         rel_tol=1e-9))
            plain_sum_attn = math.fsum(t.attn for t in terms)
            # The limit must NOT be the attention-only sum (first FFN survives).
            self.assertGreater(score_config(cfg, 1e12) - plain_sum_attn, 1.0)

    def test_rejects_negative_alpha(self):
        with self.assertRaises(ValueError):
            score_config(toy("late"), -0.5)


class InterfaceTests(unittest.TestCase):
    def test_score_config_matches_score_spec(self):
        cfg = sample_configs(3)[1]
        self.assertEqual(score_config(cfg, 0.5),
                         score_spec(spec_from_config(cfg), 0.5))

    def test_scores_for_alphas_matches_single_calls(self):
        cfg = sample_configs(3)[2]
        batch = scores_for_alphas(cfg, ALPHAS)
        for alpha in ALPHAS:
            self.assertEqual(batch[alpha], score_config(cfg, alpha))  # bitwise

    def test_scores_for_alphas_accepts_spec(self):
        cfg = sample_configs(3)[0]
        spec = spec_from_config(cfg)
        self.assertEqual(scores_for_alphas(spec, (0.5,))[0.5],
                         scores_for_alphas(cfg, (0.5,))[0.5])

    def test_m3_primitive_bitwise_against_independent_formula(self):
        # DoD 11: score_with_ratios(config, beta, position_ratios(L)) must equal
        # an independently written sum of A_l + F_l/(1+beta*(l+1)/L), bitwise.
        betas = (0.0, 0.25, 0.5, 1.0, 2.0)
        for cfg in sample_configs():
            d = cfg["d_model"]
            heads = cfg["n_head"]
            inner = cfg["d_inner"]
            if isinstance(heads, int):
                heads = [heads] * cfg["n_layer"]
            if isinstance(inner, int):
                inner = [inner] * cfg["n_layer"]
            length = len(heads)
            attns = [3 * h * nsc.psi_mp(d, d // h) + nsc.psi_mp(d, d)
                     for h in heads]
            ffns = [2 * nsc.psi_mp(d, f) for f in inner]
            for beta in betas:
                expected = math.fsum(
                    attns[i] + ffns[i] * (1.0 / (1.0 + beta * (i + 1) / length))
                    for i in range(length))
                got = score_with_ratios(cfg, beta, position_ratios(length))
                self.assertEqual(got, expected,
                                 f"M3 primitive mismatch at beta={beta}")


if __name__ == "__main__":
    unittest.main()
