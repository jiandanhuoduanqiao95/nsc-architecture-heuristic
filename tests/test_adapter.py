"""Unit tests for ctxnsc.adapter (schema boundary via nsc.layers)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nsc
from ctxnsc.adapter import spec_from_config
from ctxnsc.specs import ArchitectureSpec, LayerSpec

REPO = Path(__file__).resolve().parents[1]


def archive_config_with_embed_mismatch():
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    for key in sorted(configs):
        cfg = configs[key]
        if cfg["d_embed"] != cfg["d_model"]:
            return key, cfg
    raise AssertionError("archive has no d_embed != d_model config")


class SpecFromConfigTests(unittest.TestCase):
    def test_matches_nsc_layers(self):
        cfg = {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
               "d_inner": [256, 512], "weight_init_std": 0.02}
        d, heads, inner = nsc.layers(cfg)
        spec = spec_from_config(cfg)
        self.assertEqual([l.hidden for l in spec.layers], [d] * len(heads))
        self.assertEqual([l.heads for l in spec.layers], heads)
        self.assertEqual([l.ffn for l in spec.layers], inner)
        self.assertEqual(spec.init_std, 0.02)

    def test_uses_d_model_not_d_embed(self):
        key, cfg = archive_config_with_embed_mismatch()
        spec = spec_from_config(cfg)
        self.assertEqual(spec.layers[0].hidden, cfg["d_model"])
        self.assertNotEqual(spec.layers[0].hidden, cfg["d_embed"])
        self.assertTrue(key)  # the mismatch case really exists

    def test_missing_weight_init_std_raises(self):
        cfg = {"d_model": 128, "n_layer": 1, "n_head": 4, "d_inner": 256}
        with self.assertRaises(KeyError):
            spec_from_config(cfg)

    def test_unexpected_sigma_raises(self):
        cfg = {"d_model": 128, "n_layer": 1, "n_head": 4, "d_inner": 256,
               "weight_init_std": 0.01}
        with self.assertRaises(ValueError):
            spec_from_config(cfg)

    def test_scalar_heads_and_inner_expand(self):
        cfg = {"d_model": 128, "n_layer": 3, "n_head": 4, "d_inner": 256,
               "weight_init_std": 0.02}
        spec = spec_from_config(cfg)
        self.assertEqual(len(spec.layers), 3)
        for layer in spec.layers:
            self.assertEqual((layer.hidden, layer.heads, layer.ffn),
                             (128, 4, 256))

    def test_invalid_divisibility_raises(self):
        cfg = {"d_model": 128, "n_layer": 1, "n_head": 3, "d_inner": 256,
               "weight_init_std": 0.02}
        with self.assertRaises(ValueError):
            spec_from_config(cfg)

    def test_spec_is_frozen(self):
        cfg = {"d_model": 128, "n_layer": 1, "n_head": 4, "d_inner": 256,
               "weight_init_std": 0.02}
        spec = spec_from_config(cfg)
        with self.assertRaises(Exception):
            spec.layers[0].hidden = 64

    def test_name_is_debug_label_only(self):
        base = {"d_model": 128, "n_layer": 1, "n_head": 4, "d_inner": 256,
                "weight_init_std": 0.02}
        labelled = dict(base, _id="config_secret_x")
        self.assertEqual(spec_from_config(labelled).name, "config_secret_x")
        self.assertEqual(spec_from_config(base).name, "")
        # The label never leaks into any score.
        from ctxnsc import score_spec
        self.assertEqual(score_spec(spec_from_config(base), 1.0),
                         score_spec(spec_from_config(labelled), 1.0))


if __name__ == "__main__":
    unittest.main()
