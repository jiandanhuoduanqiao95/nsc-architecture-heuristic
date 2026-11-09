"""Tests for tools/make_report_pack.py: the pack is current, only B placeholders
remain, and EVERY citation re-resolves to its raw value independently of the
generator (JSON key paths, computed data_audit/weighting_diagnostic values,
CSV cells, check counts and live code constants)."""
import csv
import inspect
import json
import re
import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evaluate  # noqa: E402
from checks import checks as checks_mod  # noqa: E402
from tools import make_report_pack as pack  # noqa: E402
from tools import select_alpha  # noqa: E402
from tools.selection_ext import select_trials_ext  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DOTTED = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+|\[alpha=[0-9.]+\])*"
                    r"(?:\.[A-Za-z0-9_]+)*$")
SOURCES = re.compile(r"^\| ([SP]\d+) \| (.*?) \| `([^`]+)` \| (.*?) \| `(.*)` \|$",
                     flags=re.M)


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


def load(rel):
    with (REPO / rel).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class CitationResolution:
    """Independent re-resolution of every Sources-row citation."""

    def __init__(self):
        self.checks = json.loads((REPO / "results" / "checks.json").read_text())
        self.audit = load("results/data_audit.csv")
        self.diag = load("results/weighting_diagnostic.csv")
        self.toy = next(r for r in load("results/reorder_pairs.csv")
                        if r["pair_id"] == "pair_00")
        self.norm = json.loads((REPO / "results" / "normalization_summary.json")
                               .read_text())

    def check_by_id(self, cid):
        return next(c for c in self.checks["checks"] if c["id"] == cid)

    def resolves(self, source, key, raw):
        """True iff the citation (source, key) -> raw re-derives independently."""
        # JSON key paths (any *_summary.json; checks.json handled separately)
        if source.endswith(".json") and source != "results/checks.json" \
                and DOTTED.match(key):
            payload = json.loads((REPO / source).read_text(encoding="utf-8"))
            return repr(resolve(payload, key)) == raw
        # checks.json: per-check case counts and the CH10 detail figure
        if source == "results/checks.json" and " n_cases - n_failed" in key:
            c = self.check_by_id(key.split(" ", 1)[0])
            return raw == repr((c["n_cases"] - c["n_failed"], c["n_cases"]))
        if source == "results/checks.json" and key.startswith("CH10 detail"):
            c = self.check_by_id("CH10")
            err = float(re.search(r"max rel err ([0-9.e+-]+)", c["detail"]).group(1))
            return raw == repr(err)
        # reorder_pairs.csv: raw cell or int/float cast; FFN lists bracket-joined
        if source == "results/reorder_pairs.csv" and key.startswith("pair_00 "):
            cell = self.toy[key.split(" ", 1)[1]]
            candidates = {repr(cell)}
            for cast in (int, float):
                try:
                    candidates.add(repr(cast(cell)))
                except ValueError:
                    pass
            if key in ("pair_00 ffn_before", "pair_00 ffn_after"):
                candidates.add(repr("[" + cell.replace("|", ", ") + "]"))
            return raw in candidates
        # data_audit.csv: row fields and independently recomputed aggregates
        if source == "results/data_audit.csv":
            dev = [r for r in self.audit if r["split"] == "development"]
            if key == "dev pairs with same d_model and min/max(total) >= 0.90":
                pairs = sum(1 for i in range(len(dev)) for j in range(i)
                            if dev[i]["d_model"] == dev[j]["d_model"]
                            and min(float(dev[i]["reported_total"]),
                                    float(dev[j]["reported_total"]))
                            / max(float(dev[i]["reported_total"]),
                                  float(dev[j]["reported_total"])) >= 0.90)
                return raw == repr(pairs)
            cap_match = re.match(r"^dev rows with reported_total <= (\d+)$", key)
            if cap_match:
                cap = int(cap_match.group(1))
                return raw == repr(sum(1 for r in dev
                                       if float(r["reported_total"]) <= cap))
            if key == "rows with d_embed != d_model":
                return raw == repr(sum(1 for r in self.audit
                                       if r["d_embed"] != r["d_model"]))
            if key == "rows":
                return raw == repr(len(self.audit))
            if key == "max total_over_projection":
                return raw == repr(max(float(r["total_over_projection"])
                                       for r in self.audit))
            if key == "dev rows with reported_total <= 10M and d_model == 512":
                return raw == repr(sum(1 for r in dev
                                       if float(r["reported_total"]) <= 10000000
                                       and r["d_model"] == "512"))
        # weighting_diagnostic.csv: depth-group medians and argmax depth
        if source == "results/weighting_diagnostic.csv":
            by_depth = {}
            for r in self.diag:
                by_depth.setdefault(int(r["n_layer"]), []).append(
                    float(r["m2_alpha2"]) / float(r["m3_beta2"]))
            if key == "n_layer group with the largest median m2_alpha2/m3_beta2":
                return raw == repr(max(by_depth,
                                       key=lambda d: statistics.median(by_depth[d])))
            match = re.match(r"^median of m2_alpha2/m3_beta2 over n_layer "
                             r"(==|>=) (\d+)$", key)
            if match:
                op, depth = match.group(1), int(match.group(2))
                values = by_depth[depth] if op == "==" else \
                    [v for d, vs in by_depth.items() if d >= depth for v in vs]
                return raw == repr(statistics.median(values))
        # normalization_summary.json: count of the picked configurations
        if source == "results/normalization_summary.json" \
                and key == "picked_configs (count)":
            return raw == repr(len(self.norm["picked_configs"]))
        # live code constants
        if source == "evaluate.py":
            if key == "BUDGETS":
                return raw == repr(evaluate.BUDGETS)
            if key == "K_VALUES":
                return raw == repr(evaluate.K_VALUES)
            if key == "REPEATS":
                return raw == repr(evaluate.REPEATS)
        if source == "checks/checks.py" and key == "ALPHA_LIMIT_PROBE":
            return raw == repr(checks_mod.ALPHA_LIMIT_PROBE)
        if source == "tools/select_alpha.py" and key == "DEFAULT_GRID":
            return raw == repr(select_alpha.DEFAULT_GRID)
        if source == "tools/selection_ext.py" and key.startswith("select_trials_ext"):
            default = inspect.signature(select_trials_ext).parameters["repeats"].default
            return raw == repr(default)
        return False


class ReportPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = pack.OUT.read_text(encoding="utf-8")
        cls.rows = SOURCES.findall(cls.content.partition("## Sources")[2])
        cls.helper = CitationResolution()

    def test_committed_pack_equals_a_fresh_render(self):
        self.assertEqual(self.content, pack.render())

    def test_only_the_three_b_placeholders_remain(self):
        self.assertEqual(pack.rule_problems(self.content), [])
        self.assertEqual(sorted(re.findall(r"\[\[[^\]]*\]\]", self.content)),
                         sorted(pack.B_PLACEHOLDERS))

    def test_every_marker_in_the_body_is_listed(self):
        body, _, table = self.content.partition("## Sources")
        used = set(re.findall(r"\[([SP]\d+)\]", body))
        listed = set(re.findall(r"^\| ([SP]\d+) \|", table, flags=re.M))
        self.assertEqual(used, listed)

    def test_at_least_60_citations_and_all_reresolve(self):
        """P3: >= 60 of the printed values carry automated evidence; in fact
        every Sources row must re-resolve."""
        self.assertGreaterEqual(len(self.rows), 60)
        uncovered = [(sid, source, key)
                     for sid, _v, source, key, raw in self.rows
                     if not self.helper.resolves(source, key, raw)]
        self.assertEqual(uncovered, [], f"unresolved citations: {uncovered}")

    def test_data_audit_derived_values_reresolve(self):
        """S47-S55: the nine data_audit.csv-derived values (pairs, pools,
        embedding mismatch, row count, ratio max, width-512 absence)."""
        keys = [key for _sid, _v, source, key, _raw in self.rows
                if source == "results/data_audit.csv"]
        self.assertEqual(len(keys), 9)
        for key in keys:
            self.assertTrue(self.helper.resolves("results/data_audit.csv", key,
                                                 self._raw(key)), key)

    def test_weighting_diagnostic_derived_values_reresolve(self):
        """S38-S40: the depth-argmax and the two M2/M3 median ratios."""
        keys = [key for _sid, _v, source, key, _raw in self.rows
                if source == "results/weighting_diagnostic.csv"]
        self.assertEqual(len(keys), 3)
        for key in keys:
            self.assertTrue(self.helper.resolves("results/weighting_diagnostic.csv",
                                                 key, self._raw(key)), key)

    def _raw(self, key):
        for _sid, _v, _source, k, raw in self.rows:
            if k == key:
                return raw
        raise AssertionError(key)


if __name__ == "__main__":
    unittest.main()
