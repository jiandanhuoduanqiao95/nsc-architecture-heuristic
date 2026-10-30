#!/usr/bin/env python3
"""Print the per-layer breakdown of S(alpha) for one archive configuration.

Usage:
    python3 tools/show_breakdown.py <config_id> <alpha>
    python3 tools/show_breakdown.py config_0_j0 0.5

A/F are printed with 6 decimals, c/factor with 9 decimals, so the output can
be checked against the hand-computed worked example in the execution plan.
The ``exact`` line compares S(0) with ``nsc.original_nsc`` bit-for-bit and
must print True (same process, same psi cache, same arithmetic path).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
from nsc import original_nsc  # noqa: E402


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    config_id, alpha_arg = sys.argv[1], sys.argv[2]
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    if config_id not in configs:
        print(f"unknown config id: {config_id}")
        return 2
    alpha = float(alpha_arg)
    bd = ctxnsc.breakdown_config(configs[config_id], alpha)
    for item in bd.items:
        print(f"l={item.layer}  A={item.attn:.6f}  F={item.ffn:.6f}   "
              f"c={item.ratio:.9f}  factor={item.factor:.9f}")
    limit = bd.sum_attn + bd.first_ffn
    print(f"S0={bd.s0:.9f}  S({alpha:g})={bd.total:.9f}  "
          f"sumA={bd.sum_attn:.9f}  sumA+F1={limit:.9f}")
    exact = ctxnsc.score_config(configs[config_id], 0.0) == original_nsc(configs[config_id])
    print(f"exact: S(0) == original_nsc -> {exact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
