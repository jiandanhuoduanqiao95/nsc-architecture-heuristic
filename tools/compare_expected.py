#!/usr/bin/env python3
"""Field-by-field parity check between a harness result JSON and the fixture.

Usage:
    python3 tools/compare_expected.py <actual.json> <expected.json>
    python3 tools/compare_expected.py results/dev_baseline.json expected_development.json

Compares the two files recursively and requires exact equality of every field
(floats compared bitwise via ==, dicts by key set, lists by order), ignoring
only the timing keys ``scoring_seconds`` and ``timing_note`` that the official
``expected_development.json`` omits. Exits 1 and prints ``path: expected vs
actual`` for the first differences; prints ``PARITY OK`` otherwise.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # allow running from tools/ without installing

IGNORED_KEYS = ("scoring_seconds", "timing_note")


def diff(path, expected, actual, out):
    """Append human-readable difference lines for (expected, actual) at path."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key in IGNORED_KEYS:
                continue
            if key not in expected:
                out.append(f"{path}.{key}: <missing in expected> vs {actual[key]!r}")
            elif key not in actual:
                out.append(f"{path}.{key}: {expected[key]!r} vs <missing in actual>")
            else:
                diff(f"{path}.{key}", expected[key], actual[key], out)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path}: list length {len(expected)} vs {len(actual)}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                diff(f"{path}[{i}]", e, a, out)
    elif expected != actual or type(expected) is not type(actual):
        out.append(f"{path}: {expected!r} vs {actual!r}")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    actual_path, expected_path = (Path(sys.argv[1]), Path(sys.argv[2]))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = json.loads(actual_path.read_text(encoding="utf-8"))
    out = []
    diff("$", expected, actual, out)
    if out:
        print(f"PARITY FAILED ({len(out)} differences); ignored keys: "
              f"{', '.join(IGNORED_KEYS)}")
        for line in out[:20]:
            print("  " + line)
        return 1
    print(f"PARITY OK (ignored keys: {', '.join(IGNORED_KEYS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
