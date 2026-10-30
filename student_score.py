"""Edit this file to implement ONE motivated graph-aware heuristic.

The evaluator passes architecture configuration only. Do not load labels,
look up architecture IDs, or fit to the final split. Record all development
choices. The unedited template deliberately returns the original baseline.
"""
from nsc import original_nsc


def score(config):
    """Return a finite scalar, with larger values predicting better quality."""
    return original_nsc(config)


def ablation(config):
    """Disable only your proposed mechanism; document what changes."""
    return original_nsc(config)
