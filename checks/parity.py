"""The ONE shared comparator for harness payloads (used by CH03 and
``tools/compare_expected.py`` — no second implementation allowed).

Rules (plan v1.2, group decision D0-1):

* ``scoring_seconds`` and ``timing_note`` are ignored everywhere.
* Every other field must be bit-equal (same type or numeric-equal, with
  bool/int kept distinct).
* D0-1 exception, only when Python >= 3.11 (``sd_tolerance_allowed()``):
  ``selection[*].methods.random.sd_best_ppl`` may differ by <= 1 ULP
  (integer ULP distance via ``math.nextafter``); each differing field is
  reported with path, got, exp and the ULP distance. On Python <= 3.10 any
  difference in that field fails too.
* Post-freeze mode (ALPHA != 0): differences under ``$.ranking.student``,
  ``$.ranking.ablation``, ``$.selection[*].methods.student.*`` and
  ``$.selection[*].methods.ablation.*`` are the expected effect of the tuned
  scorer and are recorded; EVERY other difference (including the selection
  baselines random/eligible/oracle_ppl and the four baseline methods) fails.
"""
from __future__ import annotations

import math
import re
import sys

IGNORED_KEYS = ("scoring_seconds", "timing_note")
TOLERATED_SD_FIELD = re.compile(r"^\$\.selection\[\d+\]\.methods\.random\.sd_best_ppl$")
POST_FREEZE_EXPECTED_DIFF = re.compile(
    r"^\$\.(?:ranking\.(?:student|ablation)"
    r"|selection\[\d+\]\.methods\.(?:student|ablation))(?:\.|:|\s|$)")
D0_1_MAX_ULP = 1


def sd_tolerance_allowed() -> bool:
    """D0-1 applies only on Python >= 3.11 (statistics.pstdev change)."""
    return sys.version_info >= (3, 11)


def ulp_distance(expected: float, actual: float) -> float:
    """Integer ULP distance between two floats, counted via math.nextafter."""
    if expected == actual:
        return 0
    if not (math.isfinite(expected) and math.isfinite(actual)):
        return math.inf
    dist, x = 0, expected
    target, step = (actual, math.inf) if actual > expected else (actual, -math.inf)
    while dist <= 16:
        if x == target:
            return dist
        if dist == 16:
            break
        x = math.nextafter(x, step)
        dist += 1
    return math.inf


def compare_payloads(expected, actual, allow_d0_1=None, path="$"):
    """Exact field-by-field comparison with the D0-1 rule.

    Returns (violations, tolerated, n_sd_fields_checked). ``tolerated`` lists
    only fields that actually differ but fall inside the D0-1 allowance
    (ULP distance >= 1 and <= 1). ``allow_d0_1=None`` auto-detects from the
    interpreter version; ``True``/``False`` overrides (used by tests and
    ``--strict``, which passes False).
    """
    if allow_d0_1 is None:
        allow_d0_1 = sd_tolerance_allowed()
    violations, tolerated = [], []
    n_sd_checked = 0
    stack = [(path, expected, actual)]
    while stack:
        path, exp, act = stack.pop()
        if isinstance(exp, dict) and isinstance(act, dict):
            for key in sorted(set(exp) | set(act)):
                if key in IGNORED_KEYS:
                    continue
                child = f"{path}.{key}"
                if key not in exp:
                    violations.append(f"{child}: missing in expected")
                elif key not in act:
                    violations.append(f"{child}: missing in actual")
                else:
                    stack.append((child, exp[key], act[key]))
        elif isinstance(exp, list) and isinstance(act, list):
            if len(exp) != len(act):
                violations.append(f"{path}: list length {len(exp)} != {len(act)}")
            else:
                stack.extend((f"{path}[{i}]", e, a)
                             for i, (e, a) in enumerate(zip(exp, act)))
        else:
            if TOLERATED_SD_FIELD.match(path) and isinstance(exp, float) \
                    and isinstance(act, float):
                n_sd_checked += 1
                dist = ulp_distance(exp, act)
                if allow_d0_1 and dist <= D0_1_MAX_ULP:
                    if dist > 0:  # report real differences, not exact hits
                        tolerated.append(f"{path}: got {act!r} exp {exp!r} "
                                         f"(ULP={dist:g})")
                    continue
            same_type = type(exp) is type(act)
            numbers = isinstance(exp, (int, float)) and isinstance(act, (int, float))
            if exp != act or not (same_type or (numbers and not
                                                isinstance(exp, bool)
                                                and not isinstance(act, bool))):
                violations.append(f"{path}: expected {exp!r} vs actual {act!r}")
    return violations, tolerated, n_sd_checked


def post_freeze_violations(violations):
    """Violations that must be zero after the freeze (ALPHA != 0).

    Drops the expected student/ablation differences and keeps everything
    else: the four baseline methods, the selection baselines (random),
    eligible/oracle_ppl and every structural field.
    """
    return [v for v in violations if not POST_FREEZE_EXPECTED_DIFF.match(v)]
