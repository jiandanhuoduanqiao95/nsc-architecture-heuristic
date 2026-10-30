"""Our context-discounted NSC heuristic (CS5491 G045).

score(config)    -> S(alpha): FFN capacity is discounted by the architecture's
own accumulated preceding capacity, 1/(1 + alpha * c_l) with strict-prefix
ratios c_l = C_<l / S0 (group conventions C1/C2; see docs/mechanism.md).
ablation(config) -> the original NSC (alpha = 0); removes only our mechanism.

The evaluator passes architecture configuration only. Do not load labels,
look up architecture IDs, or fit to the final split. Record all development
choices. The scoring math lives in ``ctxnsc`` (spec-only, standard library);
this file is a thin wrapper whose only tunable is the ALPHA constant below,
selected on the development split and frozen before any final evaluation.
alpha = 0 is exact recovery of the starter's original_nsc (verified bitwise
by checks/run_checks.py, CH05).
"""
from nsc import original_nsc
from ctxnsc import score_config

# Frozen at 2026-10-31 by Congyang Feng. Selected on the development split
# only (grid {0, 0.25, 0.5, 1, 2}); do not read environment variables or any
# file to change it. Role C updates this one line at the freeze, together
# with freeze.json (validated by CH18).
ALPHA = 0.0


def score(config):
    """Return a finite scalar, with larger values predicting better quality."""
    return score_config(config, alpha=ALPHA)


def ablation(config):
    """Disable only your proposed mechanism; document what changes."""
    return original_nsc(config)
