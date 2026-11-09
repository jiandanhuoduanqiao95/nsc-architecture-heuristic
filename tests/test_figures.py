"""Tests for tools/make_figures.py: SVGs are well-formed, current and equal to the CSVs."""
import csv
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import make_figures  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
NS = "{http://www.w3.org/2000/svg}"


def svg_root(name):
    return ET.parse(REPO / "docs" / "figures" / name).getroot()


def all_text(root):
    return " ".join("".join(node.itertext()) for node in root.iter(NS + "text"))


class FigureTests(unittest.TestCase):
    def test_committed_svgs_equal_a_fresh_render(self):
        for name, render in make_figures.FIGURES.items():
            path = REPO / "docs" / "figures" / name
            self.assertEqual(path.read_text(encoding="utf-8"), render(), name)

    def test_reorder_curve_points_equal_csv_toy_row(self):
        rows = list(csv.DictReader((REPO / "results" / "reorder_pairs.csv").open()))
        toy = next(r for r in rows if r["pair_id"] == "pair_00")
        root = svg_root("reorder_alpha_curve.svg")
        points = [c for c in root.iter(NS + "circle") if c.get("data-series")]
        self.assertEqual(len(points), 10)
        self.assertEqual(len(list(root.iter(NS + "polyline"))), 2)
        keys = dict(make_figures.ALPHAS)
        for point in points:
            column = ("s_" if point.get("data-series") == "before" else "s_after_") \
                + keys[point.get("data-alpha")]
            self.assertEqual(point.get("data-s"), toy[column])
        # higher S is drawn higher (smaller y); the alpha=0 points coincide
        by_series = {}
        for point in points:
            by_series.setdefault(point.get("data-series"), []).append(point)
        first = [p for p in points if p.get("data-alpha") == "0"]
        self.assertEqual(first[0].get("cy"), first[1].get("cy"))
        text = all_text(root)
        for label in ("discount strength α", "S(α)", "large FFN late",
                      "large FFN early", "both orders tie"):
            self.assertIn(label, text)

    def test_scatter_points_equal_weighting_csv(self):
        rows = {r["config_id"]: r for r in csv.DictReader(
            (REPO / "results" / "weighting_diagnostic.csv").open())}
        root = svg_root("m2_m3_scores.svg")
        points = [c for c in root.iter(NS + "circle") if c.get("data-config")]
        self.assertEqual(len(points), 100)
        self.assertEqual({p.get("data-config") for p in points}, set(rows))
        for point in points:
            row = rows[point.get("data-config")]
            self.assertEqual(point.get("data-x"), row["m3_beta2"])
            self.assertEqual(point.get("data-y"), row["m2_alpha2"])
            self.assertEqual(point.get("data-n-layer"), row["n_layer"])
        summary = json.loads((REPO / "results" / "weighting_summary.json").read_text())
        r_value = next(p["pearson_M2_M3_dev"] for p in summary["per_alpha"]
                       if p["alpha"] == 2.0)
        text = all_text(root)
        self.assertIn(f"Pearson r(M2, M3) = {r_value:.5f}", text)
        for label in ("M3 score", "M2 score", "y = x", "not a tuned value"):
            self.assertIn(label, text)


if __name__ == "__main__":
    unittest.main()
