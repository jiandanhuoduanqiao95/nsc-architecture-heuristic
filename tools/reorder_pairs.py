#!/usr/bin/env python3
"""Controlled FFN-reorder experiments (A4) + the pair library used by CH11.

Direction rule (frozen): for layers i < j with different FFN widths, the
``before`` variant places the SMALLER width early and the LARGER width late,
and the ``after`` variant swaps exactly those two widths ("large FFN moved
earlier"). Only the two entries of ``d_inner`` change, so the width multiset —
and therefore projection parameters and reference MACs — is preserved, and the
original NSC is unchanged up to one rounding (math.fsum is order-independent).
Direction assertion: S(after) > S(before) for every alpha > 0.

CLI:
    python3 tools/reorder_pairs.py --write results/reorder_pairs.csv
    python3 tools/reorder_pairs.py --self-test        # quick toy-only pass

Full direction sweep (toy + every dev layer pair with differing widths) is
CH11's job; this module holds the shared construction so there is exactly one
copy of the rule.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import nsc  # noqa: E402

TOY_A = {"d_model": 128, "n_layer": 2, "n_head": [4, 4], "d_inner": [256, 512],
         "weight_init_std": 0.02}
TOY_B = {"d_model": 128, "n_layer": 2, "n_head": [4, 4], "d_inner": [512, 256],
         "weight_init_std": 0.02}
ALPHA_GRID = (0.0, 0.25, 0.5, 1.0, 2.0)


def direction_pair(cfg, i, j):
    """(before, after) configs swapping FFN widths of layers i < j, or None.

    ``before``: small FFN early, large FFN late. ``after``: large FFN early.
    Everything except d_inner[i]/d_inner[j] is untouched (deep copy).
    """
    inner = cfg["d_inner"]
    if i >= j or inner[i] == inner[j]:
        return None
    lo, hi = min(inner[i], inner[j]), max(inner[i], inner[j])
    before = copy.deepcopy(cfg)
    after = copy.deepcopy(cfg)
    before["d_inner"] = list(inner)
    after["d_inner"] = list(inner)
    before["d_inner"][i], before["d_inner"][j] = lo, hi
    after["d_inner"][i], after["d_inner"][j] = hi, lo
    return before, after


def iter_panel_pairs(configs, keys):
    """Yield (config_id, i, j, before, after) for every eligible dev layer pair."""
    for key in keys:
        cfg = configs[key]
        inner = cfg["d_inner"]
        for i in range(cfg["n_layer"]):
            for j in range(i + 1, cfg["n_layer"]):
                if inner[i] == inner[j]:
                    continue
                before, after = direction_pair(cfg, i, j)
                yield key, i, j, before, after


def pair_scores(before, after, alpha=0.5):
    """Scores and invariants for one before/after pair."""
    nsc_before = nsc.original_nsc(before)
    nsc_after = nsc.original_nsc(after)
    rel = abs(nsc_after - nsc_before) / abs(nsc_before)
    res_b = nsc.resource_estimate(before)
    res_a = nsc.resource_estimate(after)
    return {
        "nsc_before": nsc_before,
        "nsc_after": nsc_after,
        "nsc_rel_diff": rel,
        "projection_params": res_b["projection_parameters"],
        "reference_macs": res_b["reference_macs_per_token"],
        "projection_params_after": res_a["projection_parameters"],
        "reference_macs_after": res_a["reference_macs_per_token"],
        "s_a0": ctxnsc.score_config(before, 0.0),
        "s_a0_after": ctxnsc.score_config(after, 0.0),
        "s_a05": ctxnsc.score_config(before, alpha),
        "s_a05_after": ctxnsc.score_config(after, alpha),
    }


def select_panel_sources(configs, dev_keys, want=12):
    """Deterministically pick 12 source configs per the A4.2 rule.

    Buckets, in order: the 4 configs with the largest max_l |c_l-(l+1)/L|,
    then (up to) 4 with the largest S0, then the first 4 in
    sha256(config_id + "reorder") order (preferring uncovered d_model
    widths), then any remaining configs in sha256(config_id + "fill") order.
    """
    stats = []
    for key in dev_keys:
        cfg = configs[key]
        terms = ctxnsc.per_layer_terms(ctxnsc.spec_from_config(cfg))
        ratios = ctxnsc.cumulative_ratios(terms)
        positions = [(i + 1) / len(ratios) for i in range(len(ratios))]
        max_dev = max(abs(c - p) for c, p in zip(ratios, positions))
        stats.append((key, max_dev, ctxnsc.s0_from_terms(terms), cfg["d_model"]))
    by_dev = sorted(stats, key=lambda e: (-e[1], e[0]))
    by_s0 = sorted(stats, key=lambda e: (-e[2], e[0]))
    by_hash = sorted(stats, key=lambda e: (hashlib.sha256(
        (e[0] + "reorder").encode()).hexdigest(), e[0]))
    by_fill = sorted(stats, key=lambda e: (hashlib.sha256(
        (e[0] + "fill").encode()).hexdigest(), e[0]))

    picked, used = [], set()

    def eligible(key):
        inner = configs[key]["d_inner"]
        p = min(range(len(inner)), key=lambda t: (inner[t], t))
        q = max(range(len(inner)), key=lambda t: (inner[t], t))
        return p != q and inner[p] != inner[q]

    def take(entry):
        if entry[0] not in used:
            used.add(entry[0])
            picked.append(entry[0])

    # A4.2 buckets in priority order; sources that cannot form a pair
    # (argmin == argmax) are skipped and replaced from the next bucket so the
    # panel always yields 12 eligible sources.
    for entry in by_dev[:4]:
        if len(picked) >= want:
            break
        if entry[0] not in used and eligible(entry[0]):
            take(entry)
    for entry in by_s0:
        if len(picked) >= 8:
            break
        if entry[0] not in used and eligible(entry[0]):
            take(entry)
    widths = {configs[k]["d_model"] for k in picked}
    for entry in by_hash:  # prefer widths not yet covered
        if len(picked) >= want:
            break
        if entry[0] not in used and eligible(entry[0]) and entry[3] not in widths:
            take(entry)
            widths.add(entry[3])
    for entry in by_hash:
        if len(picked) >= want:
            break
        if entry[0] not in used and eligible(entry[0]):
            take(entry)
    for entry in by_fill:
        if len(picked) >= want:
            break
        if entry[0] not in used and eligible(entry[0]):
            take(entry)
    return picked[:want]


CSV_FIELDS = ["pair_id", "source_config", "d_model", "n_layer", "split",
              "ffn_before", "ffn_after", "projection_params", "reference_macs",
              "nsc_before", "nsc_after", "nsc_rel_diff",
              "s_a0", "s_a025", "s_a05", "s_a1", "s_a2", "delta_a05", "sign_ok"]


def pair_row(pair_id, source, cfg, before, after):
    s_before = {a: ctxnsc.score_config(before, a) for a in ALPHA_GRID}
    s_after = {a: ctxnsc.score_config(after, a) for a in ALPHA_GRID}
    res = nsc.resource_estimate(before)
    nsc_b = nsc.original_nsc(before)
    nsc_a = nsc.original_nsc(after)
    delta = s_after[0.5] - s_before[0.5]
    row = {
        "pair_id": pair_id,
        "source_config": source,
        "d_model": cfg["d_model"],
        "n_layer": cfg["n_layer"],
        "split": "toy" if source == "toy" else "development",
        "ffn_before": "|".join(str(f) for f in before["d_inner"]),
        "ffn_after": "|".join(str(f) for f in after["d_inner"]),
        "projection_params": res["projection_parameters"],
        "reference_macs": res["reference_macs_per_token"],
        "nsc_before": repr(nsc_b),
        "nsc_after": repr(nsc_a),
        "nsc_rel_diff": repr(abs(nsc_a - nsc_b) / abs(nsc_b)),
        "s_a0": repr(s_before[0.0]),
        "s_a025": repr(s_before[0.25]),
        "s_a05": repr(s_before[0.5]),
        "s_a1": repr(s_before[1.0]),
        "s_a2": repr(s_before[2.0]),
        "delta_a05": repr(delta),
        "sign_ok": str(delta > 0.0),
    }
    return row, s_before, s_after


def write_markdown(rows, toy_before_scores, toy_after_scores, sweep_count,
                   sweep_violations, path):
    """Generate docs/reorder_table.md from the computed rows (A4.4/A6.5)."""
    lines = [
        "# Controlled FFN reorderings (generated by `tools/reorder_pairs.py`"
        " — do not hand-edit)",
        "",
        "Direction rule (frozen): `before` places the smaller FFN early and",
        "the larger FFN late; `after` swaps exactly those two widths",
        "(\"large FFN moved earlier\"). Only two `d_inner` entries change, so",
        "projection parameters and reference MACs are identical per pair and",
        "the original NSC matches to rel <= 1e-14.",
        "",
        "| pair | source | d_model | L | ffn before -> after | params | MACs |"
        " rel NSC diff | delta S(0.5) | sign_ok |",
        "|---|---|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        ffn = (r["ffn_before"] if len(r["ffn_before"]) <= 24
               else r["ffn_before"][:10] + "..." + r["ffn_before"][-10:])
        ffn_a = (r["ffn_after"] if len(r["ffn_after"]) <= 24
                 else r["ffn_after"][:10] + "..." + r["ffn_after"][-10:])
        ffn = ffn.replace("|", "\\|")  # keep markdown tables intact
        ffn_a = ffn_a.replace("|", "\\|")
        lines.append(
            f"| {r['pair_id']} | {r['source_config']} | {r['d_model']} "
            f"| {r['n_layer']} | {ffn} -> {ffn_a} "
            f"| {r['projection_params']} | {r['reference_macs']} "
            f"| {float(r['nsc_rel_diff']):.1e} "
            f"| {float(r['delta_a05']):+.6f} | {r['sign_ok']} |")
    lines += [
        "",
        f"Full direction sweep: **{sweep_count} pairs, "
        f"{sweep_violations} violations** at alpha=0.5 (all 200 archive"
        " configurations, every layer pair with differing FFN widths;"
        " dev 4,961 + final 4,884 = 9,845; scores only, no label file read).",
        "",
        "Machine-checkable record: `results/reorder_summary.json` "
        "(sweep_pairs / sweep_violations / csv_rows).",
        "",
        "## Figure data: the toy pair's S(alpha) curves",
        "",
        "Suggested figure (whether to render it is role C's call): x-axis"
        " alpha in {0, 0.25, 0.5, 1, 2}, y-axis S(alpha); two lines = the toy",
        "FFN orders [256,512] (before) and [512,256] (after); the lines touch",
        "at alpha=0 (the reorder tie) and separate as alpha grows — this is",
        "the mechanism's sensitivity, NOT predictive validity.",
        "",
        "| alpha | S [256,512] (large late) | S [512,256] (large early) |",
        "|---:|---:|---:|",
    ]
    for alpha in ALPHA_GRID:
        lines.append(f"| {alpha:g} | {toy_before_scores[alpha]:.9f} "
                     f"| {toy_after_scores[alpha]:.9f} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def full_sweep_violations(alpha=0.5, configs=None):
    """Run the full direction sweep; return (n_pairs, violation descriptors).

    Scope: ALL 200 archive configurations (dev + final architectures — scores
    only, no label file is ever read). The plan's measured anchor is 9,845
    pairs for the full panel (dev 4,961 + final 4,884); note its prose says
    "development's 100 configurations" while quoting the 9,845 figure — we
    follow the number (stronger scope, still label-free).

    ``configs`` may be a pre-slimmed {key: config} dict (CH11 passes slim
    copies for speed). alpha=0 equality uses rel <= 1e-14, NOT bitwise:
    swapping two FFN widths re-pairs A_l with F_l, so individual addends of
    the fsum round differently (float non-associativity — anti-pattern #11).
    """
    if configs is None:
        configs = json.loads((REPO / "data" / "architectures.json").read_text())
    slim = {k: {f: configs[k][f] for f in ("d_model", "n_layer", "n_head",
                                           "d_inner", "weight_init_std")}
            for k in configs}
    keys = sorted(slim)
    violations = []
    count = 0
    for key, i, j, before, after in iter_panel_pairs(slim, keys):
        count += 1
        info = pair_scores(before, after, alpha)
        if info["projection_params"] != info["projection_params_after"]:
            violations.append(f"{key}[{i},{j}]: projection params differ")
        if info["reference_macs"] != info["reference_macs_after"]:
            violations.append(f"{key}[{i},{j}]: reference MACs differ")
        if info["nsc_rel_diff"] > 1e-14:
            violations.append(f"{key}[{i},{j}]: NSC rel diff {info['nsc_rel_diff']:.2e}")
        if info["s_a0"] == info["s_a0_after"]:
            pass
        elif abs(info["s_a0_after"] - info["s_a0"]) / abs(info["s_a0"]) > 1e-14:
            violations.append(f"{key}[{i},{j}]: alpha=0 rel diff exceeds 1e-14")
        if not (info["s_a05_after"] > info["s_a05"]):
            violations.append(
                f"{key}[{i},{j}]: direction violated at alpha={alpha} "
                f"({info['s_a05_after']!r} <= {info['s_a05']!r})")
    return count, violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path, metavar="PATH",
                        help="write the 13-row toy+panel CSV here")
    parser.add_argument("--self-test", action="store_true",
                        help="run the toy pair only")
    args = parser.parse_args()

    if args.self_test:
        before, after = TOY_A, TOY_B
        info = pair_scores(before, after, 0.5)
        assert info["projection_params"] == 327680
        assert info["reference_macs"] == 524288
        assert info["nsc_rel_diff"] <= 1e-14
        assert info["s_a0"] == info["s_a0_after"]
        assert info["s_a05_after"] > info["s_a05"]
        print("REORDER SELF-TEST OK")
        return 0

    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    sources = select_panel_sources(configs, splits["development"])

    rows, score_pairs = [], {}
    pair_id = 0
    for tag, before, after in (("toy", TOY_A, TOY_B),):
        row, s_before, s_after = pair_row(f"pair_{pair_id:02d}", tag, before,
                                          before, after)
        rows.append(row)
        score_pairs[row["pair_id"]] = (s_before, s_after)
        pair_id += 1
    for key in sources:
        cfg = configs[key]
        inner = cfg["d_inner"]
        p = min(range(len(inner)), key=lambda t: (inner[t], t))
        q = max(range(len(inner)), key=lambda t: (inner[t], t))
        if p == q:
            continue  # A4.2: skip when argmin == argmax
        early, late = min(p, q), max(p, q)  # indices ordered, per A4.2
        before, after = direction_pair(cfg, early, late)
        row, s_before, s_after = pair_row(f"pair_{pair_id:02d}", key, cfg,
                                          before, after)
        rows.append(row)
        score_pairs[row["pair_id"]] = (s_before, s_after)
        pair_id += 1

    count, violations = full_sweep_violations(0.5)

    if args.write:
        with args.write.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.write} ({len(rows)} rows)")
        toy_before, toy_after = score_pairs[rows[0]["pair_id"]]
        write_markdown(rows, toy_before, toy_after, count, len(violations),
                       REPO / "docs" / "reorder_table.md")
        summary = {"alpha": 0.5, "csv_rows": len(rows), "sweep_pairs": count,
                   "sweep_violations": len(violations),
                   "panel_sources": len(sources)}
        (REPO / "results" / "reorder_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("wrote docs/reorder_table.md; summary -> results/reorder_summary.json")

    for row in rows:
        print(f"{row['pair_id']}  src={row['source_config']:<14s} "
              f"ffn {row['ffn_before']} -> {row['ffn_after']}  "
              f"params={row['projection_params']}  macs={row['reference_macs']}  "
              f"delta_a05={float(row['delta_a05']):+.6f}  sign_ok={row['sign_ok']}")
    print(f"panel sources: {len(sources)}; full sweep pairs={count}, "
          f"violations={len(violations)}")
    for v in violations[:5]:
        print("  ", v)
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
