"""Thin, mandatory wrapper around the starter's Marchenko-Pastur integral.

The starter's ``nsc.psi_mp`` is the only allowed source of psi values: we do
not reimplement the integral, change the default 512 Simpson steps, or add our
own cache (``psi_mp`` is already ``lru_cache``d). The wrapper only asserts the
one property the scoring math relies on (strict positivity for positive
integer dimensions at sigma > 0) so that a silent zero/negative would fail
loudly instead of corrupting a score.
"""
from nsc import psi_mp


def psi(m: int, n: int, sigma: float = 0.02) -> float:
    """MP capacity of a (m, n) iid Gaussian matrix at init std ``sigma``.

    Raises ValueError when the starter integral does not return a positive
    value (which would indicate an invalid dimension or sigma).
    """
    value = psi_mp(m, n, sigma)  # keep the starter's default steps=512
    if not (value > 0.0):
        raise ValueError(f"psi must be positive, got {value} for ({m}, {n})")
    return value
