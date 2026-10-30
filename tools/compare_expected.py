#!/usr/bin/env python3
"""Field-by-field parity check between a harness result JSON and the fixture.

Usage:
    python3 tools/compare_expected.py <actual.json> <expected.json> [--strict]

Shares ONE comparator with check CH03 (``checks/parity.py`` — no second
implementation). Default mode applies the group-approved D0-1 rule:
on Python >= 3.11 the fixture's random-baseline ``sd_best_ppl`` may differ
by <= 1 ULP from the harness output (documented CPython rounding change);
every other field must be bit-equal. On Python <= 3.10, and always under
``--strict``, any difference fails.

Exit codes: 0 = parity (with D0-1 allowances printed); 1 = any violation.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from checks.parity import IGNORED_KEYS, compare_payloads, sd_tolerance_allowed  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    actual_path, expected_path = (Path(args[0]), Path(args[1]))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = json.loads(actual_path.read_text(encoding="utf-8"))
    violations, tolerated, n_sd_checked = compare_payloads(
        expected, actual, allow_d0_1=False if strict else None)
    mode = "strict" if strict else f"default (D0-1 {'on' if sd_tolerance_allowed() else 'n/a on this Python'})"
    if violations:
        print(f"PARITY FAILED ({len(violations)} violations); ignored keys: "
              f"{', '.join(IGNORED_KEYS)}; mode: {mode}")
        for line in violations[:20]:
            print("  " + line)
        return 1
    if tolerated:
        print(f"PARITY OK (D0-1: {len(tolerated)} tolerated ULP at "
              f"{tolerated[0].split(':')[0]}; {n_sd_checked} random-sd fields "
              f"checked; mode: {mode})")
        return 0
    print(f"PARITY OK (mode: {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
