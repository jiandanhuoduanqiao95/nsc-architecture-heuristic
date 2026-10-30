"""Fixed-alpha variant for the development grid (generated, do not edit).

Identical to student_score.py except the frozen ALPHA constant; role B runs
the grid via evaluate.py --student, role C freezes the chosen value into
student_score.py + freeze.json.
"""
from nsc import original_nsc
from ctxnsc import score_config

ALPHA = 0.5


def score(config):
    """Return a finite scalar, with larger values predicting better quality."""
    return score_config(config, alpha=ALPHA)


def ablation(config):
    """Disable only our mechanism; the original NSC, independent of ALPHA."""
    return original_nsc(config)
