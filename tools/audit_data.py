#!/usr/bin/env python3
"""Archive data audit (Role A, task A1).

Reads ONLY the four whitelisted data files (architectures, resources, splits,
development labels) and never touches ``final_labels.json`` beyond the
byte-level hash check that ``check_starter.py`` already performs. Emits:

* ``results/data_audit.csv``  one row per configuration (200 rows + header)
* ``docs/data_audit.md``      the 12-item checklist with expected vs measured
                              values, supplementary distribution facts and the
                              three panel-wide conclusions for the report

Exit code 0 iff all twelve checklist items match the plan's expected values.
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # allow ``import nsc`` when run from tools/

from nsc import layer_capacities, resource_estimate  # noqa: E402

ALLOWED_FILES = {"architectures.json", "resources.json", "splits.json",
                 "development_labels.json"}
_OPENED = []


def read_data(name):
    """Read a whitelisted data file; refuse anything else (esp. final labels)."""
    if name not in ALLOWED_FILES:
        raise PermissionError(f"audit must not read {name!r}")
    _OPENED.append(name)
    return json.loads((REPO / "data" / name).read_text(encoding="utf-8"))


def cumulative_ratios_from_capacities(capacities):
    """Strict-prefix ratios c_l = C_<l / S0 (same convention as ctxnsc)."""
    s0 = math.fsum(capacities)
    ratios, prefix = [], []
    for cap in capacities:
        ratios.append(math.fsum(prefix) / s0)
        prefix.append(cap)
    return s0, ratios


def main():
    configs = read_data("architectures.json")
    resources = read_data("resources.json")
    splits = read_data("splits.json")
    dev_labels = read_data("development_labels.json")
    dev_keys, final_keys = splits["development"], splits["final"]
    split_of = {k: "development" for k in dev_keys}
    split_of.update({k: "final" for k in final_keys})

    rows = []
    ratios_by_id = {}
    s0_by_id = {}
    for cid in sorted(configs):
        cfg = configs[cid]
        capacities = layer_capacities(cfg)
        s0, ratios = cumulative_ratios_from_capacities(capacities)
        ratios_by_id[cid] = ratios
        s0_by_id[cid] = s0
        projection = resource_estimate(cfg)["projection_parameters"]
        total = resources[cid]["total"]
        max_dev = max(abs(c - (i + 1) / len(ratios))
                      for i, c in enumerate(ratios))
        rows.append({
            "config_id": cid,
            "split": split_of[cid],
            "d_model": cfg["d_model"],
            "d_embed": cfg["d_embed"],
            "n_layer": cfg["n_layer"],
            "n_head": "|".join(str(h) for h in cfg["n_head"]),
            "d_inner": "|".join(str(f) for f in cfg["d_inner"]),
            "reported_total": repr(float(total)),
            "nonembedding": repr(float(resources[cid]["nonembedding"])),
            "projection_params": projection,
            "total_over_projection": repr(total / projection),
            "s0": repr(s0),
            "c_last": repr(ratios[-1]),
            "max_dev_from_position": repr(max_dev),
            "dev_ppl": repr(dev_labels[cid]["valid_ppl"]) if cid in dev_labels else "",
        })

    out_csv = REPO / "results" / "data_audit.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # ---- 12-item checklist -------------------------------------------------
    checks = []

    def check(idx, desc, expected, measured, ok=None):
        checks.append((idx, desc, expected, measured, ok if ok is not None
                       else expected == measured))

    dev_cfgs = [configs[k] for k in dev_keys]
    final_cfgs = [configs[k] for k in final_keys]
    check(1, "config count / split sizes / disjoint / union",
          "200; 100+100; disjoint; union-yes",
          f"{len(configs)}; {len(dev_keys)}+{len(final_keys)}; "
          f"{'disjoint' if not set(dev_keys) & set(final_keys) else 'overlap'}; "
          f"{'union-yes' if set(dev_keys) | set(final_keys) == set(configs) else 'union-no'}")

    def list_ok(cfg):
        return (isinstance(cfg["n_head"], list) and isinstance(cfg["d_inner"], list)
                and len(cfg["n_head"]) == cfg["n_layer"]
                and len(cfg["d_inner"]) == cfg["n_layer"])

    n_lists = sum(list_ok(c) for c in configs.values())
    check(2, "n_head/d_inner are per-layer lists of length n_layer",
          "200/200", f"{n_lists}/200")

    n_div = sum(cfg["d_model"] % h == 0 for c in configs.values() for h in c["n_head"])
    total_heads = sum(c["n_layer"] for c in configs.values())
    check(3, "d_model divisible by every head count",
          "all layer-head pairs", f"{n_div}/{total_heads} layer-head pairs",
          n_div == total_heads)

    width_hist = {}
    depth_min, depth_max = math.inf, -math.inf
    for c in configs.values():
        width_hist[c["d_model"]] = width_hist.get(c["d_model"], 0) + 1
        depth_min, depth_max = min(depth_min, c["n_layer"]), max(depth_max, c["n_layer"])
    check(4, "d_model histogram / n_layer range",
          "64:49; 128:51; 256:53; 512:47; 2-16",
          "; ".join(f"{w}:{width_hist[w]}" for w in sorted(width_hist))
          + f"; {depth_min}-{depth_max}")

    n_embed_diff = sum(c["d_embed"] != c["d_model"] for c in configs.values())
    check(5, "d_embed != d_model (adaptive embedding)", 141, n_embed_diff)

    constants = {"weight_init_std": 0.02, "pre_lnorm": False, "mem_len": 192,
                 "d_head": -1, "adaptive": True}
    const_desc = "; ".join(f"{k} == {v!r} x200" for k, v in constants.items())
    const_meas = "; ".join(
        f"{k} == {v!r} x{sum(c.get(k) == v for c in configs.values())}"
        for k, v in constants.items())
    check(6, "constant archive fields", const_desc, const_meas,
          all(sum(c.get(k) == v for c in configs.values()) == 200
              for k, v in constants.items()))

    ratios_tp = sorted(resources[k]["total"]
                       / resource_estimate(configs[k])["projection_parameters"]
                       for k in configs)
    deciles = statistics.quantiles(ratios_tp, n=10)  # exclusive method
    p10, p50, p90 = deciles[0], deciles[4], deciles[8]
    fmt = lambda v: f"{v:.2f}"
    check(7, "total/projection p10/p50/p90/max",
          "1.35 / 2.85 / 12.83 / 57.85",
          f"{fmt(p10)} / {fmt(p50)} / {fmt(p90)} / {fmt(ratios_tp[-1])}",
          all(abs(a - b) < 0.005 for a, b in
              zip((p10, p50, p90, ratios_tp[-1]), (1.35, 2.85, 12.83, 57.85))))

    above = {t: sum(r > t for r in ratios_tp) for t in (2, 5, 10, 20)}
    check(8, "configs with total/projection > 2/5/10/20",
          "130 / 51 / 24 / 9", f"{above[2]} / {above[5]} / {above[10]} / {above[20]}")

    specs = [(c["d_model"], tuple(c["n_head"]), tuple(c["d_inner"]))
             for c in configs.values()]
    check(9, "duplicate specs (d_model, n_head, d_inner)", 0,
          len(specs) - len(set(specs)))

    dev_ppls = [dev_labels[k]["valid_ppl"] for k in dev_keys]
    ppl_min, ppl_med, ppl_max = (min(dev_ppls), statistics.median(dev_ppls),
                                 max(dev_ppls))
    check(10, "dev valid_ppl min/median/max", "24.35 / 38.34 / 74.38",
          f"{fmt(ppl_min)} / {fmt(ppl_med)} / {fmt(ppl_max)}",
          all(abs(a - b) < 0.005 for a, b in
              zip((ppl_min, ppl_med, ppl_max), (24.35, 38.34, 74.38))))

    budgets = (10_000_000, 20_000_000, 30_000_000, 50_000_000)
    dev_totals = [resources[k]["total"] for k in dev_keys]
    pools = [sum(t <= b for t in dev_totals) for b in budgets]
    check(11, "dev feasible pools at 10/20/30/50M caps", "24 / 65 / 83 / 96",
          " / ".join(str(p) for p in pools))

    matched = 0
    for i in range(len(dev_keys)):
        for j in range(i):
            if (configs[dev_keys[i]]["d_model"] == configs[dev_keys[j]]["d_model"]
                    and min(dev_totals[i], dev_totals[j])
                    / max(dev_totals[i], dev_totals[j]) >= 0.90):
                matched += 1
    check(12, "dev size-controlled pairs (same d_model, min/max>=0.90)",
          180, matched)

    # ---- supplementary facts (plan §1.8, no hard assertion) ----------------
    dev_rows = [r for r in rows if r["split"] == "development"]
    s0s = sorted(s0_by_id[k] for k in dev_keys)
    panel_c2 = [ratios_by_id[k][1] for k in configs]       # full 200 panel
    panel_clast = [ratios_by_id[k][-1] for k in configs]   # full 200 panel
    sup = [
        ("dev S0 min/median/max", "116.10 / 1,576.39 / 13,046.78",
         f"{s0s[0]:.2f} / {statistics.median(s0s):,.2f} / {s0s[-1]:.2f}"),
        ("panel c_2 (ratios[1]) min/max, all 200", "0.0464 / 0.6186",
         f"{min(panel_c2):.4f} / {max(panel_c2):.4f}"),
        ("panel c_last min/max, all 200", "0.3961 / 0.9591",
         f"{min(panel_clast):.4f} / {max(panel_clast):.4f}"),
        ("dev-only c_2 min/max", "- / -",
         f"{min(ratios_by_id[k][1] for k in dev_keys):.4f} / "
         f"{max(ratios_by_id[k][1] for k in dev_keys):.4f}"),
        ("dev-only c_last min/max", "- / -",
         f"{min(ratios_by_id[k][-1] for k in dev_keys):.4f} / "
         f"{max(ratios_by_id[k][-1] for k in dev_keys):.4f}"),
    ]

    # ---- write docs/data_audit.md ------------------------------------------
    lines = [
        "# Archive data audit (generated by `tools/audit_data.py` — do not hand-edit)",
        "",
        "Row-level data: `results/data_audit.csv` (200 rows + header).",
        "The audit reads only `architectures.json`, `resources.json`, `splits.json`,",
        "`development_labels.json`; it never opens `final_labels.json`",
        f"(files opened this run: {', '.join(sorted(set(_OPENED)))}).",
        "",
        "## 12-item checklist (expected values from the execution plan)",
        "",
        "| # | Check | Expected | Measured | OK |",
        "|---|---|---|---|---|",
    ]
    for idx, desc, expected, measured, ok in checks:
        lines.append(f"| {idx} | {desc} | {expected} | {measured} "
                     f"| {'YES' if ok else 'NO'} |")
    lines += [
        "",
        "## Supplementary label-free distribution facts (plan §1.8)",
        "",
        "| Quantity | Plan §1.8 | Measured |",
        "|---|---|---|",
    ]
    for desc, expected, measured in sup:
        lines.append(f"| {desc} | {expected} | {measured} |")
    lines += [
        "",
        "## Consequences for the whole group",
        "",
        "1. **`d_embed` is not `d_model`:** 141/200 configurations differ; the",
        "   scorer must parse `d_model` (via `nsc.layers`). Any implementation",
        "   reading `d_embed` produces different scores for those 141 configs.",
        "2. **Parameter budget and NSC scoring are different scopes:**",
        "   `resources.total` includes adaptive embeddings and reaches",
        f"   {ratios_tp[-1]:.2f}x the projection parameters; at the 10M cap only",
        "   24 dev configurations are eligible and none has d_model=512.",
        "   Selection experiments must state that the budget uses `total` while",
        "   the score covers projection matrices only.",
        "3. **No d_model=512 in the 10M pool:** cross-width selection",
        "   comparisons at that cap are limited. The full-panel size-controlled",
        f"   analysis ({matched} pairs) is unaffected by caps, but per-cap",
        "   readings must carry this caveat.",
        "",
    ]
    out_md = REPO / "docs" / "data_audit.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")

    for idx, desc, expected, measured, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] #{idx:2d} {desc}: {measured}")
    print(f"files opened: {sorted(set(_OPENED))}")
    print(f"wrote {out_csv.relative_to(REPO)} ({len(rows)} rows) and "
          f"{out_md.relative_to(REPO)}")
    return 0 if all(ok for *_, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
