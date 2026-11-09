"""Tests for the M3 position-only variant modules (tools/make_position_variants.py)."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctxnsc  # noqa: E402
import nsc  # noqa: E402
from tools import make_position_variants as mpv  # noqa: E402
from tools.make_variants import load_module  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class PositionVariantTests(unittest.TestCase):
    def test_committed_variants_equal_the_generator_output(self):
        for beta in mpv.GRID:
            path = mpv.variant_path(beta)
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.read_text(encoding="utf-8"),
                             mpv.M3_TEMPLATE.format(beta=beta))

    def test_verify_passes(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mpv.verify(), 0)
        self.assertIn("M3 VARIANTS OK", out.getvalue())

    def test_beta_half_matches_primitive_and_independent_formula(self):
        configs = json.loads((REPO / "data" / "architectures.json").read_text())
        module = load_module(mpv.variant_path(0.5))
        for key in sorted(configs)[:5]:
            cfg = configs[key]
            expected = ctxnsc.score_with_ratios(cfg, 0.5,
                                                ctxnsc.position_ratios(cfg["n_layer"]))
            self.assertEqual(module.score(cfg), expected)
            self.assertEqual(module.score(cfg), mpv.independent_m3(cfg, 0.5))
            self.assertEqual(module.ablation(cfg), nsc.original_nsc(cfg))

    def test_independent_formula_is_order_faithful_off_grid(self):
        # beta = 0.3 is not a power of two: the ratio must be formed first.
        configs = json.loads((REPO / "data" / "architectures.json").read_text())
        for key in sorted(configs)[:5]:
            cfg = configs[key]
            self.assertEqual(
                mpv.independent_m3(cfg, 0.3),
                ctxnsc.score_with_ratios(cfg, 0.3,
                                         ctxnsc.position_ratios(cfg["n_layer"])))

    def test_beta_zero_is_original_nsc(self):
        configs = json.loads((REPO / "data" / "architectures.json").read_text())
        module = load_module(mpv.variant_path(0.0))
        for key in sorted(configs):
            self.assertEqual(module.score(configs[key]),
                             nsc.original_nsc(configs[key]))


if __name__ == "__main__":
    unittest.main()
