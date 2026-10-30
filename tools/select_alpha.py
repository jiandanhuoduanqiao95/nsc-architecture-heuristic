#!/usr/bin/env python3
"""Development-split alpha/beta selector with an exact, frozen rule (A2.11).

Rule (C4, TA 2 "freeze the exact development ranking criterion and its
tie-breaking rule"): for each grid value, canonicalize the 100 development
scores with ``evaluate.canonical`` (12 significant digits), rank them with
average ranks, and compute Spearman rho against negative dev PPL. Pick the
largest rho; when two grid values' rho are equal at 12 significant digits,
pick the SMALLER grid value and record ``tie_break_used: true``.

Role A only runs ``--self-test``. The real grids (--method ...) are run by
role B; role C freezes the outcome; CH18 re-derives it.

    python3 tools/select_alpha.py --self-test
    python3 tools/select_alpha.py --method cumulative --grid 0,0.25,0.5,1,2
    python3 tools/select_alpha.py --method position   --grid 0,0.25,0.5,1,2
"""
import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import evaluate  # noqa: E402  (starter module: canonical/ranks/correlation)

DEFAULT_GRID = (0.0, 0.25, 0.5, 1.0, 2.0)


def canonical_rho(scores, ppl):
    """Spearman rho of canonicalized scores vs negative PPL (None -> -inf)."""
    canon = [evaluate.canonical(s) for s in scores]
    rho = evaluate.correlation(evaluate.ranks(canon), evaluate.ranks([-v for v in ppl]))
    return -math.inf if rho is None else rho


def select_from_rho(rho_by_alpha):
    """Return (selected_alpha, tie_break_used) for {alpha: rho} (rho may be -inf).

    Ties are compared at 12 significant digits; the smaller alpha wins a tie.
    """
    keyed = {}
    for a, r in rho_by_alpha.items():
        keyed[a] = (-math.inf if r is None or not math.isfinite(r)
                    else float(format(r, ".12g")))
    best = max(keyed.values())
    winners = sorted(a for a, r in keyed.items() if r == best)
    return winners[0], len(winners) > 1


def dev_grid(method, grid):
    """Score every dev config at every grid value; return rho map + raw scores."""
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    labels = json.loads((REPO / "data" / "development_labels.json").read_text())
    keys = splits["development"]
    ppl = [labels[k]["valid_ppl"] for k in keys]
    scores = {}
    for alpha in grid:
        column = []
        for k in keys:
            cfg = configs[k]
            if method == "cumulative":
                column.append(ctxnsc.score_config(cfg, alpha))
            elif method == "position":
                ratios = ctxnsc.position_ratios(cfg["n_layer"])
                column.append(ctxnsc.score_with_ratios(cfg, alpha, ratios))
            else:
                raise ValueError(f"unknown method: {method}")
        scores[alpha] = column
    rho = {alpha: canonical_rho(scores[alpha], ppl) for alpha in grid}
    return rho, scores, ppl


def run_self_test():
    """Fixture checks for the argmax + tie-break logic and the dev pipeline."""
    # 1. distinct rhos: plain argmax, no tie-break.
    picked, tied = select_from_rho({0.0: 0.90, 0.25: 0.95, 0.5: 0.93})
    assert picked == 0.25 and not tied, (picked, tied)
    # 2. rho pair equal at 12 significant digits -> smaller alpha, tie recorded.
    base = 0.12345678901234
    wobble = math.nextafter(base, 1.0)  # differs in the last ULP only
    assert format(base, ".12g") == format(wobble, ".12g")
    picked, tied = select_from_rho({0.5: wobble, 2.0: base})
    assert picked == 0.5 and tied, (picked, tied)
    # 3. None rho (constant scores) is worst; two None values tie to smaller.
    picked, tied = select_from_rho({0.0: None, 0.25: 0.4, 0.5: None})
    assert picked == 0.25 and not tied, (picked, tied)
    picked, tied = select_from_rho({0.0: None, 0.25: None})
    assert picked == 0.0 and tied, (picked, tied)
    print("TIE-BREAK OK")

    # 4. End-to-end on synthetic configs: the full canonical->rho->select path.
    toy_a = {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
             "d_inner": [256, 512], "weight_init_std": 0.02}
    toy_b = {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
             "d_inner": [512, 256], "weight_init_std": 0.02}
    toy_c = {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
             "d_inner": [384, 384], "weight_init_std": 0.02}
    fake_ppl = [20.0, 25.0, 30.0]
    grid = (0.0, 0.5)
    scores = {a: [ctxnsc.score_config(c, a) for c in (toy_a, toy_b, toy_c)]
              for a in grid}
    rho = {a: canonical_rho(scores[a], fake_ppl) for a in grid}
    picked, tied = select_from_rho(rho)
    assert picked in grid and isinstance(tied, bool)
    assert all(math.isfinite(r) for r in rho.values())
    print("SELECTION OK")
    return 0


def run_grid(method, grid, output):
    """Real development grid (role B runs this; A does not tune)."""
    rho, _scores, _ppl = dev_grid(method, grid)
    selected, tied = select_from_rho(rho)
    payload = {
        "method": method,
        "grid": list(grid),
        "rho": [None if not math.isfinite(r) else r for r in
                (rho[a] for a in grid)],
        "selected": selected,
        "tie_break_used": tied,
        "score_precision": "12 significant digits",
    }
    text = json.dumps(payload, indent=2) + "\n"
    if output:
        output.write_text(text, encoding="utf-8")
        print(f"wrote {output}")
    print(f"method={method}")
    for a in grid:
        r = rho[a]
        print(f"  alpha={a:g}  rho={'-inf' if not math.isfinite(r) else f'{r:.6f}'}")
    print(f"selected={selected:g}  tie_break_used={tied}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="run the fixture checks for rule and tie-break")
    parser.add_argument("--method", choices=("cumulative", "position"))
    parser.add_argument("--grid", default=",".join(str(g) for g in DEFAULT_GRID),
                        help="comma-separated grid, e.g. 0,0.25,0.5,1,2")
    parser.add_argument("--output", type=Path, default=None,
                        help="write the grid JSON here (results/dev_grid_<m>.json)")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.method:
        grid = tuple(float(x) for x in args.grid.split(",") if x.strip())
        output = args.output or REPO / "results" / f"dev_grid_{args.method}.json"
        return run_grid(args.method, grid, output)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
