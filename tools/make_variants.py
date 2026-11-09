#!/usr/bin/env python3
"""Generate (and verify) the fixed-alpha variant modules for role B (A5.2).

    python3 tools/make_variants.py                 # (re)write variants/
    python3 tools/make_variants.py --verify        # contract-check variants

Each ``variants/dev_alpha_<a>.py`` is a self-contained student module whose
only difference from ``student_score.py`` is the frozen ALPHA constant, so B
can sweep the development grid without touching the official file:

    python3 evaluate.py --split development --student variants/dev_alpha_0.50.py

``--verify`` checks, for every variant: (a) module.score(config) is bitwise
equal to ctxnsc.score_config(config, ALPHA) on sampled archive configs, and
(b) the ranking block produced by ``evaluate.py --student <variant>`` equals
the statistics recomputed from the direct ctxnsc scores (same canonical/ranks
conventions), proving the --student mechanism end to end.
"""
import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import evaluate  # noqa: E402

GRID = (0.0, 0.25, 0.5, 1.0, 2.0)

VARIANT_TEMPLATE = '''"""Fixed-alpha variant for the development grid (generated, do not edit).

Identical to student_score.py except the frozen ALPHA constant; role B runs
the grid via evaluate.py --student, role C freezes the chosen value into
student_score.py + freeze.json.
"""
from nsc import original_nsc
from ctxnsc import score_config

ALPHA = {alpha!r}


def score(config):
    """Return a finite scalar, with larger values predicting better quality."""
    return score_config(config, alpha=ALPHA)


def ablation(config):
    """Disable only our mechanism; the original NSC, independent of ALPHA."""
    return original_nsc(config)
'''


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace(".", "_"),
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate() -> int:
    out_dir = REPO / "variants"
    out_dir.mkdir(exist_ok=True)
    for alpha in GRID:
        name = f"dev_alpha_{alpha:.2f}.py"
        (out_dir / name).write_text(VARIANT_TEMPLATE.format(alpha=alpha),
                                    encoding="utf-8")
        print(f"wrote variants/{name}")
    return 0


def verify() -> int:
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    labels = json.loads((REPO / "data" / "development_labels.json").read_text())
    keys = splits["development"]
    ppl = [labels[k]["valid_ppl"] for k in keys]
    quality = [-v for v in ppl]
    total = [json.loads((REPO / "data" / "resources.json").read_text())[k]["total"]
             for k in keys]
    pairs = [(i, j) for i in range(len(keys)) for j in range(i)]
    matched = [(i, j) for i, j in pairs
               if configs[keys[i]]["d_model"] == configs[keys[j]]["d_model"]
               and min(total[i], total[j]) / max(total[i], total[j]) >= 0.90]
    failures = 0
    for alpha in GRID:
        name = f"dev_alpha_{alpha:.2f}.py"
        module = load_module(REPO / "variants" / name)
        # (a) bitwise agreement on sampled configs
        sampled = sorted(configs)[:: 20][:5]
        for key in sampled:
            if module.score(configs[key]) != ctxnsc.score_config(configs[key], alpha):
                print(f"FAIL {name}: score({key}) != score_config({key}, {alpha})")
                failures += 1
        # (b) recompute the ranking block from direct scores
        scores = [evaluate.canonical(ctxnsc.score_config(configs[k], alpha))
                  for k in keys]
        expected_ranking = {
            "spearman_rho": evaluate.correlation(evaluate.ranks(scores),
                                                 evaluate.ranks(quality)),
            "all_pairs": evaluate.pair_summary(scores, quality, pairs),
            "size_controlled_pairs": evaluate.pair_summary(scores, quality,
                                                           matched),
        }
        # evaluate.py outputs may live in results/ (A's acceptance run) or in
        # results/dev_grid/ (role B's grid runs, plan section 3.1): check both.
        candidates = [REPO / "results" / f"dev_alpha_{alpha:.2f}.json",
                      REPO / "results" / "dev_grid" / f"dev_alpha_{alpha:.2f}.json"]
        present = [p for p in candidates if p.exists()]
        if not present:
            print(f"SKIP {name}: no evaluate.py output yet (run evaluate.py "
                  f"--student variants/{name} --output "
                  f"results/dev_grid/dev_alpha_{alpha:.2f}.json)")
            continue
        for out_path in present:
            actual = json.loads(out_path.read_text())["ranking"]["student"]
            if actual != expected_ranking:
                print(f"FAIL {name}: {out_path.relative_to(REPO)} ranking block "
                      f"differs from recomputation")
                failures += 1
            else:
                print(f"OK   {name}: module scores bitwise; "
                      f"{out_path.relative_to(REPO)} ranking block matches "
                      f"recomputation")
    if failures:
        print(f"{failures} verification failures")
        return 1
    print("VARIANTS OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="verify existing variants instead of writing them")
    args = parser.parse_args()
    return verify() if args.verify else generate()


if __name__ == "__main__":
    sys.exit(main())
