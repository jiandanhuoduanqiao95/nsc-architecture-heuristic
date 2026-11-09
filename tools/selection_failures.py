#!/usr/bin/env python3
"""Selection failure-case extractor (TA 1 "report failure cases as planned",
TA 2 "analyze specific selection failures").

Reads role B's selection export ``results/selection_1000.json`` (contract:
docs/interface.md, section "Selection export contract") and, for every
(method, cap, k) entry whose representative choice missed the pool optimum,
reports WHO was chosen, WHO was best, BY HOW MUCH, and WHY (reason tags).

    python3 tools/selection_failures.py --selection results/selection_1000.json \
        --split development --out-csv results/selection_failures.csv \
        --out-md docs/selection_failures.md
    python3 tools/selection_failures.py --self-test

Column meanings (CSV, exactly these 13 columns):
    chosen_ids / chosen_ppl   what the method picked ("|"-joined)
    best_id / best_ppl        the pool optimum = lowest PPL in the feasible pool
    gap                       best PPL among chosen - best_ppl
                              (= the entry's best_ppl - oracle_ppl = regret)
    reason_tags               "|"-joined subset of TAG_ORDER (see TAG_HELP)
    score_rank_of_best        competition rank of the optimum under the
                              method's canonical (12 significant digit) scores
                              (1 + number of pool designs scored strictly
                              higher); blank when the method's scores cannot
                              be resolved
    size_ratio_chosen_vs_best reported total of the best chosen design / total
                              of the optimum
    depth_delta / width_delta n_layer / d_model of best chosen minus optimum

Only failure entries (gap > 0) become CSV rows; ``random`` entries are
skipped (no single choice). The export is validated against the archive
first (pool = cap-feasible set, chosen PPLs = labels, oracle = pool
minimum, chosen = a valid top-k under the method's canonical scores);
any mismatch is a contract error (exit 1).

Label access: only the selected split's label file is read (development ->
data/development_labels.json). ``--split final`` additionally requires
``--allow-final`` (role B, after the freeze tag); without it the tool exits
2 before reading any file. ``--fixture-world`` analyses the synthetic world
embedded in tests/fixtures/selection_example.json (self-test / examples).
Maintenance: ``--write-fixture PATH`` regenerates that fixture.
"""
import argparse
import copy
import csv
import io
import json
import math
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import evaluate  # noqa: E402  (starter module: canonical 12-significant-digit scores)
import nsc  # noqa: E402
from tools.selection_ext import representative_choice, select_trials_ext  # noqa: E402

CSV_COLUMNS = ["method", "cap", "k", "chosen_ids", "chosen_ppl", "best_id",
               "best_ppl", "gap", "reason_tags", "score_rank_of_best",
               "size_ratio_chosen_vs_best", "depth_delta", "width_delta"]
TAG_ORDER = ["score_missed_oracle", "near_cap", "depth_mismatch",
             "width_mismatch", "tie_at_boundary", "pool_artifact"]
TAG_HELP = {
    "score_missed_oracle": "the pool optimum is not among the chosen designs and gap > 0",
    "near_cap": "a chosen design's reported total exceeds 0.9 x cap (budget-edge choice)",
    "depth_mismatch": "best chosen design and optimum differ in n_layer",
    "width_mismatch": "best chosen design and optimum differ in d_model",
    "tie_at_boundary": ("canonical scores tie across ranks k and k+1, so the "
                        "harness shuffle decided membership"),
    "pool_artifact": ("best chosen design and optimum differ >= 2x in reported "
                      "total / projection parameters: the cap counts adaptive "
                      "embeddings that projection-only scores never see "
                      "(docs/data_audit.md, consequence 2)"),
}
NEAR_CAP_FRACTION = 0.9
POOL_ARTIFACT_FACTOR = 2.0
REQUIRED_TOP = ("split", "trials", "entries")
REQUIRED_ENTRY = ("method", "cap", "k", "pool", "chosen", "chosen_ppl",
                  "best_ppl", "oracle_ppl", "regret")
SKIPPED_METHODS = ("random",)
FIXTURE_PATH = REPO / "tests" / "fixtures" / "selection_example.json"
EXAMPLE_CSV = REPO / "docs" / "examples" / "selection_failures_example.csv"
EXAMPLE_MD = REPO / "docs" / "examples" / "selection_failures_example.md"
LABEL_FILES = {"development": ("development_labels.json", "valid_ppl"),
               "final": ("final_labels.json", "test_ppl")}

