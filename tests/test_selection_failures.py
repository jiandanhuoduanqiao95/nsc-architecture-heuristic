"""Tests for tools/selection_failures.py (failure-case extractor)."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import selection_failures as sf  # noqa: E402
from tools.selection_ext import representative_choice  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def fixture_payload():
    return json.loads(sf.FIXTURE_PATH.read_text(encoding="utf-8"))


class SelfTestTests(unittest.TestCase):
    def test_self_test_passes(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(sf.self_test(), 0)
        self.assertIn("SELECTION FAILURES OK", out.getvalue())

    def test_fixture_is_reproducible_from_builder(self):
        self.assertEqual(sf.build_fixture(), fixture_payload())


class ContractTests(unittest.TestCase):
    def test_explicit_scores_path_matches_builtin_method(self):
        payload = fixture_payload()
        world = sf.fixture_world(payload)
        rows_builtin, _ = sf.analyse(payload, world, "development")
        renamed = copy.deepcopy(payload)
        pool_all = world.split_keys
        renamed["scores"] = {"custom_nsc": {
            cid: sf.method_scores("original_nsc", world, pool_all)[cid]
            for cid in pool_all}}
        for entry in renamed["entries"]:
            if entry["method"] == "original_nsc":
                entry["method"] = "custom_nsc"
        rows_explicit, _ = sf.analyse(renamed, world, "development")
        strip = lambda rows: [{k: v for k, v in r.items() if k != "method"}
                              for r in rows]
        self.assertEqual(strip(rows_builtin), strip(rows_explicit))

    def test_unresolvable_method_leaves_rank_blank(self):
        payload = fixture_payload()
        for entry in payload["entries"]:
            if entry["method"] == "original_nsc":
                entry["method"] = "unknown_method"
        rows, _ = sf.analyse(payload, sf.fixture_world(payload), "development")
        unknown = [r for r in rows if r["method"] == "unknown_method"]
        self.assertTrue(unknown)
        for row in unknown:
            self.assertEqual(row["score_rank_of_best"], "")
            self.assertNotIn("tie_at_boundary", row["reason_tags"])

    def test_random_entries_are_skipped(self):
        payload = fixture_payload()
        extra = copy.deepcopy(payload["entries"][0])
        extra["method"] = "random"
        payload["entries"].append(extra)
        _, summary = sf.analyse(payload, sf.fixture_world(payload), "development")
        self.assertEqual(summary["skipped_random"], 1)
        self.assertEqual(summary["entries"], 8)

    def test_fixture_world_requires_flag(self):
        with self.assertRaises(sf.ContractError):
            sf.run(sf.FIXTURE_PATH, "development", None, None, use_fixture=False)

    def test_final_refused_before_any_read(self):
        sf.OPENED.clear()
        with self.assertRaises(sf.UsageError):
            sf.run(sf.FIXTURE_PATH, "final", None, None)
        with self.assertRaises(sf.UsageError):
            sf.load_archive_world("final", allow_final=False)
        self.assertEqual(sf.OPENED, [])


class ArchivePathTests(unittest.TestCase):
    """Real development entry: matches the official harness, reads dev labels only."""

    def test_original_nsc_10m_k1_matches_harness_and_reads_dev_only(self):
        world = sf.load_archive_world("development", allow_final=False)
        cap, k, seed = 10_000_000, 1, 202627 + 10_000_000 + 1
        pool = [cid for cid in world.split_keys if world.total[cid] <= cap]
        scores = sf.method_scores("original_nsc", world, pool)
        chosen = representative_choice(pool, scores, k, seed)
        chosen_ppl = [world.ppl[c] for c in chosen]
        oracle = min(world.ppl[p] for p in pool)
        payload = {"split": "development", "trials": 1000, "entries": [{
            "method": "original_nsc", "cap": cap, "k": k, "pool": pool,
            "chosen": chosen, "chosen_ppl": chosen_ppl,
            "best_ppl": min(chosen_ppl), "oracle_ppl": oracle,
            "regret": min(chosen_ppl) - oracle}]}
        expected = json.loads((REPO / "expected_development.json").read_text())
        harness = expected["selection"][0]
        self.assertEqual((harness["parameter_cap"], harness["k"]), (cap, k))
        self.assertEqual(len(pool), harness["eligible"])  # 24
        self.assertEqual(oracle, harness["oracle_ppl"])
        self.assertEqual(min(chosen_ppl),
                         harness["methods"]["original_nsc"]["mean_best_ppl"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selection.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sf.OPENED.clear()
            rows, summary = sf.run(path, "development", Path(tmp) / "f.csv",
                                   Path(tmp) / "f.md")
        self.assertIn("development_labels.json", sf.OPENED)
        self.assertNotIn("final_labels.json", sf.OPENED)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(float(rows[0]["gap"]),
                         harness["methods"]["original_nsc"]["mean_regret"])


if __name__ == "__main__":
    unittest.main()
