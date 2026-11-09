#!/usr/bin/env python3
"""Generate docs/report_pack.md — role A's material for the 4-page report.

    python3 tools/make_report_pack.py            # (re)write docs/report_pack.md
    python3 tools/make_report_pack.py --check    # exit 1 on drift / rule breach

Every empirical number in the pack is read from a committed artifact at
render time and carries a source id ``[Sn]``; the "Sources" table maps each
id to the file, the key or computation, and the raw value. Protocol
constants (caps, k, trials, grid) are read live from the code that defines
them and carry ``[Pn]``. No number is typed into the prose by hand, so the
pack cannot silently drift from ``results/``: ``--check`` re-renders and
compares, and enforces that the ONLY placeholders are the three
``[[B: ...]]`` slots for role B's pending results.
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import inspect  # noqa: E402
import evaluate  # noqa: E402  (protocol constants: BUDGETS, K_VALUES, REPEATS)
from checks import checks as checks_mod  # noqa: E402  (ALPHA_LIMIT_PROBE)
from tools import select_alpha  # noqa: E402  (protocol constant: DEFAULT_GRID)
from tools.selection_ext import select_trials_ext  # noqa: E402  (repeats default)

OUT = REPO / "docs" / "report_pack.md"
B_PLACEHOLDERS = ("[[B: dev ranking table]]", "[[B: selection table]]",
                  "[[B: failure cases]]")


class Facts:
    """Registry of cited values: each call returns 'value [id]'."""

    def __init__(self):
        self.items = []

    def _add(self, prefix, source, key, raw, text):
        sid = f"{prefix}{sum(1 for i in self.items if i[0].startswith(prefix)) + 1}"
        self.items.append((sid, source, key, raw, text))
        return f"{text} [{sid}]"

    def s(self, source, key, raw, text):
        return self._add("S", source, key, raw, text)

    def p(self, source, key, raw, text):
        return self._add("P", source, key, raw, text)


def load_json(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def load_csv(rel):
    with (REPO / rel).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def check_by_id(checks, cid):
    return next(c for c in checks["checks"] if c["id"] == cid)


def per_alpha(summary, alpha, key):
    return next(p[key] for p in summary["per_alpha"] if p["alpha"] == alpha)


def render():
    f = Facts()
    checks = load_json("results/checks.json")
    weighting = load_json("results/weighting_summary.json")
    norm = load_json("results/normalization_summary.json")
    reorder = load_json("results/reorder_summary.json")
    toy = next(r for r in load_csv("results/reorder_pairs.csv") if r["pair_id"] == "pair_00")
    audit = load_csv("results/data_audit.csv")
    diag = load_csv("results/weighting_diagnostic.csv")
    dev = [r for r in audit if r["split"] == "development"]
    WS = "results/weighting_summary.json"
    RP = "results/reorder_pairs.csv"
    NS = "results/normalization_summary.json"
    DA = "results/data_audit.csv"

    def ch(cid, label):
        c = check_by_id(checks, cid)
        ok = c["n_cases"] - c["n_failed"]
        return f.s("results/checks.json",
                   "{} n_cases - n_failed / n_cases ({})".format(cid, label),
                   (ok, c["n_cases"]), "{}/{}".format(ok, c["n_cases"]))

    def num(source, key, raw, fmt):
        return f.s(source, key, raw, fmt.format(raw))

    # ---- section 2 (in order of appearance) -------------------------------
    t_ch05 = ch("CH05", "alpha=0 bitwise")
    t_ch04 = ch("CH04", "layer identity")
    t_ch10 = ch("CH10", "limit")
    exponent = round(math.log10(checks_mod.ALPHA_LIMIT_PROBE))
    assert 10 ** exponent == checks_mod.ALPHA_LIMIT_PROBE
    t_probe = f.p("checks/checks.py", "ALPHA_LIMIT_PROBE", checks_mod.ALPHA_LIMIT_PROBE,
                  "10^{}".format(exponent))
    ch10 = check_by_id(checks, "CH10")
    limit_err = float(re.search(r"max rel err ([0-9.e+-]+)", ch10["detail"]).group(1))
    t_limit = num("results/checks.json", "CH10 detail: max rel err", limit_err, "{:.2e}")
    grid = ", ".join("{:g}".format(g) for g in select_alpha.DEFAULT_GRID)
    t_grid = f.p("tools/select_alpha.py", "DEFAULT_GRID", select_alpha.DEFAULT_GRID,
                 "{" + grid + "}")

    # ---- section 3 ----------------------------------------------------------
    t_toy_d = num(RP, "pair_00 d_model", int(toy["d_model"]), "{}")
    t_toy_ffn_b = f.s(RP, "pair_00 ffn_before", toy["ffn_before"],
                      "[" + toy["ffn_before"].replace("|", ", ") + "]")
    t_toy_ffn_a = f.s(RP, "pair_00 ffn_after", toy["ffn_after"],
                      "[" + toy["ffn_after"].replace("|", ", ") + "]")
    t_toy_nsc = num(RP, "pair_00 nsc_before", float(toy["nsc_before"]), "{:.9f}")
    t_toy_params = num(RP, "pair_00 projection_params", int(toy["projection_params"]), "{:,}")
    t_toy_macs = num(RP, "pair_00 reference_macs", int(toy["reference_macs"]), "{:,}")
    t_probe_alpha = num("results/reorder_summary.json", "alpha", reorder["alpha"], "{:g}")
    t_toy_after = num(RP, "pair_00 s_after_a05", float(toy["s_after_a05"]), "{:.6f}")
    t_toy_before = num(RP, "pair_00 s_a05", float(toy["s_a05"]), "{:.6f}")
    t_toy_delta = num(RP, "pair_00 delta_a05", float(toy["delta_a05"]), "{:.6f}")
    t_sweep = num("results/reorder_summary.json", "sweep_pairs", reorder["sweep_pairs"], "{:,}")
    t_viol = num("results/reorder_summary.json", "sweep_violations",
                 reorder["sweep_violations"], "{}")
    t_ch08 = ch("CH08", "single layer")
    t_ch06 = ch("CH06", "finite")
    t_ch09 = ch("CH09", "monotone")

    # ---- section 4 ----------------------------------------------------------
    s2 = weighting["s2_over_s0_dev"]
    t_s2 = " / ".join(num(WS, "s2_over_s0_dev." + k, s2[k], "{:.3f}")
                      for k in ("min", "median", "max"))
    alphas = (0.25, 0.5, 1.0, 2.0)
    t_sp = " / ".join(num(WS, "per_alpha[alpha={:g}].spearman_S_vs_S0_dev".format(a),
                          per_alpha(weighting, a, "spearman_S_vs_S0_dev"), "{:.5f}")
                      for a in alphas)
    t_pm = " / ".join(num(WS, "per_alpha[alpha={:g}].pearson_M2_M3_dev".format(a),
                          per_alpha(weighting, a, "pearson_M2_M3_dev"), "{:.5f}")
                      for a in alphas)
    pear_panel = weighting["pearson_c_vs_position"]["panel"]
    t_pear = " / ".join(num(WS, "pearson_c_vs_position.panel." + k, pear_panel[k], "{:.5f}")
                        for k in ("min", "median"))
    dev_panel = weighting["max_abs_dev"]["panel"]
    t_maxdev = " / ".join(num(WS, "max_abs_dev.panel." + k, dev_panel[k], "{:.5f}")
                          for k in ("median", "max"))
    t_gt010 = num(WS, "dev_configs_max_abs_dev_gt_0_10",
                  weighting["dev_configs_max_abs_dev_gt_0_10"], "{}")
    t_ndev = num(WS, "n_dev_rows", weighting["n_dev_rows"], "{}")
    t_depth = num(WS, "pearson_s2_over_s0_vs_n_layer_dev",
                  weighting["pearson_s2_over_s0_vs_n_layer_dev"], "{:.3f}")
    by_depth = {}
    for r in diag:
        by_depth.setdefault(int(r["n_layer"]), []).append(
            float(r["m2_alpha2"]) / float(r["m3_beta2"]))
    top_depth = max(by_depth, key=lambda depth: statistics.median(by_depth[depth]))
    t_top_depth = num("results/weighting_diagnostic.csv",
                      "n_layer group with the largest median m2_alpha2/m3_beta2",
                      top_depth, "{}")
    ratio_two = [float(r["m2_alpha2"]) / float(r["m3_beta2"]) for r in diag if r["n_layer"] == "2"]
    ratio_rest = [float(r["m2_alpha2"]) / float(r["m3_beta2"]) for r in diag if r["n_layer"] != "2"]
    t_two = num("results/weighting_diagnostic.csv",
                "median of m2_alpha2/m3_beta2 over n_layer == 2",
                statistics.median(ratio_two), "{:.3f}")
    t_rest = num("results/weighting_diagnostic.csv",
                 "median of m2_alpha2/m3_beta2 over n_layer >= 3",
                 statistics.median(ratio_rest), "{:.3f}")

    # ---- section 5 ----------------------------------------------------------
    t_npicked = num(NS, "picked_configs (count)", len(norm["picked_configs"]), "{}")
    t_variants = f.s(NS, "variants", norm["variants"],
                     " / ".join("x" + v for v in norm["variants"]))
    t_dfac = num(NS, "untouched_max_abs_delta_factor",
                 norm["untouched_max_abs_delta_factor"], "{:.3e}")
    t_dcon = num(NS, "untouched_max_abs_delta_contribution",
                 norm["untouched_max_abs_delta_contribution"], "{:.3f}")
    t_ident = num(NS, "identity_stable_worst_rel", norm["identity_stable_worst_rel"], "{:.2e}")
    t_ifail = num(NS, "identity_failures", norm["identity_failures"], "{}")

    # ---- section 6 ----------------------------------------------------------
    pairs = 0
    for i in range(len(dev)):
        for j in range(i):
            a, b = float(dev[i]["reported_total"]), float(dev[j]["reported_total"])
            if dev[i]["d_model"] == dev[j]["d_model"] and min(a, b) / max(a, b) >= 0.90:
                pairs += 1
    t_pairs = num(DA, "dev pairs with same d_model and min/max(total) >= 0.90", pairs, "{}")
    caps = ", ".join("{}M".format(b // 1000000) for b in evaluate.BUDGETS)
    t_caps = f.p("evaluate.py", "BUDGETS", evaluate.BUDGETS, caps)
    t_k = f.p("evaluate.py", "K_VALUES", evaluate.K_VALUES,
              " and ".join(str(k) for k in evaluate.K_VALUES))
    repeats_default = inspect.signature(select_trials_ext).parameters["repeats"].default
    t_trials = f.p("tools/selection_ext.py", "select_trials_ext(repeats=...) default",
                   repeats_default, "{:,}".format(repeats_default))
    t_repeats = f.p("evaluate.py", "REPEATS", evaluate.REPEATS, str(evaluate.REPEATS))
    pools = [sum(1 for r in dev if float(r["reported_total"]) <= cap) for cap in evaluate.BUDGETS]
    t_pools = " / ".join(num(DA, "dev rows with reported_total <= {}".format(cap), n, "{}")
                         for cap, n in zip(evaluate.BUDGETS, pools))

    # ---- section 7 ----------------------------------------------------------
    embed_diff = sum(1 for r in audit if r["d_embed"] != r["d_model"])
    t_embed = num(DA, "rows with d_embed != d_model", embed_diff, "{}")
    t_rows = num(DA, "rows", len(audit), "{}")
    max_tp = max(float(r["total_over_projection"]) for r in audit)
    t_maxtp = num(DA, "max total_over_projection", max_tp, "{:.2f}")
    no512 = sum(1 for r in dev if float(r["reported_total"]) <= evaluate.BUDGETS[0]
                and r["d_model"] == "512")
    t_no512 = num(DA, "dev rows with reported_total <= 10M and d_model == 512", no512, "{}")

    lines = [
        "# Report pack — role A material for the 4-page report",
        "",
        "> Generated by `tools/make_report_pack.py` from committed artifacts — do",
        "> not hand-edit (edit the generator and re-run). `[Sn]` = source of an",
        "> empirical number, `[Pn]` = protocol constant; both are listed under",
        "> *Sources* (delete the markers in the paper). The three double-bracketed",
        "> B slots in Section 6 are the results role B still has to produce. Owner",
        "> of the final text: role C.",
        "",
        "## 1. Motivation and problem",
        "",
        "Neural Spectral Capacity (NSC) scores an architecture from its",
        "specification alone by summing per-matrix Marchenko–Pastur capacities.",
        "Summation is order-blind: reordering FFN widths across layers leaves NSC",
        "unchanged, although the residual stream a later FFN reads already carries",
        "the context accumulated by earlier blocks. The course question is whether",
        "one motivated graph-aware change makes NSC sensitive to such structure and",
        "whether that improves ranking or fixed-budget selection of trained",
        "architectures — two separate claims: sensitivity is not predictive",
        "validity, and a careful negative result is a valid outcome.",
        "",
        "## 2. Method",
        "",
        "Hypothesis: the more capacity has accumulated before layer l, the smaller",
        "the marginal capacity an additional FFN block contributes. We discount each",
        "layer's FFN term by its strict-prefix capacity share:",
        "",
        "```",
        "A_l = 3·h_l·ψ(d, d//h_l) + ψ(d, d)      F_l = 2·ψ(d, f_l)",
        "S0  = Σ_l (A_l + F_l)                   C_<l = Σ_{i<l} (A_i + F_i),  C_<1 = 0",
        "c_l = C_<l / S0                         S(α) = Σ_l [ A_l + F_l / (1 + α·c_l) ]",
        "```",
        "",
        "| quantity | includes | excludes |",
        "|---|---|---|",
        "| `A_l` | per-head Q/K/V `3·h_l·ψ(d, d//h_l)` + output projection `ψ(d, d)` | bias, LayerNorm, dropout, softmax |",
        "| `F_l` | both FFN projections `2·ψ(d, f_l)` (one block) | bias, activation |",
        "| `C_<l` | layers `i < l` only; `C_<1 = 0` | current layer; embeddings; vocab head |",
        "| `S0` | all layers `1..L` | embeddings, bias, norms, vocab head |",
        "| `c_l` | `C_<l / S0` with the architecture's own `S0` | constants, panel means, clamps, epsilons |",
        "",
        "Assumptions: NSC's additive per-matrix capacity, the starter's matrix",
        "grouping and the archived init std are kept; only FFN terms are discounted.",
        "",
        "- **Zero-strength ablation is exact**: S(0) equals the starter's",
        "  `original_nsc` bit-for-bit on " + t_ch05 + " archived configurations, with",
        "  no special-case branch; per-layer `A_l + F_l` equals `nsc.layer_capacities`",
        "  elementwise and bitwise on " + t_ch04 + ".",
        "- **Limit**: c_1 = 0, so the first FFN is never discounted and",
        "  lim_(α→∞) S(α) = ΣA + F_1 — not the attention-only sum ΣA (checked at",
        "  α = " + t_probe + " on " + t_ch10 + " configurations, max relative error",
        "  " + t_limit + ").",
        "- α is chosen on the development split only, on the grid " + t_grid,
        "  by the frozen C4 rule (canonical 12-significant-digit scores, max",
        "  average-rank Spearman ρ against negative PPL, ties → smaller α).",
        "",
        "## 3. Controlled checks (before any tuning)",
        "",
        "- **Official toy pair** (d = " + t_toy_d + ", FFN " + t_toy_ffn_b + " vs " + t_toy_ffn_a + "):",
        "  both orders have the same NSC " + t_toy_nsc + ", projection parameters",
        "  " + t_toy_params + " and reference MACs " + t_toy_macs + "; at α = " + t_probe_alpha,
        "  the large-FFN-early order",
        "  scores " + t_toy_after + " vs " + t_toy_before + " (Δ = +" + t_toy_delta + ").",
        "- **Reorder sweep**: every layer pair with different FFN widths in all",
        "  archived structures (no labels read) — moving the larger FFN earlier raises",
        "  S(α) at the same α on " + t_sweep + " pairs with " + t_viol + " violations; parameters and",
        "  MACs are identical within each pair (direction lemma:",
        "  ΔS = [F(f_j) − F(f_i)]·[1/(1+αc_i) − 1/(1+αc_j)] > 0 for i < j, f_i < f_j).",
        "- **Single layer**: S(α) = S0 for every α on " + t_ch08 + " synthetic",
        "  single-layer configurations; **finite and monotone**: finite, positive",
        "  scores on " + t_ch06 + " configurations and S(α) strictly decreasing in α on",
        "  " + t_ch09 + ".",
        "",
        "## 4. Effect sizes (label-free; development split unless stated)",
        "",
        "| diagnostic | value |",
        "|---|---|",
        "| S(2)/S0 (min / median / max) | " + t_s2 + " |",
        "| Spearman(S(α), S0), α = 0.25 / 0.5 / 1 / 2 | " + t_sp + " |",
        "| Pearson(M2, M3), α = β = 0.25 / 0.5 / 1 / 2 | " + t_pm + " |",
        "| Pearson(c_l, (l+1)/L) per config, all 200 (min / median) | " + t_pear + " |",
        "| max_l abs(c_l − (l+1)/L), all 200 (median / max) | " + t_maxdev + " |",
        "| dev configs with max_l abs(c_l − (l+1)/L) > 0.10 | " + t_gt010 + " of " + t_ndev + " |",
        "| Pearson(S(2)/S0, n_layer) | " + t_depth + " |",
        "",
        "Reading: the discount is a small perturbation of the NSC ordering (S0",
        "spans two orders of magnitude, so even the strongest grid value keeps the",
        "rank correlation with S0 near one); deeper models are discounted more; and",
        "M2 (accumulated capacity) is nearly collinear with M3 (layer index only),",
        "so the attribution test has low power. Among depth groups, n_layer =",
        t_top_depth + " separates them most: median M2/M3 at α = β = 2 is " + t_two,
        "for the two-layer configurations vs " + t_rest + " for n_layer ≥ 3 — the",
        "subgroup to analyze when attributing any M2-vs-M3 difference.",
        "",
        "## 5. Normalization side effect (C3, TA 2 — report as its own table)",
        "",
        "Because c_l divides by the architecture's own total, changing only the last",
        "layer's FFN moves every earlier ratio: Δc_l = C_<l · (1/S0′ − 1/S0). On",
        t_npicked + " development configurations (smallest / median / largest S0) with",
        "the last FFN scaled by " + t_variants + ", the untouched layers' factors move by",
        "up to " + t_dfac + " and their contributions by up to " + t_dcon + " (identity",
        "verified per row, worst relative residual " + t_ident + ", " + t_ifail + " violations;",
        "full table `results/normalization_probe.csv`). This is a structural side",
        "effect of normalizing by total capacity, not evidence for the mechanism.",
        "",
        "## 6. Results role B still has to produce",
        "",
        B_PLACEHOLDERS[0],
        "",
        "Expected content: Spearman ρ, Kendall τ-b and ties for M1–M6 and the",
        "ablation on the development split, all pairs and the " + t_pairs,
        "size-controlled pairs (rule `same d_model; min(total)/max(total) >= 0.90`),",
        "plus both 5-row grids (M2 over α, M3 over β), α*, β* and `tie_break_used`",
        "(`tools/select_alpha.py --method cumulative|position`).",
        "",
        B_PLACEHOLDERS[1],
        "",
        "Expected content: best selected PPL and regret for every method and the",
        "random baseline at caps " + t_caps + " and k = " + t_k + ", from " + t_trials,
        "trials per cell (`results/selection_1000.json`); the harness's " + t_repeats,
        "trials are its exact prefix and belong in an appendix only. Development",
        "feasible pools: " + t_pools + ".",
        "",
        B_PLACEHOLDERS[2],
        "",
        "Expected content: at least three concrete cases — chosen design, pool",
        "optimum, gap and reason — from `python3 tools/selection_failures.py",
        "--selection results/selection_1000.json --split development` (table in",
        "`docs/selection_failures.md`; format preview in",
        "`docs/examples/selection_failures_example.md`).",
        "",
        "## 7. Limitations",
        "",
        "- **Scope mismatch**: `d_embed` differs from `d_model` in " + t_embed + " of",
        "  " + t_rows + " configurations (scores use `d_model`); the selection cap uses",
        "  reported totals that include adaptive embeddings — up to " + t_maxtp + "× the",
        "  scored projection parameters — and the smallest cap's pool contains",
        "  " + t_no512 + " configurations of width 512.",
        "- **Single-outcome archive**: one recorded result per architecture (no seeds,",
        "  tokens or hardware; `data/provenance.json`), so the trial variance measures",
        "  selection/tie-breaking randomness only, never training-seed uncertainty.",
        "- **Weak attribution power**: M2 and M3 are nearly collinear (Section 4); a",
        "  null M2-vs-M3 difference is uninformative about the mechanism.",
        "- **Small perturbation**: ranking changes relative to NSC are small by",
        "  construction (Section 4); sensitivity in controlled reorderings is not",
        "  predictive validity.",
        "- **Final split held out**: the final architectures are evaluated once, after",
        "  the freeze tag; nothing here used their labels.",
        "",
        "## 8. Figure specifications",
        "",
        "1. `docs/figures/reorder_alpha_curve.svg` (rendered by `tools/make_figures.py`):",
        "   S(α) of the toy pair's two FFN orders over the α grid; the lines meet at",
        "   α = 0 (the reorder tie) and separate as α grows. Data:",
        "   `results/reorder_pairs.csv`, row pair_00. Caption must say: sensitivity,",
        "   not predictive validity.",
        "2. `docs/figures/m2_m3_scores.svg` (rendered): M2 vs M3 scores of the",
        "   development configurations at the reference strength α = β = 2, log–log,",
        "   y = x line, two-layer configurations highlighted. Data:",
        "   `results/weighting_diagnostic.csv`. Caption must say the strength is a",
        "   reference value, not a tuned one.",
        "3. Selection regret (to be drawn once B's results exist): x = parameter cap,",
        "   y = mean regret over the 1,000-trial protocol, one line per method (M1–M6,",
        "   ablation, random), panels k = 1 and k = 3. Data: `results/selection_1000.json`.",
        "",
        "## Sources",
        "",
        "| id | value | source | key / computation | raw |",
        "|---|---|---|---|---|",
    ]
    for sid, source, key, raw, text_value in f.items:
        lines.append("| {} | {} | `{}` | {} | `{!r}` |".format(sid, text_value, source, key, raw))
    lines.append("")
    return "\n".join(lines)


def rule_problems(content):
    problems = []
    tokens = re.findall(r"\[\[[^\]]*\]\]", content)
    if sorted(tokens) != sorted(B_PLACEHOLDERS):
        problems.append(f"placeholders must be exactly {list(B_PLACEHOLDERS)}, got {tokens}")
    body, _, table = content.partition("## Sources")
    used = set(re.findall(r"\[([SP]\d+)\]", body))
    listed = set(re.findall(r"^\| ([SP]\d+) \|", table, flags=re.M))
    if used != listed:
        problems.append(f"source ids used {sorted(used - listed)} not listed / "
                        f"listed {sorted(listed - used)} not used")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="re-render and compare with docs/report_pack.md")
    args = parser.parse_args()
    content = render()
    problems = rule_problems(content)
    if problems:
        for line in problems:
            print("REPORT PACK RULE VIOLATION:", line)
        return 1
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("REPORT PACK DRIFTED (run python3 tools/make_report_pack.py)")
            return 1
        table = content.partition("## Sources")[2]
        n = len(re.findall(r"^\| (?:S|P)\d+ \|", table, flags=re.M))
        print(f"REPORT PACK OK (equals a fresh render; {n} cited values; "
              f"only the 3 [[B: ...]] placeholders)")
        return 0
    OUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
