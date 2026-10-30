"""Seven seeded bugs proving the check suite can fail (A3.3).

Mutations are in-process monkeypatches: no source file is ever modified
(``git status`` must stay clean after ``--mutations``). Each mutation patches
every binding the scoring path actually uses (a module-level ``from .x import
y`` in ``ctxnsc.score`` binds its own copy, so one patch is not enough), runs
the FULL check suite, and must be caught by at least one check.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import importlib  # noqa: E402
from checks import checks as checks_mod  # noqa: E402
from ctxnsc.terms import LayerTerms  # noqa: E402

# Real module objects (the package attribute ctxnsc.breakdown is shadowed by
# the re-exported ``breakdown`` function — see checks/checks.py).
SCORE_MOD = importlib.import_module("ctxnsc.score")
BREAKDOWN_MOD = importlib.import_module("ctxnsc.breakdown")
PREFIX_MOD = importlib.import_module("ctxnsc.prefix")
TERMS_MOD = importlib.import_module("ctxnsc.terms")


def _patched_cumulative_ratios_include_current(terms):
    """MU2: the ratio of layer l includes the layer's own capacity."""
    import math as _math
    s0 = _math.fsum(item.attn + item.ffn for item in terms)
    ratios, prefix = [], []
    for item in terms:
        prefix.append(item.attn + item.ffn)
        ratios.append(_math.fsum(prefix) / s0)
    return ratios


def _patched_cumulative_ratios_reverse(terms):
    """MU5: weights become (L - l)/L instead of strict prefixes."""
    length = len(terms)
    return [(length - i) / length for i in range(length)]


def _patched_discount_factors_uniform(ratios, alpha):
    """MU4: every layer discounted by 1/(1+alpha), ignoring c_l."""
    return [1.0 / (1.0 + alpha) for _ in ratios]


def _mutation_targets(module_attr):
    """All (module, attr) bindings that must be patched together."""
    module, attr = module_attr
    targets = [(module, attr)]
    if attr in ("cumulative_ratios", "discount_factors"):
        targets.append((SCORE_MOD, attr))
        targets.append((BREAKDOWN_MOD, attr))
    return targets


def apply(patch_list):
    """Apply [((module, attr), replacement)]; return the undo callable."""
    saved = []
    for (module, attr), replacement in patch_list:
        saved.append((module, attr, getattr(module, attr)))
        setattr(module, attr, replacement)

    def undo():
        for module, attr, original in saved:
            setattr(module, attr, original)

    return undo


def build_mutations():
    """[(id, description, patch_list, expected_catcher)] in execution order."""
    original_score_config = SCORE_MOD.score_config
    original_load_freeze = checks_mod.load_freeze

    def mu1_score_config(config, alpha=0.0):
        return 0.0 if alpha == 0.0 else original_score_config(config, alpha)

    def mu3_layer_terms(layer, sigma=0.02):
        from ctxnsc.mp import psi
        d, h, f = layer.hidden, layer.heads, layer.ffn
        return LayerTerms(3 * h * psi(d, d // h, sigma), 2 * psi(d, f, sigma))

    def mu7_load_freeze(mode):
        freeze, grid_cum, grid_pos = original_load_freeze(mode)
        drifted = dict(freeze)
        drifted["alpha_star"] = float(freeze["alpha_star"]) + 0.25
        return drifted, grid_cum, grid_pos

    def expand(patches):
        out = []
        for (module, attr), replacement in patches:
            for target in _mutation_targets((module, attr)):
                out.append((target, replacement))
        return out

    return [
        ("MU1", "alpha0_returns_zero",
         expand([((SCORE_MOD, "score_config"), mu1_score_config)]), "CH05"),
        ("MU2", "prefix_includes_current",
         expand([((PREFIX_MOD, "cumulative_ratios"),
                  _patched_cumulative_ratios_include_current)]), "CH07"),
        ("MU3", "drop_out_projection",
         expand([((TERMS_MOD, "layer_terms"), mu3_layer_terms)]), "CH04"),
        ("MU4", "uniform_discount",
         expand([((PREFIX_MOD, "discount_factors"),
                  _patched_discount_factors_uniform)]), "CH11/CH16"),
        ("MU5", "reverse_weights",
         expand([((PREFIX_MOD, "cumulative_ratios"),
                  _patched_cumulative_ratios_reverse)]), "CH07"),
        ("MU6", "size_control_threshold_095",
         expand([((checks_mod, "SIZE_CONTROL_MIN_RATIO"), 0.95)]), "CH17"),
        ("MU7", "freeze_alpha_mismatch",
         expand([((checks_mod, "load_freeze"), mu7_load_freeze)]), "CH18"),
    ]


def run_mutations(only=None) -> int:
    """Run each mutation against the full suite; every one must be caught."""
    caught = total = 0
    for mid, description, patch_list, expected in build_mutations():
        if only and mid not in only:
            continue
        total += 1
        undo = apply(patch_list)
        try:
            results = checks_mod.run_checks()
        finally:
            undo()
        failed = [r for r in results if not r.passed]
        ids = ", ".join(r.id for r in failed)
        if failed:
            caught += 1
            per_check = ", ".join(f"{r.id} {r.n_failed}/{r.n_cases}"
                                  for r in failed)
            print(f"{mid} {description:<26s} caught by {per_check}")
        else:
            print(f"{mid} {description:<26s} NOT CAUGHT (expected {expected}) "
                  f"-- strengthen the checks, do not remove the mutation")
    print(f"{caught}/{total} mutations caught")
    return 0 if caught == total and total else 1


if __name__ == "__main__":
    sys.exit(run_mutations())
