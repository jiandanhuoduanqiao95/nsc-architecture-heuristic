"""Unit tests for ctxnsc.terms and ctxnsc.mp (starter grouping preserved)."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nsc
from ctxnsc.mp import psi
from ctxnsc.specs import ArchitectureSpec, LayerSpec
from ctxnsc.terms import layer_terms, per_layer_terms


def toy_config():
    return {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
            "d_inner": [256, 512], "weight_init_std": 0.02}


class PsiTests(unittest.TestCase):
    def test_transpose_invariance(self):
        self.assertEqual(psi(128, 32), psi(32, 128))

    def test_known_value(self):
        self.assertEqual(psi(128, 32), 1.5884174437376406)

    def test_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            psi(0, 8)
        with self.assertRaises(ValueError):
            psi(8, -1)

    def test_rejects_float_and_bool(self):
        # Use primes no other test touches: psi_mp's lru_cache keys suffer
        # int/float aliasing (hash(128.0) == hash(128)), so a previously
        # cached psi_mp(128, 32) makes psi_mp(128.0, 32) return the cached
        # value without re-running the int validation. On a cold cache the
        # float dimension raises; that is the behavior under test here.
        with self.assertRaises(ValueError):
            psi(104729.0, 1299709)  # float dimension: psi_mp demands ints
        with self.assertRaises(ValueError):
            psi(True, 15485863)

    def test_zero_sigma_gives_zero(self):
        self.assertEqual(nsc.psi_mp(64, 64, 0.0), 0.0)


class LayerTermsTests(unittest.TestCase):
    def test_bitwise_matches_layer_capacities(self):
        cfg = toy_config()
        caps = nsc.layer_capacities(cfg)
        spec = ArchitectureSpec(layers=(LayerSpec(128, 4, 256), LayerSpec(128, 4, 512)))
        terms = per_layer_terms(spec)
        self.assertEqual(len(terms), 2)
        for term, cap in zip(terms, caps):
            self.assertEqual(term.attn + term.ffn, cap)  # bitwise

    def test_attn_includes_output_projection(self):
        d, h, f = 128, 4, 512
        term = layer_terms(LayerSpec(d, h, f))
        expected_attn = 3 * h * psi(d, d // h) + psi(d, d)
        self.assertEqual(term.attn, expected_attn)

    def test_ffn_is_two_projections(self):
        d, h, f = 128, 4, 512
        term = layer_terms(LayerSpec(d, h, f))
        self.assertEqual(term.ffn, 2 * psi(d, f))

    def test_attn_factor_order_mirrors_starter(self):
        # 3*h first, then times psi, then plus psi(d, d): any reordering
        # (e.g. 3 * psi * h) can differ in the last ULP.
        d, h, f = 256, 8, 1024
        term = layer_terms(LayerSpec(d, h, f))
        self.assertEqual(term.attn, 3 * h * psi(d, d // h) + psi(d, d))
        self.assertEqual(term.attn + term.ffn,
                         nsc.layer_capacities({"d_model": d, "n_layer": 1,
                                               "n_head": h, "d_inner": f})[0])

    def test_per_layer_terms_uses_spec_sigma(self):
        spec = ArchitectureSpec(layers=(LayerSpec(64, 1, 128),), init_std=0.02)
        terms = per_layer_terms(spec)
        self.assertEqual(terms[0].ffn, 2 * psi(64, 128, 0.02))

    def test_sigma_changes_terms(self):
        d, h, f = 128, 4, 256
        self.assertNotEqual(layer_terms(LayerSpec(d, h, f), 0.02).ffn,
                            layer_terms(LayerSpec(d, h, f), 0.01).ffn)


class SpecValidationTests(unittest.TestCase):
    def test_rejects_empty_layers(self):
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=())

    def test_rejects_non_positive_dims(self):
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(0, 1, 8),))
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(64, 1, 0),))
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(64, -2, 8),))

    def test_rejects_indivisible_heads(self):
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(128, 3, 256),))

    def test_rejects_non_positive_sigma(self):
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(64, 1, 128),), init_std=0.0)
        with self.assertRaises(ValueError):
            ArchitectureSpec(layers=(LayerSpec(64, 1, 128),), init_std=-0.02)

    def test_len_returns_layer_count(self):
        spec = ArchitectureSpec(layers=(LayerSpec(64, 1, 128),
                                        LayerSpec(64, 2, 256)))
        self.assertEqual(len(spec), 2)


if __name__ == "__main__":
    unittest.main()
