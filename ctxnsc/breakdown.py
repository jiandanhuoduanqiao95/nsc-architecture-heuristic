"""Per-layer breakdown of S(alpha): ratios, factors and contributions.

Used by ``tools/show_breakdown.py`` (hand-checked worked example), by CH16
(breakdown consistency) and by role B's C3 normalization study — when only a
later layer's FFN changes, every layer's ratio and factor moves because the
denominator S0 changes, and this module displays that layer by layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from .adapter import spec_from_config
from .prefix import cumulative_ratios, discount_factors
from .terms import LayerTerms, per_layer_terms


@dataclass(frozen=True)
class BreakdownItem:
    """One layer's A_l, F_l, ratio c_l, factor 1/(1+alpha*c_l) and contribution."""

    layer: int           # 1-based
    attn: float          # A_l
    ffn: float           # F_l
    ratio: float         # c_l
    factor: float        # 1 / (1 + alpha * c_l)
    contribution: float  # attn + ffn * factor


@dataclass(frozen=True)
class Breakdown:
    """Full per-layer decomposition plus the headline aggregates."""

    items: Tuple[BreakdownItem, ...]
    s0: float            # undiscounted sum of (A_l + F_l)
    total: float         # S(alpha) = fsum(contribution)
    sum_attn: float      # fsum(A_l)
    first_ffn: float     # F_1 (the layer never discounted, since c_1 = 0)


def breakdown(terms: Sequence[LayerTerms], alpha: float) -> Breakdown:
    """Decompose S(alpha) layer by layer for precomputed terms."""
    ratios = cumulative_ratios(terms)
    factors = discount_factors(ratios, alpha)
    items = tuple(
        BreakdownItem(layer=i + 1, attn=t.attn, ffn=t.ffn, ratio=c,
                      factor=f, contribution=t.attn + t.ffn * f)
        for i, (t, c, f) in enumerate(zip(terms, ratios, factors)))
    return Breakdown(items=items,
                     s0=math.fsum(t.attn + t.ffn for t in terms),
                     total=math.fsum(item.contribution for item in items),
                     sum_attn=math.fsum(t.attn for t in terms),
                     first_ffn=terms[0].ffn)


def breakdown_config(config: Mapping, alpha: float) -> Breakdown:
    """Decompose S(alpha) for a starter config dict."""
    return breakdown(per_layer_terms(spec_from_config(config)), alpha)
