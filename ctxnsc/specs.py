"""Architecture specifications independent of the starter's config schema.

A spec is a plain, validated, frozen description of an architecture: per-layer
(hidden width, head count, FFN width) plus the fixed init std. The core math
modules (terms/prefix/score/breakdown) consume specs only, so they can be unit
tested without the archive. ``ctxnsc.adapter`` is the single place that turns
starter config dicts into specs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class LayerSpec:
    """One transformer layer: hidden width, head count, FFN width."""

    hidden: int
    heads: int
    ffn: int


@dataclass(frozen=True)
class ArchitectureSpec:
    """An ordered tuple of layers plus the init standard deviation.

    ``name`` is an optional debug label only; it must never influence scores.
    """

    layers: Tuple[LayerSpec, ...]
    init_std: float = 0.02
    name: str = ""

    def __post_init__(self):
        if not self.layers:
            raise ValueError("architecture must have at least one layer")
        for layer in self.layers:
            if layer.hidden <= 0 or layer.heads <= 0 or layer.ffn <= 0:
                raise ValueError("layer dimensions must be positive")
            if layer.hidden % layer.heads:
                raise ValueError("hidden width must be divisible by head count")
        if not (self.init_std > 0):
            raise ValueError("init_std must be positive")

    def __len__(self) -> int:
        return len(self.layers)
