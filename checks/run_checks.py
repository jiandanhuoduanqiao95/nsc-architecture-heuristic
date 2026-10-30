#!/usr/bin/env python3
"""CLI for the 18-check suite and the 7-mutation proof (A3.1).

    python3 checks/run_checks.py                  # all checks -> exit 0/1,
                                                  # writes results/checks.json
    python3 checks/run_checks.py --only CH04,CH05
    python3 checks/run_checks.py --json out.json
    python3 checks/run_checks.py --mutations      # 7 mutations must be caught
    python3 checks/run_checks.py --only CH18 --dry-run   # fixture mode (handoff)
    python3 checks/run_checks.py --only CH18 --freeze    # strict freeze mode

CH18 mode: ``--freeze`` forces strict validation of the real freeze.json;
``--dry-run`` forces the fixture mode; with neither, strict is used when
freeze.json exists and dry-run otherwise, so 18/18 works before the freeze
and becomes strict afterwards.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from checks import checks as checks_mod  # noqa: E402
from checks import mutations  # noqa: E402

DEFAULT_JSON = REPO / "results" / "checks.json"


def git_commit() -> str:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(REPO), capture_output=True, text=True,
                              timeout=10)
        return proc.stdout.strip() if proc.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def write_json(path: Path, results, freeze_mode: str) -> None:
    payload = {
        "python_version": sys.version,
        "git_commit": git_commit(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "freeze_mode": freeze_mode,
        "checks": [r.as_dict() for r in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="",
                        help="comma-separated check ids, e.g. CH04,CH05")
    parser.add_argument("--json", type=Path, default=None,
                        help="where to write the result JSON "
                             "(default: results/checks.json on full runs)")
    parser.add_argument("--mutations", action="store_true",
                        help="run the 7-mutation proof instead of the suite")
    parser.add_argument("--dry-run", action="store_true",
                        help="CH18: validate fixtures instead of freeze.json")
    parser.add_argument("--freeze", action="store_true",
                        help="CH18: strict mode against the real freeze.json")
    args = parser.parse_args()

    if args.mutations:
        return mutations.run_mutations()

    only = {token.strip() for token in args.only.split(",") if token.strip()}
    if args.freeze:
        freeze_mode = "strict"
    elif args.dry_run:
        freeze_mode = "dry-run"
    else:
        freeze_mode = None  # decide per presence of freeze.json

    results = checks_mod.run_checks(only=only or None, freeze_mode=freeze_mode)
    # Accounting invariant: n_failed counts failing CASES and can never leave
    # [0, n_cases]. A violation here is a bug in the check itself -> exit 1.
    accounting_errors = [f"{r.id}: n_failed={r.n_failed} outside "
                         f"[0, n_cases={r.n_cases}]"
                         for r in results if not 0 <= r.n_failed <= r.n_cases]
    if accounting_errors:
        for line in accounting_errors:
            print("ACCOUNTING VIOLATION:", line)
        print("CHECK ACCOUNTING BROKEN")
        return 1
    # effective mode for the JSON record
    effective = ("strict" if args.freeze else "dry-run" if args.dry_run else
                 ("strict" if (REPO / "freeze.json").exists() else "dry-run"))
    for r in results:
        print(f"{r.id} {r.name:<22s} {'PASS' if r.passed else 'FAIL'} "
              f"({r.n_cases - r.n_failed}/{r.n_cases}, {r.tolerance})")
        for failure in r.failures[:5]:
            print("    ", failure)
        if len(r.failures) > 5:
            print(f"     ... {len(r.failures) - 5} more failures")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} checks passed")
    # Only full runs write the default record; --only runs would otherwise
    # clobber results/checks.json with a partial one (explicit --json wins).
    if args.json is not None or not only:
        out = args.json if args.json is not None else DEFAULT_JSON
        write_json(out, results, effective)
        print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    elif only:
        print("(--only run: results/checks.json left untouched)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
