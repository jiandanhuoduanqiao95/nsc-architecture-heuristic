"""Tests for tools/make_report_pack.py: the pack is current, only B placeholders
remain, and every JSON-keyed citation re-resolves to its raw value."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import make_report_pack as pack  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DOTTED = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+|\[alpha=[0-9.]+\])*"
                    r"(?:\.[A-Za-z0-9_]+)*$")


def resolve(payload, key):
    """Walk 'a.b.c' and 'per_alpha[alpha=2].x' paths independently of the tool."""
    node = payload
    for part in re.findall(r"[A-Za-z0-9_]+|\[alpha=[0-9.]+\]", key):
        if part.startswith("[alpha="):
            alpha = float(part[len("[alpha="):-1])
            node = next(item for item in node if item["alpha"] == alpha)
        else:
            node = node[part]
    return node


class ReportPackTests(unittest.TestCase):
    def setUp(self):
        self.content = pack.OUT.read_text(encoding="utf-8")

    def test_committed_pack_equals_a_fresh_render(self):
        self.assertEqual(self.content, pack.render())

    def test_only_the_three_b_placeholders_remain(self):
        self.assertEqual(pack.rule_problems(self.content), [])
        self.assertEqual(sorted(re.findall(r"\[\[[^\]]*\]\]", self.content)),
                         sorted(pack.B_PLACEHOLDERS))

    def test_json_citations_reresolve_to_their_raw_values(self):
        table = self.content.partition("## Sources")[2]
        rows = re.findall(r"^\| (S\d+) \| (.*?) \| `([^`]+)` \| (.*?) \| `(.*)` \|$",
                          table, flags=re.M)
        self.assertGreaterEqual(len(rows), 40)
        checked = 0
        for sid, _value, source, key, raw in rows:
            if not source.endswith(".json") or source == "results/checks.json":
                continue
            if not DOTTED.match(key):
                continue
            payload = json.loads((REPO / source).read_text(encoding="utf-8"))
            self.assertEqual(repr(resolve(payload, key)), raw, f"{sid} {source} {key}")
            checked += 1
        self.assertGreaterEqual(checked, 25)

    def test_csv_row_and_check_citations_reresolve(self):
        table = self.content.partition("## Sources")[2]
        rows = re.findall(r"^\| (S\d+) \| (.*?) \| `([^`]+)` \| (.*?) \| `(.*)` \|$",
                          table, flags=re.M)
        import csv
        with (REPO / "results" / "reorder_pairs.csv").open(encoding="utf-8") as fh:
            toy = next(r for r in csv.DictReader(fh) if r["pair_id"] == "pair_00")
        checks = json.loads((REPO / "results" / "checks.json").read_text())
        checked = 0
        for sid, _value, source, key, raw in rows:
            if source == "results/reorder_pairs.csv" and key.startswith("pair_00 "):
                cell = toy[key.split(" ", 1)[1]]
                candidates = {repr(cell)}
                for cast in (int, float):
                    try:
                        candidates.add(repr(cast(cell)))
                    except ValueError:
                        pass
                self.assertIn(raw, candidates, f"{sid} {key}")
                checked += 1
            elif source == "results/checks.json" and " n_cases - n_failed" in key:
                cid = key.split(" ", 1)[0]
                c = next(item for item in checks["checks"] if item["id"] == cid)
                self.assertEqual(raw, repr((c["n_cases"] - c["n_failed"], c["n_cases"])))
                checked += 1
        self.assertGreaterEqual(checked, 15)

    def test_every_marker_in_the_body_is_listed(self):
        body, _, table = self.content.partition("## Sources")
        used = set(re.findall(r"\[([SP]\d+)\]", body))
        listed = set(re.findall(r"^\| ([SP]\d+) \|", table, flags=re.M))
        self.assertEqual(used, listed)


if __name__ == "__main__":
    unittest.main()
