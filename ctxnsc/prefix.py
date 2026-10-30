"""Strict-prefix ratios, discount factors and the position-only hook.

Conventions (group C1/C2, frozen): the cumulative capacity C_<l contains only
layers i < l (C_<1 = 0, the current layer's own terms are excluded) and the
denominator S0 is the architecture's own sum over all layers. No clamping, no
epsilon: the first ratio is exactly 0.0 because it is math.fsum([]) / S0.
"""
from __future__ import annotations

import math
from typing import List, Sequence

from .terms import LayerTerms


def s0_from_terms(terms: Sequence[LayerTerms]) -> float:
    """S0 = sum over layers of (A_l + F_l), accumulated with math.fsum."""
    return math.fsum(item.attn + item.ffn for item in terms)


def cumulative_ratios(terms: Sequence[LayerTerms]) -> List[float]:
    """c_l = C_<l / S0 with strict prefixes (ratios[0] is exactly 0.0)."""
    s0 = s0_from_terms(terms)
    if not (s0 > 0.0) or not math.isfinite(s0):
        raise ValueError("S0 must be finite and positive")
    ratios, prefix = [], []
    for item in terms:
        ratios.append(math.fsum(prefix) / s0)  # C_<l / S0, strict prefix
        prefix.append(item.attn + item.ffn)
    return ratios


def discount_factors(ratios: Sequence[float], alpha: float) -> List[float]:
    """1 / (1 + alpha * c_l); no special case for alpha == 0.

    alpha = 0 flows through the same arithmetic (1.0 + 0.0*c == 1.0, so every
    factor is exactly 1.0 and the score falls back to S0 bit-for-bit).
    """
    if not math.isfinite(alpha) or alpha < 0.0:
        raise ValueError("alpha must be finite and non-negative")
    return [1.0 / (1.0 + alpha * c) for c in ratios]


def position_ratios(length: int) -> List[float]:
    """Position-only weights (i+1)/length for the M3 attribution control.

    Same (i+1)/L weighting as ``nsc.position_example``; role B plugs these into
    ``ctxnsc.score_with_ratios`` to obtain M3. Not used by our own score.
    """
    if length < 1:
        raise ValueError("length must be positive")
    return [(i + 1) / length for i in range(length)]
