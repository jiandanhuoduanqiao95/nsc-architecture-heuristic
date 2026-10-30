"""Per-layer NSC terms with the starter's exact matrix grouping.

The expressions below are a hard requirement, not a style choice: they mirror
``nsc.layer_capacities``' left-associative ``((3*h*psi + psi) + 2*psi)``
evaluation order so that ``attn + ffn`` is bit-identical to the starter's
per-layer capacity (checked elementwise by CH04). Do not reorder factors
(``3 * psi * h`` differs in the last ULP) and do not merge the two psi calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .mp import psi
from .specs import ArchitectureSpec, LayerSpec


@dataclass(frozen=True)
class LayerTerms:
    """Attention capacity A_l and FFN capacity F_l of one layer."""

    attn: float  # A_l = 3*h*psi(d, d//h) + psi(d, d)
    ffn: float   # F_l = 2*psi(d, f)


def layer_terms(layer: LayerSpec, sigma: float = 0.02) -> LayerTerms:
    """A_l and F_l for one layer, mirroring nsc.layer_capacities exactly."""
    d, h, f = layer.hidden, layer.heads, layer.ffn
    attn = 3 * h * psi(d, d // h, sigma) + psi(d, d, sigma)
    ffn = 2 * psi(d, f, sigma)
    return LayerTerms(attn, ffn)


def per_layer_terms(spec: ArchitectureSpec) -> List[LayerTerms]:
    """Terms for every layer of a spec, in layer order."""
    return [layer_terms(layer, spec.init_std) for layer in spec.layers]
