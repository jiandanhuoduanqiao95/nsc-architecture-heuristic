#!/usr/bin/env python3
"""C3 probe: normalization side-effects when only the last layer changes (A2.12).

TA 2 asks: "Check the effect of normalizing by total architecture capacity on
scores when only later layers change." For three deterministic development
configurations (smallest / median / largest S0) we replace only the last
layer's FFN width by round(f_L * {0.5, 1.25, 2.0}) and report, per layer:
the strict-prefix capacity C_<l, both S0 values, both ratios, both discount
factors, both contributions and the total score shift.

Analytic identity checked per row (rel <= 1e-15):

    delta_c_l = C_<l * (1/S0' - 1/S0)

so "only changing a later layer" still moves every earlier layer's ratio and
factor — a structural side effect of normalizing by S0, NOT evidence of a
graph mechanism. Label-free: no PPL is read. Writes
``results/normalization_probe.csv``.
"""
import argparse
import copy
import csv
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402

VARIANTS = (0.5, 1.25, 2.0)
COLUMNS = ["config_id", "variant", "alpha", "layer", "C_prefix", "S0", "S0_new",
           "c_l", "c_l_new", "delta_c", "factor", "factor_new", "delta_factor",
           "contribution", "contribution_new", "delta_contribution",
           "delta_S_total"]


def prefix_capacities(terms):
    """C_<l per layer (strict prefix, C_<1 = 0)."""
    out, prefix = [], []
    for item in terms:
        out.append(math.fsum(prefix))
        prefix.append(item.attn + item.ffn)
    return out


