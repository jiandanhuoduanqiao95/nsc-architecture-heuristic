"""The single schema boundary between starter configs and the core library.

Everything below this module works on ArchitectureSpec; everything above it
(starter harness, archive JSON) speaks config dicts. Parsing is delegated to
``nsc.layers`` so schema validation, int/list n_head/d_inner handling and the
``d_model % h`` check stay bit-compatible with the official code. ``d_model``
is the scoring width — never ``d_embed`` (they differ in 141/200 archive
configs). ``weight_init_std`` must be present and equal 0.02: the archived
panel's fixed convention, and the sigma our psi calls must use.
"""
from __future__ import annotations

from typing import Any, Mapping

import nsc

from .specs import ArchitectureSpec, LayerSpec


def spec_from_config(config: Mapping[str, Any]) -> ArchitectureSpec:
    """Parse a starter config dict into an ArchitectureSpec (no copying)."""
    d, heads, inner = nsc.layers(config)  # the one official parsing entry point
    sigma = float(config["weight_init_std"])  # missing key raises: no silent default
    if sigma != 0.02:
        raise ValueError(f"unexpected weight_init_std: {sigma}")
    layers = tuple(LayerSpec(d, h, f) for h, f in zip(heads, inner))
    return ArchitectureSpec(layers=layers, init_std=sigma,
                            name=str(config.get("_id", "")))