OPENED = []  # every data file this process read (audited by the tests)


class ContractError(ValueError):
    """The selection export violates the documented contract."""


class UsageError(ValueError):
    """Refused invocation (e.g. --split final without --allow-final)."""


def _read_data(name):
    OPENED.append(name)
    return json.loads((REPO / "data" / name).read_text(encoding="utf-8"))


class World:
    """Configs, PPLs and reported totals of one split (archive or fixture)."""

    def __init__(self, configs, ppl, total, split_keys, source):
        self.configs = configs
        self.ppl = ppl
        self.total = total
        self.split_keys = split_keys
        self.source = source
        self._projection = {}

    def projection(self, cid):
        if cid not in self._projection:
            self._projection[cid] = nsc.resource_estimate(
                self.configs[cid])["projection_parameters"]
        return self._projection[cid]


def load_archive_world(split, allow_final):
    """Archive world for ``split``; final is refused BEFORE any file read."""
    if split not in LABEL_FILES:
        raise UsageError(f"unknown split {split!r}")
    if split == "final" and not allow_final:
        raise UsageError("--split final requires --allow-final (role B, only "
                         "after the group's freeze tag); refusing before "
                         "reading any file")
    label_file, label_key = LABEL_FILES[split]
    configs = _read_data("architectures.json")
    resources = _read_data("resources.json")
    keys = _read_data("splits.json")[split]
    labels = _read_data(label_file)
    return World(configs={k: configs[k] for k in keys},
                 ppl={k: labels[k][label_key] for k in keys},
                 total={k: resources[k]["total"] for k in keys},
                 split_keys=list(keys), source=f"archive:{split}")


def fixture_world(payload):
    data = payload.get("fixture_world")
    if not isinstance(data, dict):
        raise ContractError("--fixture-world given but the input has no fixture_world")
    keys = list(data["split_keys"])
    return World(configs=data["configs"], ppl=data["ppl"], total=data["total"],
                 split_keys=keys, source="fixture")


def method_scores(method, world, pool, explicit=None):
    """Canonical scores {config_id: float} for ``pool``, or None if unresolvable.

    Resolution order: explicit ``scores[method]`` from the export, then the
    canonical method names (original_nsc, ablation, position_example,
    reported_parameters, reference_flops, m2_alpha_<a>, m3_beta_<b>).
    """
    raw = None
    if explicit and method in explicit:
        table = explicit[method]
        missing = [p for p in pool if p not in table]
        if missing:
            raise ContractError(f"scores[{method!r}] lacks pool ids {missing[:3]}")
        raw = {p: float(table[p]) for p in pool}
    elif method in ("original_nsc", "ablation"):
        raw = {p: nsc.original_nsc(world.configs[p]) for p in pool}
    elif method == "position_example":
        raw = {p: nsc.position_example(world.configs[p]) for p in pool}
    elif method == "reported_parameters":
        raw = {p: world.total[p] for p in pool}
    elif method == "reference_flops":
        raw = {p: nsc.resource_estimate(world.configs[p])["reference_flops_per_token"]
               for p in pool}
    else:
        m2 = re.match(r"^m2_alpha_([0-9]+(?:\.[0-9]+)?)$", method)
        m3 = re.match(r"^m3_beta_([0-9]+(?:\.[0-9]+)?)$", method)
        if m2:
            alpha = float(m2.group(1))
            raw = {p: ctxnsc.score_config(world.configs[p], alpha) for p in pool}
        elif m3:
            beta = float(m3.group(1))
            raw = {p: ctxnsc.score_with_ratios(
                world.configs[p], beta,
                ctxnsc.position_ratios(world.configs[p]["n_layer"])) for p in pool}
    if raw is None:
        return None
    return {p: evaluate.canonical(v) for p, v in raw.items()}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int_value(v, what):
    if isinstance(v, bool) or not _is_number(v) or v != int(v) or v <= 0:
        raise ContractError(f"{what} must be a positive integer, got {v!r}")
    return int(v)


