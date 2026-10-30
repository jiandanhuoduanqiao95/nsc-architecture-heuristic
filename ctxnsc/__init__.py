"""ctxnsc — context-discounted NSC (CS5491 G045's one motivated change).

Public API (see docs/interface.md):

* ``score_config(config, alpha)``        -> S(alpha)
* ``scores_for_alphas(target, alphas)``  -> {alpha: S(alpha)}
* ``score_with_ratios(config, alpha, ratios)`` -> S(alpha) with caller ratios (M3)
* ``position_ratios(length)``            -> [(i+1)/L] weights for M3
* ``breakdown_config(config, alpha)``    -> per-layer Breakdown
* ``original_nsc(config)``               -> re-export of the starter baseline

The core is pure math over frozen specs; only ``adapter`` touches starter
schemas. No module here reads files or labels, and none imports
``student_score``.
"""
from nsc import original_nsc

from .adapter import spec_from_config
from .breakdown import Breakdown, BreakdownItem, breakdown, breakdown_config
from .mp import psi
from .prefix import (cumulative_ratios, discount_factors, position_ratios,
                     s0_from_terms)
from .score import (score_config, score_spec, score_terms, score_with_ratios,
                    scores_for_alphas)
from .specs import ArchitectureSpec, LayerSpec
from .terms import LayerTerms, layer_terms, per_layer_terms

__all__ = [
    "spec_from_config", "ArchitectureSpec", "LayerSpec",
    "Breakdown", "BreakdownItem", "breakdown", "breakdown_config",
    "psi",
    "cumulative_ratios", "discount_factors", "position_ratios", "s0_from_terms",
    "score_config", "score_spec", "score_terms", "score_with_ratios",
    "scores_for_alphas",
    "LayerTerms", "layer_terms", "per_layer_terms",
    "original_nsc",
]
