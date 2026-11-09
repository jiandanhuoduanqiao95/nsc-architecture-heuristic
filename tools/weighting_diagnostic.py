#!/usr/bin/env python3
"""Label-free score-space diagnostics for the discount weighting (A2.9).

For every development configuration this reports how far the strict-prefix
ratios c_l are from the positional weights (l+1)/L, and how strongly the
cumulative-discount score (M2) correlates with the position-only score (M3).
It never reads any label file and never touches PPL: these numbers describe
the score space only, which is what makes them legitimate pre-tuning
diagnostics rather than tuning. Writes ``results/weighting_diagnostic.csv``
and prints a summary consumed by ``docs/mechanism.md``.
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import evaluate  # noqa: E402  (starter module: ranks/correlation conventions)

ALPHAS = (0.25, 0.5, 1.0, 2.0)


def pearson(xs, ys):
    """Pearson correlation following evaluate.correlation's convention."""
    return evaluate.correlation(list(xs), list(ys))


def spearman(xs, ys):
    """Spearman rho = Pearson of average ranks (evaluate's convention)."""
    return evaluate.correlation(evaluate.ranks(list(xs)), evaluate.ranks(list(ys)))


def min_med_max(values):
    return (f"min={min(values):.5f} median={statistics.median(values):.5f} "
            f"max={max(values):.5f}")


def min_med_max_dict(values):
    return {"min": min(values), "median": statistics.median(values),
            "max": max(values)}


def main():
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    dev_keys = splits["development"]

    rows = []
    devs, pearsons = [], []          # dev-split aggregates (CSV scope)
    panel_devs, panel_pearsons = [], []  # full-panel aggregates (plan §1.8 scope)
    m2_scores = {a: [] for a in ALPHAS}
    m3_scores = {a: [] for a in ALPHAS}
    s0_scores, s2_ratios, depths = [], [], []
    for key in configs:
        cfg = configs[key]
        n_layer = cfg["n_layer"]
        positions = [(i + 1) / n_layer for i in range(n_layer)]
        bd = ctxnsc.breakdown_config(cfg, 0.0)  # ratios/factors at alpha = 0
        ratios = [item.ratio for item in bd.items]
        max_dev = max(abs(c - p) for c, p in zip(ratios, positions))
        pear = pearson(ratios, positions)
        s0 = bd.s0
        panel_devs.append(max_dev)
        panel_pearsons.append(pear)
        if key in set(dev_keys):
            for a in ALPHAS:
                m2_scores[a].append(ctxnsc.score_config(cfg, a))
                m3_scores[a].append(ctxnsc.score_with_ratios(
                    cfg, a, ctxnsc.position_ratios(n_layer)))
            s0_scores.append(s0)
            s2_ratios.append(ctxnsc.score_config(cfg, 2.0) / s0)  # S(2)/S0
            depths.append(n_layer)
            rows.append({
                "config_id": key,
                "d_model": cfg["d_model"],
                "n_layer": n_layer,
                "c_l": "|".join(repr(c) for c in ratios),
                "position_l": "|".join(repr(p) for p in positions),
                "max_abs_dev": repr(max_dev),
                "pearson_c_vs_position": repr(pear),
                # appended at handoff (figure data, label-free): S0 and the
                # M2/M3 scores at the grid's largest strength alpha=beta=2
                "s0": repr(s0),
                "m2_alpha2": repr(m2_scores[2.0][-1]),
                "m3_beta2": repr(m3_scores[2.0][-1]),
            })
            devs.append(max_dev)
            pearsons.append(pear)

    out = REPO / "results" / "weighting_diagnostic.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    # Persist every printed aggregate so docs can be re-derived from artifacts
    # (docs/mechanism.md section 6 quotes these numbers).
    summary = {
        "n_dev_rows": len(rows),
        "pearson_c_vs_position": {"dev": min_med_max_dict(pearsons),
                                  "panel": min_med_max_dict(panel_pearsons)},
        "max_abs_dev": {"dev": min_med_max_dict(devs),
                        "panel": min_med_max_dict(panel_devs)},
        "dev_configs_max_abs_dev_gt_0_10": sum(d > 0.10 for d in devs),
        "s2_over_s0_dev": min_med_max_dict(s2_ratios),
        "pearson_s2_over_s0_vs_n_layer_dev": pearson(s2_ratios, depths),
        "per_alpha": [
            {"alpha": a,
             "spearman_S_vs_S0_dev": spearman(m2_scores[a], s0_scores),
             "pearson_M2_M3_dev": pearson(m2_scores[a], m3_scores[a])}
            for a in ALPHAS],
    }
    summary_path = REPO / "results" / "weighting_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"rows: {len(rows)} dev configs -> {out.relative_to(REPO)}; "
          f"summary -> {summary_path.relative_to(REPO)}")
    print(f"[dev 100] pearson(c_l, (l+1)/L): {min_med_max(pearsons)}")
    print(f"[dev 100] max_l |c_l - (l+1)/L|: {min_med_max(devs)}")
    print(f"[dev 100] configs with max_abs_dev > 0.10: "
          f"{sum(d > 0.10 for d in devs)}/{len(devs)}")
    print(f"[panel 200] pearson(c_l, (l+1)/L): {min_med_max(panel_pearsons)}")
    print(f"[panel 200] max_l |c_l - (l+1)/L|: {min_med_max(panel_devs)}")
    print(f"S(2)/S0 (dev): {min_med_max(s2_ratios)}")
    print(f"pearson(S(2)/S0, n_layer) (dev): {pearson(s2_ratios, depths):.3f} "
          f"(negative: deeper models are discounted more)")
    for a in ALPHAS:
        rho = spearman(m2_scores[a], s0_scores)
        m23 = pearson(m2_scores[a], m3_scores[a])
        print(f"alpha={a:g}: spearman(S(a), S0)={rho:.5f}  "
              f"pearson(M2, M3)={m23:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