def validate_top(payload, split):
    if not isinstance(payload, dict):
        raise ContractError("selection export must be a JSON object")
    missing = [k for k in REQUIRED_TOP if k not in payload]
    if missing:
        raise ContractError(f"missing top-level fields: {missing}")
    if payload["split"] != split:
        raise ContractError(f"export split {payload['split']!r} != --split {split!r}")
    if payload["trials"] != 1000 or isinstance(payload["trials"], bool):
        raise ContractError(f"trials must be 1000 (TA 2 main protocol), got "
                            f"{payload['trials']!r}")
    if not isinstance(payload["entries"], list) or not payload["entries"]:
        raise ContractError("entries must be a non-empty list")


def analyse(payload, world, split):
    """Validate the export and return (failure_rows, summary)."""
    validate_top(payload, split)
    explicit = payload.get("scores")
    rows, notes = [], []
    summary = {"entries": 0, "skipped_random": 0, "failures": 0,
               "successes": 0, "per_method": {}}
    for index, entry in enumerate(payload["entries"]):
        where = f"entries[{index}]"
        if not isinstance(entry, dict):
            raise ContractError(f"{where} is not an object")
        missing = [k for k in REQUIRED_ENTRY if k not in entry]
        if missing:
            raise ContractError(f"{where}: missing fields {missing}")
        method = entry["method"]
        if method in SKIPPED_METHODS:
            summary["skipped_random"] += 1
            continue
        cap = _int_value(entry["cap"], f"{where}.cap")
        k = _int_value(entry["k"], f"{where}.k")
        where = f"{where} ({method}, cap={cap}, k={k})"
        pool, chosen = entry["pool"], entry["chosen"]
        if not isinstance(pool, list) or not isinstance(chosen, list):
            raise ContractError(f"{where}: pool/chosen must be lists of config ids")
        feasible = [cid for cid in world.split_keys if world.total[cid] <= cap]
        if set(pool) != set(feasible) or len(pool) != len(feasible):
            raise ContractError(
                f"{where}: pool differs from the cap-feasible set (missing "
                f"{sorted(set(feasible) - set(pool))[:3]}, extra "
                f"{sorted(set(pool) - set(feasible))[:3]}) — every method must "
                f"use the same pool (TA 2)")
        if len(chosen) != k or len(set(chosen)) != k or not set(chosen) <= set(pool):
            raise ContractError(f"{where}: chosen must be k distinct pool ids")
        chosen_ppl = entry["chosen_ppl"]
        if (not isinstance(chosen_ppl, list) or len(chosen_ppl) != k
                or not all(_is_number(v) for v in chosen_ppl)):
            raise ContractError(f"{where}: chosen_ppl must be k numbers")
        for cid, value in zip(chosen, chosen_ppl):
            if value != world.ppl[cid]:
                raise ContractError(f"{where}: chosen_ppl for {cid} is {value!r}, "
                                    f"label is {world.ppl[cid]!r}")
        best_chosen_ppl = min(chosen_ppl)
        oracle = min(world.ppl[p] for p in pool)
        if entry["best_ppl"] != best_chosen_ppl:
            raise ContractError(f"{where}: best_ppl {entry['best_ppl']!r} != "
                                f"min(chosen_ppl) {best_chosen_ppl!r}")
        if entry["oracle_ppl"] != oracle:
            raise ContractError(f"{where}: oracle_ppl {entry['oracle_ppl']!r} != "
                                f"pool minimum {oracle!r}")
        if not _is_number(entry["regret"]) or abs(
                entry["regret"] - (best_chosen_ppl - oracle)) > 1e-9:
            raise ContractError(f"{where}: regret {entry['regret']!r} != "
                                f"best_ppl - oracle_ppl")
        scores = method_scores(method, world, pool, explicit)
        boundary_tie = False
        if scores is not None:
            ordered = sorted((scores[p] for p in pool), reverse=True)
            threshold = ordered[k - 1]
            above = {p for p in pool if scores[p] > threshold}
            if not above <= set(chosen) or any(scores[c] < threshold for c in chosen):
                raise ContractError(f"{where}: chosen is not a top-{k} set under "
                                    f"the method's canonical scores")
            boundary_tie = len(pool) > k and ordered[k - 1] == ordered[k]
        stats = summary["per_method"].setdefault(
            method, {"entries": 0, "failures": 0, "gaps": []})
        stats["entries"] += 1
        summary["entries"] += 1
        gap = best_chosen_ppl - oracle
        if "mean_regret" in entry and _is_number(entry["mean_regret"]) and \
                abs(entry["mean_regret"] - entry["regret"]) > 1e-12:
            notes.append(f"{method} cap={cap} k={k}: 1,000-trial mean regret "
                         f"{entry['mean_regret']:.6f} differs from the "
                         f"representative {entry['regret']:.6f} — score ties "
                         f"made the choice vary across trials")
        if not gap > 0:
            summary["successes"] += 1
            continue
        summary["failures"] += 1
        stats["failures"] += 1
        stats["gaps"].append(gap)
        candidates = [p for p in pool if world.ppl[p] == oracle]
        if scores is not None:
            candidates.sort(key=lambda p: (-scores[p], p))
        else:
            candidates.sort()
        best_id = candidates[0]
        best_chosen = chosen[chosen_ppl.index(best_chosen_ppl)]
        cfg_c, cfg_o = world.configs[best_chosen], world.configs[best_id]
        tags = []
        if best_id not in chosen:
            tags.append("score_missed_oracle")
        if any(world.total[c] > NEAR_CAP_FRACTION * cap for c in chosen):
            tags.append("near_cap")
        if cfg_c["n_layer"] != cfg_o["n_layer"]:
            tags.append("depth_mismatch")
        if cfg_c["d_model"] != cfg_o["d_model"]:
            tags.append("width_mismatch")
        if boundary_tie:
            tags.append("tie_at_boundary")
        share_c = world.total[best_chosen] / world.projection(best_chosen)
        share_o = world.total[best_id] / world.projection(best_id)
        if max(share_c / share_o, share_o / share_c) >= POOL_ARTIFACT_FACTOR:
            tags.append("pool_artifact")
        rank = ("" if scores is None else
                1 + sum(1 for p in pool if scores[p] > scores[best_id]))
        rows.append({
            "method": method, "cap": cap, "k": k,
            "chosen_ids": "|".join(chosen),
            "chosen_ppl": "|".join(repr(v) for v in chosen_ppl),
            "best_id": best_id, "best_ppl": repr(oracle), "gap": repr(gap),
            "reason_tags": "|".join(tags), "score_rank_of_best": rank,
            "size_ratio_chosen_vs_best": repr(world.total[best_chosen]
                                              / world.total[best_id]),
            "depth_delta": cfg_c["n_layer"] - cfg_o["n_layer"],
            "width_delta": cfg_c["d_model"] - cfg_o["d_model"],
            "_best_chosen": best_chosen, "_best_chosen_ppl": best_chosen_ppl,
            "_pool_size": len(pool), "_scores_known": scores is not None,
        })
    summary["notes"] = notes
    rows.sort(key=lambda r: (-float(r["gap"]), r["method"], r["cap"], r["k"]))
    return rows, summary