def pick_configs(configs, dev_keys):
    """Deterministically pick min/median/max-S0 dev configurations."""
    entries = []
    for k in dev_keys:
        terms = ctxnsc.per_layer_terms(ctxnsc.spec_from_config(configs[k]))
        entries.append((ctxnsc.s0_from_terms(terms), k))
    entries.sort()
    median = statistics.median(s for s, _ in entries)
    lo = entries[0]
    hi = entries[-1]
    mid = min(entries, key=lambda e: (abs(e[0] - median), e[1]))
    return [lo[1], mid[1], hi[1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha", type=float, default=1.0,
                        help="discount strength used for factors (default 1.0)")
    args = parser.parse_args()
    alpha = args.alpha

    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    picked = pick_configs(configs, splits["development"])

    rows = []
    worst_identity = 0.0
    worst_literal = 0.0
    identity_failures = 0
    unchanged_factor_max, unchanged_contrib_max = 0.0, 0.0
    flips = []
    for cid in picked:
        base_cfg = configs[cid]
        base_terms = ctxnsc.per_layer_terms(ctxnsc.spec_from_config(base_cfg))
        base_ratios = ctxnsc.cumulative_ratios(base_terms)
        base_factors = ctxnsc.discount_factors(base_ratios, alpha)
        s0 = ctxnsc.s0_from_terms(base_terms)
        s_base = ctxnsc.score_terms(base_terms, alpha, base_ratios)
        prefixes = prefix_capacities(base_terms)
        n_layer = len(base_terms)
        for scale in VARIANTS:
            new_cfg = copy.deepcopy(base_cfg)
            new_cfg["d_inner"] = list(new_cfg["d_inner"])
            new_cfg["d_inner"][-1] = max(1, round(new_cfg["d_inner"][-1] * scale))
            new_terms = ctxnsc.per_layer_terms(ctxnsc.spec_from_config(new_cfg))
            new_ratios = ctxnsc.cumulative_ratios(new_terms)
            new_factors = ctxnsc.discount_factors(new_ratios, alpha)
            s0_new = ctxnsc.s0_from_terms(new_terms)
            s_new = ctxnsc.score_terms(new_terms, alpha, new_ratios)
            delta_s = s_new - s_base
            scale_desc = f"f_last*{scale:g}={new_cfg['d_inner'][-1]}"
            for i, (t, t_new) in enumerate(zip(base_terms, new_terms)):
                c, c_new = base_ratios[i], new_ratios[i]
                fac, fac_new = base_factors[i], new_factors[i]
                contrib = t.attn + t.ffn * fac
                contrib_new = t_new.attn + t_new.ffn * fac_new
                delta_c = c_new - c
                # Analytic identity for every layer with a nonzero prefix.
                # Checked in the cross-multiplied, cancellation-free form
                #   c_l_new * S0' == C_<l   and   c_l * S0 == C_<l,
                # which is algebraically identical to
                #   delta_c_l = C_<l * (1/S0' - 1/S0)
                # but avoids amplifying the rounding of (1/S0' - 1/S0) when
                # S0' ~ S0. Bound: 4 ulp(C_<l) => rel <= 4 * 2**-52 ~ 8.9e-16.
                if prefixes[i] > 0.0:
                    tol = 4.0 * math.ulp(prefixes[i])
                    lhs = abs(c_new * s0_new - prefixes[i])
                    rhs = abs(c * s0 - prefixes[i])
                    worst_identity = max(worst_identity,
                                         lhs / prefixes[i], rhs / prefixes[i])
                    if lhs > tol or rhs > tol:
                        identity_failures += 1
                    # informational: the literal factored form floats worse
                    predicted = prefixes[i] * (1.0 / s0_new - 1.0 / s0)
                    if predicted != 0.0:
                        worst_literal = max(
                            worst_literal, abs(delta_c - predicted) / abs(predicted))
                if i < n_layer - 1:  # untouched layer
                    unchanged_factor_max = max(unchanged_factor_max, abs(fac_new - fac))
                    unchanged_contrib_max = max(unchanged_contrib_max,
                                                abs(contrib_new - contrib))
                rows.append({
                    "config_id": cid, "variant": scale_desc, "alpha": repr(alpha),
                    "layer": i + 1, "C_prefix": repr(prefixes[i]),
                    "S0": repr(s0), "S0_new": repr(s0_new),
                    "c_l": repr(c), "c_l_new": repr(c_new),
                    "delta_c": repr(delta_c),
                    "factor": repr(fac), "factor_new": repr(fac_new),
                    "delta_factor": repr(fac_new - fac),
                    "contribution": repr(contrib),
                    "contribution_new": repr(contrib_new),
                    "delta_contribution": repr(contrib_new - contrib),
                    "delta_S_total": repr(delta_s),
                })
            flips.append((cid, scale_desc, s0, s0_new, s_base, s_new))

    out = REPO / "results" / "normalization_probe.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"picked configs (min/median/max S0): {', '.join(picked)}")
    print(f"identity (stable cross-multiplied form, rel): worst "
          f"{worst_identity:.2e} (bound 8.9e-16, plan cap 1e-15); "
          f"violations: {identity_failures}")
    print(f"literal form C_<(1/S0'-1/S0) worst rel (informational, "
          f"cancellation): {worst_literal:.2e}")
    print(f"untouched layers: max |delta_factor| = {unchanged_factor_max:.3e}, "
          f"max |delta_contribution| = {unchanged_contrib_max:.3e}")
    print("score-only ordering at alpha={:g} (no labels involved):".format(alpha))
    for cid, variant, s0, s0_new, s_base, s_new in flips:
        s0_sign = (s0_new > s0) - (s0_new < s0)
        s_sign = (s_new > s_base) - (s_new < s_base)
        verdict = "FLIP" if s0_sign != s_sign else "same"
        print(f"  {cid} [{variant}]: S0 {s0:.4f}->{s0_new:.4f} "
              f"({s0_sign:+d}), S {s_base:.4f}->{s_new:.4f} ({s_sign:+d}) "
              f"-> {verdict}")
    print(f"wrote {out.relative_to(REPO)} ({len(rows)} rows)")
    if identity_failures:
        print("IDENTITY VIOLATION")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
