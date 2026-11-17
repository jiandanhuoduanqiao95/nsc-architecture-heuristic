"""Reproduce role B's development experiments; never evaluate held-out labels.

Run ``python role_b_experiments.py --stage grids``, then ``--stage analysis``.
Use ``--check`` to recompute deterministic exports without overwriting them.
The official 200-trial harness is retained as a consistency appendix; all
main selection estimates use the supplied 1,000-trial implementation.
"""
import argparse
import copy
import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ctxnsc
import evaluate
import nsc
from tools import select_alpha, selection_failures
from tools.selection_ext import representative_choice, select_trials_ext

ROOT = Path(__file__).resolve().parent
GRID = (0.0, 0.25, 0.5, 1.0, 2.0)
RESULTS = ROOT / "results"
RULE = "same d_model; min(total)/max(total)>=0.90"


def read_json(path):
    """Read one explicitly selected UTF-8 artifact."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_text(payload):
    """Serialize finite, deterministic artifacts with a terminal newline."""
    return json.dumps(payload, indent=2, allow_nan=False) + "\n"


def artifact(relative, text, check=False):
    """Write a generated artifact, or compare it without changing any bytes."""
    path = ROOT / relative
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            raise ValueError("Artifact drift: " + relative)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    print(("CHECK " if check else "WROTE ") + relative, flush=True)


def command(arguments, log_name):
    """Run an existing project command, showing and recording its real output."""
    argv = [sys.executable, "-X", "utf8"] + arguments
    print("\n$ " + subprocess.list2cmdline(argv), flush=True)
    start = time.perf_counter()
    result = subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding="utf-8",
                            env=dict(os.environ, PYTHONUTF8="1"))
    elapsed = time.perf_counter() - start
    print(result.stdout, end="", flush=True)
    print("exit={} wall_seconds={:.3f}".format(result.returncode, elapsed), flush=True)
    record = "$ " + subprocess.list2cmdline(argv) + "\n" + result.stdout
    record += "\nexit={} wall_seconds={:.3f}\n".format(result.returncode, elapsed)
    artifact("results/role_b_logs/" + log_name + ".txt", record)
    if result.returncode:
        raise RuntimeError("Command failed; see log " + log_name)


def grids():
    """B1-B3: run both matched grids through the unmodified official harness."""
    (RESULTS / "dev_grid").mkdir(parents=True, exist_ok=True)
    for prefix in ("dev_alpha", "m3_beta"):
        for value in GRID:
            stem = "{}_{:.2f}".format(prefix, value)
            command(["evaluate.py", "--split", "development", "--student",
                     "variants/" + stem + ".py", "--output",
                     "results/dev_grid/" + stem + ".json"], stem)
    command(["tools/make_variants.py", "--verify"], "verify_m2")
    command(["tools/make_position_variants.py", "--verify"], "verify_m3")
    for method in ("cumulative", "position"):
        command(["tools/select_alpha.py", "--method", method,
                 "--grid", "0,0.25,0.5,1,2"], "select_" + method)


def selected_parameters():
    """Re-derive selection and every grid rho before consuming chosen values."""
    selected = []
    for method, prefix in (("cumulative", "dev_alpha"), ("position", "m3_beta")):
        payload = read_json(RESULTS / ("dev_grid_" + method + ".json"))
        rho, _, _ = select_alpha.dev_grid(method, GRID)
        value, tied = select_alpha.select_from_rho(rho)
        expected = {"method": method, "grid": list(GRID),
                    "rho": [rho[a] for a in GRID], "selected": value,
                    "tie_break_used": tied, "score_precision": "12 significant digits"}
        if payload != expected:
            raise ValueError("Selector artifact does not match recomputation: " + method)
        for a in GRID:
            harness = read_json(RESULTS / "dev_grid" / ("{}_{:.2f}.json".format(prefix, a)))
            if harness["ranking"]["student"]["spearman_rho"] != rho[a]:
                raise ValueError("Harness and selector disagree: " + method)
        selected.append(value)
    return tuple(selected)


def development_world():
    """Load only the development architecture order, outcomes and resources."""
    data = ROOT / "data"
    configs = read_json(data / "architectures.json")
    keys = read_json(data / "splits.json")["development"]
    resources = read_json(data / "resources.json")
    labels = read_json(data / "development_labels.json")
    return configs, keys, resources, {key: labels[key]["valid_ppl"] for key in keys}


def build_exports():
    """B4/B6: canonical scores, official ranking metrics and 64 selection cells.

    Each real 1,000-trial stream is checked against the official 200-trial
    aggregates and its exact first 200 trials. Outcomes are consulted only
    after canonical score-based choices; scorers receive configurations only.
    """
    alpha, beta = selected_parameters()
    configs, keys, resources, ppl = development_world()
    functions = {
        "original_nsc": nsc.original_nsc,
        "m2_alpha_{:g}".format(alpha): lambda cfg: ctxnsc.score_config(cfg, alpha),
        "m3_beta_{:g}".format(beta): lambda cfg: ctxnsc.score_with_ratios(
            cfg, beta, ctxnsc.position_ratios(cfg["n_layer"])),
        "position_example": nsc.position_example,
        "reported_parameters": None,
        "reference_flops": lambda cfg: nsc.resource_estimate(cfg)["reference_flops_per_token"],
        "ablation": nsc.original_nsc,
    }
    scores = {}
    for method, function in functions.items():
        scores[method] = {key: evaluate.canonical(resources[key]["total"] if function is None
                            else function(copy.deepcopy(configs[key]))) for key in keys}
    quality = [-ppl[key] for key in keys]
    pairs = [(i, j) for i in range(len(keys)) for j in range(i)]
    matched = [(i, j) for i, j in pairs
               if configs[keys[i]]["d_model"] == configs[keys[j]]["d_model"]
               and min(resources[keys[i]]["total"], resources[keys[j]]["total"])
               / max(resources[keys[i]]["total"], resources[keys[j]]["total"]) >= 0.90]
    if len(keys) != 100 or len(matched) != 180:
        raise ValueError("Unexpected development panel or size-control pair count")
    ranking = {}
    for method, values in scores.items():
        column = [values[key] for key in keys]
        ranking[method] = {"spearman_rho": evaluate.correlation(evaluate.ranks(column), evaluate.ranks(quality)),
                           "all_pairs": evaluate.pair_summary(column, quality, pairs),
                           "size_controlled_pairs": evaluate.pair_summary(column, quality, matched)}
    # Cross-check against harness output; no duplicated metric conventions.
    for method, prefix, value in (("m2_alpha_{:g}".format(alpha), "dev_alpha", alpha),
                                  ("m3_beta_{:g}".format(beta), "m3_beta", beta)):
        harness = read_json(RESULTS / "dev_grid" / ("{}_{:.2f}.json".format(prefix, value)))
        for name in ("original_nsc", "position_example", "reported_parameters", "reference_flops", "ablation"):
            if ranking[name] != harness["ranking"][name]:
                raise ValueError("Baseline ranking disagrees with harness: " + name)
        if ranking[method] != harness["ranking"]["student"]:
            raise ValueError("Selected ranking disagrees with harness: " + method)
    entries, appendix = [], []
    for cap in evaluate.BUDGETS:
        pool = [key for key in keys if resources[key]["total"] <= cap]
        for k in evaluate.K_VALUES:
            seed = 202627 + cap + k
            for method in list(scores) + ["random"]:
                values = scores.get(method)
                chosen = representative_choice(pool, values, k, seed)
                long_run = select_trials_ext(pool, values, k, ppl, seed, repeats=1000, return_trials=True)
                short_run = select_trials_ext(pool, values, k, ppl, seed, repeats=200, return_trials=True)
                official = evaluate.select_trials(pool, values, k, ppl, seed)
                trials = long_run.pop("best_ppl_trials")
                prefix = short_run.pop("best_ppl_trials")
                if prefix != trials[:200] or short_run != official:
                    raise ValueError("200-trial prefix or harness parity failed: " + method)
                chosen_ppl = [ppl[key] for key in chosen]
                oracle = min(ppl[key] for key in pool)
                entries.append(dict(method=method, cap=cap, k=k, seed=seed, pool=pool,
                                    chosen=chosen, chosen_ppl=chosen_ppl, best_ppl=min(chosen_ppl),
                                    oracle_ppl=oracle, regret=min(chosen_ppl) - oracle, **long_run))
                appendix.append(dict(method=method, cap=cap, k=k, prefix_equal=True,
                                     harness_equal=True, **official))
    if len(entries) != 64:
        raise ValueError("Expected eight methods/baselines times eight budget cells")
    selection = {"split": "development", "trials": 1000, "entries": entries}
    # A's independent contract validator recomputes pools, labels and top-k choices.
    world = selection_failures.load_archive_world("development", False)
    selection_failures.analyse(selection, world, "development")
    rank_export = {"split": "development", "architectures": len(keys), "alpha_star": alpha,
                   "beta_star": beta, "matched_rule": RULE, "ranking": ranking}
    return selection, rank_export, {"split": "development", "trials": 200,
                                    "purpose": "prefix-consistency appendix only", "entries": appendix}


def csv_text(rows, columns):
    """Render a portable CSV table using named fields."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def report(selection, ranking, failures):
    """Render report-ready development tables and bounded interpretation."""
    lines = ["# Role B development results", "",
             "Generated by `python role_b_experiments.py --stage analysis`; verify with `--check`.", "",
             "Development only: 100 architectures. No held-out evaluation has been run.", "",
             "## Parameter selection", "",
             "Both grids: {0, 0.25, 0.5, 1, 2}. Maximize average-rank Spearman rho",
             "against negative development validation PPL after score canonicalization",
             "to 12 significant digits. Rho ties at 12 digits choose the smaller value.", "",
             "| method | value | rho | selected |", "|---|---:|---:|---|"]
    for method in ("cumulative", "position"):
        grid = read_json(RESULTS / ("dev_grid_" + method + ".json"))
        for value, rho in zip(grid["grid"], grid["rho"]):
            lines.append("| {} | {:g} | {:.9f} | {} |".format(method, value, rho,
                         "yes" if value == grid["selected"] else ""))
        lines += ["", "{}: tie_break_used={}.".format(method, grid["tie_break_used"]), ""]
    lines += ["## Ranking", "", "Size-control rule: `" + RULE + "`; 180 development pairs.",
              "Pairs overlap and do not constitute independent samples.", "",
              "| method | Spearman rho | Kendall tau-b | score-only ties | quality-only ties | both ties | controlled tau-b |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for method, row in ranking["ranking"].items():
        p = row["all_pairs"]
        lines.append("| {} | {:.9f} | {:.9f} | {} | {} | {} | {:.9f} |".format(
            method, row["spearman_rho"], p["tau_b"], p["score_only_ties"], p["quality_only_ties"],
            p["both_ties"], row["size_controlled_pairs"]["tau_b"]))
    lines += ["", "## Selection (main protocol: 1,000 trials)", "",
              "Same feasible pools (`reported total <= cap`), seeds `202627 + cap + k`,",
              "canonical scores, shuffle then stable descending sort; uniform random uses sampling.",
              "Regret = best revealed PPL minus the pool's oracle PPL. SD reflects selection",
              "and tie-breaking randomness; it does not measure training-seed uncertainty.", "",
              "| cap | k | method | eligible | mean best PPL | mean regret | SD best PPL |",
              "|---:|---:|---|---:|---:|---:|---:|"]
    for row in selection["entries"]:
        lines.append("| {:,} | {} | {} | {} | {:.6f} | {:.6f} | {:.6f} |".format(
            row["cap"], row["k"], row["method"], len(row["pool"]), row["mean_best_ppl"],
            row["mean_regret"], row["sd_best_ppl"]))
    cells = {(row["method"], row["cap"], row["k"]): row for row in selection["entries"]}
    m2 = "m2_alpha_{:g}".format(ranking["alpha_star"])
    m3 = "m3_beta_{:g}".format(ranking["beta_star"])
    lines += ["", "### Paired selection comparison", "",
              "| cap | k | original NSC regret | M2 regret | M3 regret |",
              "|---:|---:|---:|---:|---:|"]
    comparisons = []
    for cap in evaluate.BUDGETS:
        for k in evaluate.K_VALUES:
            values = [cells[(name, cap, k)]["mean_regret"] for name in ("original_nsc", m2, m3)]
            comparisons.append(values)
            lines.append("| {:,} | {} | {:.6f} | {:.6f} | {:.6f} |".format(cap, k, *values))
    wins = sum(b < a for a, b, _ in comparisons)
    losses = sum(b > a for a, b, _ in comparisons)
    ties = len(comparisons) - wins - losses
    same = sum(b == c for _, b, c in comparisons)
    base = ranking["ranking"]["original_nsc"]
    changed = ranking["ranking"][m2]
    lines += ["", "M2 versus original NSC: {} lower-regret cells, {} equal, {} higher.".format(wins, ties, losses),
              "M2 and M3 have equal mean regret in {}/8 cells; this selection experiment".format(same),
              "does not distinguish the cumulative mechanism from the positional control.", "",
              "M2's Spearman rho changes from {:.9f} to {:.9f}, while its controlled".format(
                  base["spearman_rho"], changed["spearman_rho"]),
              "tau-b changes from {:.9f} to {:.9f}. These metrics support a mixed result,".format(
                  base["size_controlled_pairs"]["tau_b"], changed["size_controlled_pairs"]["tau_b"]),
              "rather than a uniform improvement. Alpha is at the largest pre-specified grid value;",
              "this is an optimum within the tested grid, not a continuous global optimum."]
    lines += ["", "## Three distinct failure cases", "",
              "Representative trial-1 choices; repeated methods on the same choice are deduplicated.", "",
              "| method | cap | k | chosen IDs | oracle ID | gap PPL | oracle score rank | diagnostic tags |",
              "|---|---:|---:|---|---|---:|---:|---|"]
    seen = set()
    candidates = sorted(failures, key=lambda row: (row["method"] != m2, -float(row["gap"])))
    for row in candidates:
        key = (row["cap"], row["k"], row["chosen_ids"], row["best_id"])
        if key in seen:
            continue
        seen.add(key)
        lines.append("| {} | {} | {} | {} | {} | {:.6f} | {} | {} |".format(
            row["method"], row["cap"], row["k"], row["chosen_ids"].replace("|", ", "),
            row["best_id"], float(row["gap"]), row["score_rank_of_best"],
            row["reason_tags"].replace("|", ", ")))
        if len(seen) == 3:
            break
    if len(seen) < 3:
        raise ValueError("Need three distinct failure cases")
    lines += ["", "## Normalization side effect (C3; separate evidence)", "",
              "Changing a later layer changes S0 and hence earlier layers' normalized prefixes.",
              "The following existing label-free diagnostic is a limitation, separate from ranking",
              "and selection results and from the controlled reorder mechanism argument.", "",
              "Source: `results/normalization_probe.csv` (generator: `tools/normalization_probe.py`).", ""]
    with (RESULTS / "normalization_probe.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups = {}
    for row in rows:
        groups.setdefault((row["config_id"], row["variant"], row["alpha"]), []).append(row)
    lines += ["Maxima below concern earlier untouched layers only; the modified last layer is excluded.", "",
              "| config | last-layer variant | alpha | max abs delta c | max abs delta factor | max abs delta contribution | delta total S |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for (cid, variant, alpha), group in groups.items():
        last = max(int(row["layer"]) for row in group)
        earlier = [row for row in group if int(row["layer"]) < last]
        maxima = [max(abs(float(row[field])) for row in earlier)
                  for field in ("delta_c", "delta_factor", "delta_contribution")]
        lines.append("| {} | {} | {} | {:.6g} | {:.6g} | {:.6g} | {:.6g} |".format(
            cid, variant, alpha, *maxima, float(group[0]["delta_S_total"])))
    lines += ["", "## Scope and interpretation", "",
              "Parameter tuning and these comparisons use the same development panel; they are",
              "preliminary and cannot establish generalization. Synthetic reorder sensitivity is",
              "not trained predictive evidence. Budgets use reported total parameters (including",
              "adaptive embeddings); NSC scores projection matrices. Reference FLOPs are a dense",
              "operation estimate, not measured latency. Shared-cache scoring times are diagnostics.", "",
              "The 200-trial results are only a prefix-consistency appendix (64/64 cells checked).",
              "Failure cases: `docs/selection_failures.md`. Final evaluation waits for C's freeze tag.", ""]
    return "\n".join(lines)


def analysis(check=False):
    """Generate or verify all B4-B6 deterministic artifacts, including failures."""
    selection, ranking, appendix = build_exports()
    artifact("results/selection_1000.json", json_text(selection), check)
    artifact("results/dev_ranking.json", json_text(ranking), check)
    artifact("results/selection_200_appendix.json", json_text(appendix), check)
    rows = []
    for name, stats in ranking["ranking"].items():
        rows.append(dict(method=name, spearman_rho=stats["spearman_rho"],
                         **stats["all_pairs"], controlled_pairs=stats["size_controlled_pairs"]["pairs"],
                         controlled_tau_b=stats["size_controlled_pairs"]["tau_b"]))
    artifact("results/dev_ranking.csv", csv_text(rows, list(rows[0])), check)
    selection_rows = [{key: row[key] for key in ("method", "cap", "k", "oracle_ppl",
                      "mean_best_ppl", "mean_regret", "sd_best_ppl", "trials")}
                      for row in selection["entries"]]
    artifact("results/selection_1000_table.csv", csv_text(selection_rows, list(selection_rows[0])), check)
    world = selection_failures.load_archive_world("development", False)
    failures, summary = selection_failures.analyse(selection, world, "development")
    artifact("results/selection_failures.csv", selection_failures.render_csv(failures), check)
    artifact("docs/selection_failures.md", selection_failures.render_md(
        failures, summary, "results/selection_1000.json", "development", False), check)
    artifact("docs/role_b_development.md", report(selection, ranking, failures), check)
    print("alpha_star={:g}; beta_star={:g}; 64/64 prefix and harness comparisons passed".format(
          ranking["alpha_star"], ranking["beta_star"]), flush=True)
    print("Failure analysis: {} entries; {} failures; {} successes".format(
          summary["entries"], summary["failures"], summary["successes"]), flush=True)


def acceptance():
    """Capture checks, including known Windows failures, without hiding any exit.

    Mutation acceptance additionally requires each seeded bug's designated
    catcher; the pre-existing CH01 failure cannot count as mutation evidence.
    Actual export corruptions must also fail A's independent contract checker.
    """
    commands = [
        (["check_starter.py"], "starter"),
        (["checks/run_checks.py", "--no-write"], "checks"),
        (["-m", "unittest", "discover", "-s", "tests", "-t", "."], "unittest"),
        (["checks/run_checks.py", "--mutations"], "mutations"),
        (["tools/selection_ext.py", "--self-test"], "selection_protocol"),
        (["tools/check_docs_counts.py"], "doc_counts"),
        (["tools/check_py39.py"], "stdlib"),
        (["tools/make_figures.py", "--check"], "figures"),
        (["tools/make_report_pack.py", "--check"], "report_pack"),
        (["role_b_experiments.py", "--check"], "artifact_check"),
    ]
    statuses = {}
    for arguments, log_name in commands:
        try:
            command(arguments, log_name)
            statuses[log_name] = "PASS"
        except RuntimeError:
            statuses[log_name] = "FAIL (see raw log)"
    # Designated catchers from the existing mutation definitions, no changes
    # to A's checks or mutations and no credit for unrelated baseline failures.
    from checks.mutations import build_mutations
    output = (RESULTS / "role_b_logs" / "mutations.txt").read_text(encoding="utf-8")
    for mid, _, _, expected in build_mutations():
        line = next((line for line in output.splitlines() if line.startswith(mid + " ")), "")
        if not all(re.search(r"\b" + catcher + r" [1-9][0-9]*/[0-9]+ failed", line)
                   for catcher in expected.split("/")):
            raise ValueError("Designated mutation catcher absent: " + mid)
    statuses["mutation_designated_catchers"] = "7/7 confirmed (CH01 excluded)"
    payload = read_json(RESULTS / "selection_1000.json")
    world = selection_failures.load_archive_world("development", False)
    negative_cases = []
    for field, replacement in (("best_ppl", -1.0), ("pool", []), ("chosen_ppl", [-1.0])):
        bad = copy.deepcopy(payload)
        bad["entries"][0][field] = replacement
        negative_cases.append((field, bad))
    bad = copy.deepcopy(payload)
    bad["trials"] = 200
    negative_cases.append(("wrong trial count", bad))
    for name, bad in negative_cases:
        try:
            selection_failures.analyse(bad, world, "development")
        except selection_failures.ContractError:
            print("EXPORT NEGATIVE CAUGHT: " + name, flush=True)
        else:
            raise ValueError("Export corruption was accepted: " + name)
    statuses["export_negative_cases"] = "4/4 rejected"
    statuses["python"] = platform.python_version()
    statuses["platform"] = platform.platform()
    artifact("results/role_b_acceptance.json", json_text(statuses))
    print(json_text(statuses), flush=True)
    return 1 if any(value.startswith("FAIL") for value in statuses.values()) else 0


def checkout_check():
    """Validate B's changes in a fresh LF checkout without rewriting originals.

    Git materializes the committed starter; only explicitly named B files
    and the required doc-count update are overlaid. The temporary checkout
    is retained for inspection. This does not repair the user's working tree.
    """
    target = Path(tempfile.mkdtemp(prefix="nsc-role-b-lf-"))
    argv = ["git", "-c", "safe.directory=" + ROOT.as_posix(), "-c", "core.autocrlf=false",
            "clone", "--no-hardlinks", "--quiet", str(ROOT), str(target)]
    subprocess.run(argv, cwd=str(ROOT), check=True)
    files = ["role_b_experiments.py", "docs/reproduction.md", "docs/HANDOFF_B.md",
             "docs/role_b_development.md", "docs/selection_failures.md",
             "results/dev_grid_cumulative.json", "results/dev_grid_position.json",
             "results/dev_ranking.json", "results/dev_ranking.csv",
             "results/selection_1000.json", "results/selection_1000_table.csv",
             "results/selection_200_appendix.json", "results/selection_failures.csv"]
    files += [path.relative_to(ROOT).as_posix() for path in (RESULTS / "dev_grid").glob("*.json")]
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    print("Retained isolated LF checkout: " + str(target), flush=True)
    transcript = ["Isolated LF checkout: " + str(target)]
    failed = []
    for arguments in (["check_starter.py"], ["checks/run_checks.py", "--no-write"],
                      ["checks/run_checks.py", "--mutations"],
                      ["role_b_experiments.py", "--check"]):
        argv = [sys.executable, "-X", "utf8"] + arguments
        print("\n$ " + subprocess.list2cmdline(argv), flush=True)
        start = time.perf_counter()
        result = subprocess.run(argv, cwd=str(target), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8",
                                env=dict(os.environ, PYTHONUTF8="1"))
        footer = "exit={} wall_seconds={:.3f}".format(result.returncode, time.perf_counter() - start)
        print(result.stdout + footer, flush=True)
        transcript += ["$ " + subprocess.list2cmdline(argv), result.stdout, footer]
        if result.returncode:
            failed.append(arguments)
    artifact("results/role_b_logs/lf_checkout.txt", "\n".join(transcript) + "\n")
    if failed:
        raise RuntimeError("Isolated checkout validation failed: " + repr(failed))
    print("LF CHECKOUT OK: starter, 18/18 checks, 7/7 mutations and B artifacts", flush=True)
    return 0


def main():
    """Expose development-only stages with an explicit non-mutating check mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("grids", "analysis", "acceptance", "checkout-check", "all"), default="all")
    parser.add_argument("--check", action="store_true", help="recompute and compare B analysis artifacts")
    args = parser.parse_args()
    print("ROLE B DEVELOPMENT | Python {} | {} | {}".format(
          platform.python_version(), platform.platform(), sys.executable), flush=True)
    if args.check:
        analysis(check=True)
    elif args.stage == "acceptance":
        return acceptance()
    elif args.stage == "checkout-check":
        return checkout_check()
    else:
        if args.stage in ("grids", "all"):
            grids()
        if args.stage in ("analysis", "all"):
            analysis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