def render_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _why(row):
    parts = []
    if row["score_rank_of_best"] != "":
        parts.append(f"the score ranked the optimum #{row['score_rank_of_best']} "
                     f"of {row['_pool_size']}")
    tags = row["reason_tags"].split("|") if row["reason_tags"] else []
    if "near_cap" in tags:
        parts.append("chose at the budget edge (>0.9 x cap)")
    if "depth_mismatch" in tags:
        parts.append(f"depth delta {row['depth_delta']:+d}")
    if "width_mismatch" in tags:
        parts.append(f"width delta {row['width_delta']:+d}")
    if "tie_at_boundary" in tags:
        parts.append("score tie at the k-th rank (shuffle decided)")
    if "pool_artifact" in tags:
        parts.append("embedding share differs >= 2x (cap vs score scope)")
    parts.append(f"size ratio {float(row['size_ratio_chosen_vs_best']):.3f}")
    return "; ".join(parts)


def render_md(rows, summary, source_label, split, is_fixture):
    lines = ["# Selection failure cases (generated by "
             "`tools/selection_failures.py` — do not hand-edit)", ""]
    if is_fixture:
        lines += ["> **FIXTURE WORLD** — synthetic configurations from "
                  "`tests/fixtures/selection_example.json`; format example "
                  "only, NOT archive results.", ""]
    lines += [f"Source: `{source_label}` · split: {split} · trials: 1000 · "
              f"entries analysed: {summary['entries']} (random skipped: "
              f"{summary['skipped_random']}) · failures: {summary['failures']} · "
              f"successes: {summary['successes']}", "",
              "## How to read", "",
              "- **chosen** = the method's representative choice (trial 1 of the "
              "harness tie-handling: shuffle, then stable sort by score).",
              "- **optimum** = the lowest-PPL design in the same feasible pool "
              "(CSV `best_id` / `best_ppl`).",
              "- **gap** = best PPL among the chosen − optimum PPL (= regret).",
              "- **rank of optimum** = competition rank under the method's "
              "canonical (12 significant digit) scores.", "",
              "| tag | meaning |", "|---|---|"]
    lines += [f"| `{tag}` | {TAG_HELP[tag]} |" for tag in TAG_ORDER]
    lines += ["", "## Failure table (largest gap first)", "",
              "| method | cap | k | chosen (PPL) | best chosen | optimum (PPL) | "
              "gap | rank of optimum | tags |",
              "|---|---:|---:|---|---|---|---:|---:|---|"]
    for r in rows:
        chosen = ", ".join(f"{c} ({float(p):.3f})" for c, p in
                           zip(r["chosen_ids"].split("|"), r["chosen_ppl"].split("|")))
        lines.append(
            f"| {r['method']} | {r['cap']:,} | {r['k']} | {chosen} | "
            f"{r['_best_chosen']} | {r['best_id']} ({float(r['best_ppl']):.3f}) | "
            f"{float(r['gap']):.3f} | {r['score_rank_of_best']} | "
            f"{r['reason_tags'].replace('|', ', ')} |")
    if not rows:
        lines.append("| — | | | no failures | | | | | |")
    lines += ["", "## Per-method summary", "",
              "| method | entries | failures | mean gap over failures |",
              "|---|---:|---:|---:|"]
    for method in sorted(summary["per_method"]):
        s = summary["per_method"][method]
        mean_gap = (f"{sum(s['gaps']) / len(s['gaps']):.3f}" if s["gaps"] else "—")
        lines.append(f"| {method} | {s['entries']} | {s['failures']} | {mean_gap} |")
    lines += ["", "## Candidate cases for the report (TA: at least 3 concrete cases)", ""]
    for number, r in enumerate(rows[:5], start=1):
        lines.append(f"{number}. **{r['method']}, cap {r['cap']:,}, k={r['k']}** — "
                     f"chose {r['chosen_ids'].replace('|', ', ')}; optimum "
                     f"{r['best_id']}; gap {float(r['gap']):.3f} PPL; why: {_why(r)}.")
    if not rows:
        lines.append("_No failure entries._")
    if summary["notes"]:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in summary["notes"]]
    lines += ["", "Variance in the 1,000 trials reflects selection/tie-breaking "
              "randomness only — the archive has one outcome per architecture, "
              "so training-seed uncertainty cannot be estimated (TA 1/2).", ""]
    return "\n".join(lines)


