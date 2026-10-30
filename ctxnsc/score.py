"""The context-discounted NSC score S(alpha) and the M3 primitive.

S(alpha) = sum_l [ A_l + F_l / (1 + alpha * c_l) ] with c_l the strict-prefix
capacity ratio of this architecture (C1/C2). Summation uses math.fsum so that
alpha = 0 is bit-identical to ``nsc.original_nsc`` — there is deliberately no
``if alpha == 0`` branch anywhere.

Term-level helpers take ``LayerTerms`` sequences; config-level helpers go
through ``ctxnsc.adapter`` (the only module that touches starter schemas).
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, Mapping, Optional, Sequence

from .adapter import spec_from_config
from .prefix import cumulative_ratios, discount_factors
from .specs import ArchitectureSpec
from .terms import LayerTerms, per_layer_terms


def score_terms(terms: Sequence[LayerTerms], alpha: float,
                ratios: Optional[Sequence[float]] = None) -> float:
    """S(alpha) from precomputed layer terms (and optionally precomputed ratios)."""
    if ratios is None:
        ratios = cumulative_ratios(terms)
    factors = discount_factors(ratios, alpha)
    return math.fsum(item.attn + item.ffn * factor
                     for item, factor in zip(terms, factors))


def score_spec(spec: ArchitectureSpec, alpha: float = 0.0,
               ratios: Optional[Sequence[float]] = None) -> float:
    """S(alpha) for an ArchitectureSpec."""
    return score_terms(per_layer_terms(spec), alpha, ratios)


def score_config(config: Mapping, alpha: float = 0.0) -> float:
    """S(alpha) for a starter config dict (parsed via nsc.layers in adapter)."""
    return score_spec(spec_from_config(config), alpha)


def score_with_ratios(config: Mapping, alpha: float,
                      ratios: Sequence[float]) -> float:
    """S(alpha) with caller-supplied per-layer discount ratios.

    This is the primitive behind the M3 position-only control: pass
    ``ctxnsc.position_ratios(n_layer)`` so the discount depends only on the
    layer index (i+1)/L, matching nsc.position_example's weighting. Role B
    must use this function instead of reimplementing the discount.
    """
    return score_terms(per_layer_terms(spec_from_config(config)), alpha, ratios)


def scores_for_alphas(target, alphas: Iterable[float]) -> Dict[float, float]:
    """Scores for several alphas, computing terms and ratios only once.

    ``target`` may be an ArchitectureSpec or a starter config dict.
    """
    if isinstance(target, ArchitectureSpec):
        spec = target
    else:
        spec = spec_from_config(target)
    terms = per_layer_terms(spec)  # compute once, reuse for every alpha
    ratios = cumulative_ratios(terms)
    return {alpha: score_terms(terms, alpha, ratios) for alpha in alphas}