def _source_label(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def run(selection, split, out_csv, out_md, allow_final=False, use_fixture=False):
    """Load, validate, analyse and write; returns (rows, summary)."""
    if split == "final" and not allow_final:  # refuse before ANY file read
        raise UsageError("--split final requires --allow-final (role B, only "
                         "after the group's freeze tag); refusing before "
                         "reading any file")
    payload = json.loads(Path(selection).read_text(encoding="utf-8"))
    if use_fixture:
        world = fixture_world(payload)
    else:
        if "fixture_world" in payload:
            raise ContractError("input carries a synthetic fixture_world; pass "
                                "--fixture-world to analyse it")
        world = load_archive_world(split, allow_final)
    rows, summary = analyse(payload, world, split)
    label = _source_label(selection)
    if out_csv:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        Path(out_csv).write_text(render_csv(rows), encoding="utf-8")
    if out_md:
        Path(out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(out_md).write_text(render_md(rows, summary, label, split, use_fixture),
                                encoding="utf-8")
    return rows, summary


# ---------------------------------------------------------------------------
# Fixture (6 synthetic configs, 2 methods x 2 caps x 2 k)
# ---------------------------------------------------------------------------

_W = 0.02
FIXTURE_CONFIGS = {
    "syn_a": {"d_model": 64, "n_layer": 2, "n_head": [2, 2], "d_inner": [128, 256],
              "weight_init_std": _W},
    "syn_b": {"d_model": 64, "n_layer": 3, "n_head": [2, 2, 2],
              "d_inner": [256, 256, 256], "weight_init_std": _W},
    "syn_c": {"d_model": 128, "n_layer": 2, "n_head": [4, 4], "d_inner": [256, 512],
              "weight_init_std": _W},
    "syn_d": {"d_model": 128, "n_layer": 4, "n_head": [4, 4, 4, 4],
              "d_inner": [512, 512, 512, 512], "weight_init_std": _W},
    "syn_e": {"d_model": 64, "n_layer": 4, "n_head": [4, 4, 4, 4],
              "d_inner": [128, 128, 128, 128], "weight_init_std": _W},
    "syn_f": {"d_model": 128, "n_layer": 3, "n_head": [4, 4, 4],
              "d_inner": [384, 384, 384], "weight_init_std": _W},
}
FIXTURE_PPL = {"syn_a": 46.0, "syn_b": 52.0, "syn_c": 48.0, "syn_d": 41.0,
               "syn_e": 45.0, "syn_f": 39.5}
FIXTURE_TOTAL = {"syn_a": 1200000.0, "syn_b": 1900000.0, "syn_c": 1900000.0,
                 "syn_d": 4800000.0, "syn_e": 600000.0, "syn_f": 3000000.0}
FIXTURE_CAPS = (2000000, 5000000)
FIXTURE_METHODS = ("original_nsc", "reported_parameters")


def build_fixture():
    keys = sorted(FIXTURE_CONFIGS)
    world = World(configs=FIXTURE_CONFIGS, ppl=FIXTURE_PPL, total=FIXTURE_TOTAL,
                  split_keys=keys, source="fixture")
    entries = []
    for method in FIXTURE_METHODS:
        for cap in FIXTURE_CAPS:
            pool = [cid for cid in keys if FIXTURE_TOTAL[cid] <= cap]
            scores = method_scores(method, world, pool)
            for k in (1, 3):
                seed = 202627 + cap + k
                chosen = representative_choice(pool, scores, k, seed)
                chosen_ppl = [FIXTURE_PPL[c] for c in chosen]
                agg = select_trials_ext(pool, scores, k, FIXTURE_PPL, seed,
                                        repeats=1000)
                oracle = min(FIXTURE_PPL[p] for p in pool)
                entries.append({
                    "method": method, "cap": cap, "k": k, "seed": seed,
                    "pool": pool, "chosen": chosen, "chosen_ppl": chosen_ppl,
                    "best_ppl": min(chosen_ppl), "oracle_ppl": oracle,
                    "regret": min(chosen_ppl) - oracle,
                    "mean_best_ppl": agg["mean_best_ppl"],
                    "mean_regret": agg["mean_regret"],
                    "sd_best_ppl": agg["sd_best_ppl"]})
    return {"split": "development", "trials": 1000,
            "note": ("synthetic fixture for tools/selection_failures.py "
                     "--self-test; NOT archive data"),
            "fixture_world": {"split_keys": keys, "configs": FIXTURE_CONFIGS,
                              "ppl": FIXTURE_PPL, "total": FIXTURE_TOTAL},
            "entries": entries}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _expect_error(kind, payload, world, split="development"):
    try:
        analyse(payload, world, split)
    except kind:
        return True
    return False


def self_test():
    """Fixture checks for rows, gap arithmetic, tags and contract errors."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    world = fixture_world(payload)
    rows, summary = analyse(payload, world, "development")
    assert summary["entries"] == 8 and summary["skipped_random"] == 0, summary
    assert summary["failures"] == 5 and summary["successes"] == 3, summary
    assert len(rows) == 5
    by_key = {(r["method"], r["cap"], r["k"]): r for r in rows}
    entry_by_key = {(e["method"], e["cap"], e["k"]): e for e in payload["entries"]}
    for key, row in by_key.items():
        entry = entry_by_key[key]
        gap = float(row["gap"])
        assert gap == entry["best_ppl"] - entry["oracle_ppl"] and gap > 0, key
        chosen_ppl = [float(v) for v in row["chosen_ppl"].split("|")]
        assert gap == min(chosen_ppl) - float(row["best_ppl"]), key
        tags = row["reason_tags"].split("|")
        assert tags and set(tags) <= set(TAG_ORDER), key
    nsc_small = by_key[("original_nsc", 2000000, 1)]
    assert nsc_small["best_id"] == "syn_e" and nsc_small["chosen_ids"] == "syn_c"
    assert nsc_small["score_rank_of_best"] == 3
    assert {"near_cap", "depth_mismatch", "width_mismatch"} <= set(
        nsc_small["reason_tags"].split("|"))
    assert "tie_at_boundary" in by_key[("reported_parameters", 2000000, 1)][
        "reason_tags"].split("|")
    rp_k3 = by_key[("reported_parameters", 2000000, 3)]
    assert "pool_artifact" in rp_k3["reason_tags"].split("|")
    assert rp_k3["score_rank_of_best"] == 4
    assert ("original_nsc", 2000000, 3) not in by_key  # success: optimum chosen
    print("ROWS OK (8 entries, 5 failures, gap = best_ppl - oracle_ppl, "
          "all tags present)")

    with tempfile.TemporaryDirectory() as tmp:
        out_csv, out_md = Path(tmp) / "f.csv", Path(tmp) / "f.md"
        run(FIXTURE_PATH, "development", out_csv, out_md, use_fixture=True)
        with out_csv.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CSV_COLUMNS, reader.fieldnames
            assert len(list(reader)) == 5
        md = out_md.read_text(encoding="utf-8")
        assert md.count("\n| original_nsc |") + md.count(
            "\n| reported_parameters |") == 5 + 2  # 5 failure rows + 2 summary rows
        assert "FIXTURE WORLD" in md
        for example, produced in ((EXAMPLE_CSV, out_csv), (EXAMPLE_MD, out_md)):
            if example.exists():
                assert example.read_text(encoding="utf-8") == produced.read_text(
                    encoding="utf-8"), f"{example} drifted; regenerate it"
    print("OUTPUT OK (13-column CSV, readable MD, committed examples current)")

    bad = copy.deepcopy(payload)
    bad["trials"] = 200
    assert _expect_error(ContractError, bad, world)
    bad = copy.deepcopy(payload)
    bad["entries"][0]["chosen_ppl"][0] += 1.0
    assert _expect_error(ContractError, bad, world)
    bad = copy.deepcopy(payload)
    bad["entries"][0]["pool"] = bad["entries"][0]["pool"][1:]
    assert _expect_error(ContractError, bad, world)
    bad = copy.deepcopy(payload)
    target = bad["entries"][0]  # original_nsc, cap 2M, k=1: chose syn_c
    target["chosen"], target["chosen_ppl"] = ["syn_a"], [FIXTURE_PPL["syn_a"]]
    target["best_ppl"] = FIXTURE_PPL["syn_a"]
    target["regret"] = FIXTURE_PPL["syn_a"] - target["oracle_ppl"]
    assert _expect_error(ContractError, bad, world)  # not a top-1 under NSC
    assert _expect_error(ContractError, payload, world, split="final")
    before = len(OPENED)
    try:
        run(FIXTURE_PATH, "final", None, None)
        raise AssertionError("--split final without --allow-final was accepted")
    except UsageError:
        pass
    assert len(OPENED) == before, "a data file was read before refusing final"
    print("CONTRACT OK (trials=200, wrong chosen_ppl, pool mismatch, non-top-k "
          "choice, split mismatch, final without --allow-final: all rejected)")
    print("SELECTION FAILURES OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selection", type=Path,
                        default=REPO / "results" / "selection_1000.json")
    parser.add_argument("--split", choices=("development", "final"),
                        default="development")
    parser.add_argument("--allow-final", action="store_true",
                        help="required with --split final (role B, after freeze)")
    parser.add_argument("--fixture-world", action="store_true",
                        help="analyse the synthetic world embedded in the input")
    parser.add_argument("--out-csv", type=Path,
                        default=REPO / "results" / "selection_failures.csv")
    parser.add_argument("--out-md", type=Path,
                        default=REPO / "docs" / "selection_failures.md")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-fixture", type=Path, metavar="PATH",
                        help="maintenance: regenerate the synthetic fixture")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.write_fixture:
        args.write_fixture.write_text(json.dumps(build_fixture(), indent=2) + "\n",
                                      encoding="utf-8")
        print(f"wrote {args.write_fixture}")
        return 0
    try:
        rows, summary = run(args.selection, args.split, args.out_csv, args.out_md,
                            allow_final=args.allow_final,
                            use_fixture=args.fixture_world)
    except UsageError as exc:
        print(f"REFUSED: {exc}")
        return 2
    except (ContractError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"CONTRACT ERROR: {exc}")
        return 1
    print(f"entries analysed: {summary['entries']} (random skipped: "
          f"{summary['skipped_random']}); failures: {summary['failures']}")
    print(f"wrote {args.out_csv} ({len(rows)} rows) and {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
