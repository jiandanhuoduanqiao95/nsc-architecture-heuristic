#!/usr/bin/env python3
"""D0-1 diagnostic: three computation paths for one fixture number.

Reconstructs the exact trial list of ``selection[2].methods.random``
(budget 20M, k=1, pool of 65 dev architectures, seed 202627+20_000_000+1,
200 trials of ``rng.sample(pool, k)``) and evaluates ``sd_best_ppl`` three
ways:

1. ``statistics.pstdev``   — version-dependent (changed in CPython 3.11)
2. ``math.fsum`` float path — sqrt(fsum((x-mean)^2)/n)
3. exact ``Fraction`` path  — correctly rounded true value

Documented facts (docs/reproduction.md D0-1): paths 2 and 3 both give
11.825936547801547 = the fixture value on EVERY interpreter; path 1 matches
on Python <= 3.10 and is 1 ULP low on >= 3.11. Exit 0 iff the two
version-independent facts hold.
"""
import json
import math
import random
import statistics
import sys
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGET, K, FIXTURE = 20_000_000, 1, 11.825936547801547


def main():
    configs = json.loads((REPO / "data" / "architectures.json").read_text())
    resources = json.loads((REPO / "data" / "resources.json").read_text())
    splits = json.loads((REPO / "data" / "splits.json").read_text())
    labels = json.loads((REPO / "data" / "development_labels.json").read_text())
    keys = splits["development"]
    ppl = [labels[k]["valid_ppl"] for k in keys]
    total = [resources[k]["total"] for k in keys]
    pool = [i for i, size in enumerate(total) if size <= BUDGET]
    rng = random.Random(202627 + BUDGET + K)
    best = [min(ppl[i] for i in rng.sample(pool, K)) for _ in range(200)]
    n = len(best)

    v_pstdev = statistics.pstdev(best)
    mean_fsum = math.fsum(best) / n
    v_fsum = math.sqrt(math.fsum((x - mean_fsum) ** 2 for x in best) / n)
    mean_exact = sum(map(Fraction, best)) / n
    ss_exact = sum((Fraction(x) - mean_exact) ** 2 for x in best)
    v_exact = math.sqrt(ss_exact / n)

    print(f"trial list: 200 samples, pool={len(pool)}, "
          f"seed={202627 + BUDGET + K}")
    print(f"1. statistics.pstdev      : {v_pstdev!r}")
    print(f"2. math.fsum float path   : {v_fsum!r}")
    print(f"3. exact Fraction path    : {v_exact!r}")
    print(f"fixture sd_best_ppl       : {FIXTURE!r}")
    print(f"python                    : {sys.version.split()[0]}")
    exact_ok = (v_fsum == FIXTURE and v_exact == FIXTURE)
    print(f"fsum == exact == fixture  : {exact_ok}")
    print(f"pstdev on this python     : "
          f"{'matches fixture (<=3.10 behaviour)' if v_pstdev == FIXTURE else f'{abs(FIXTURE - v_pstdev) / math.ulp(FIXTURE):.0f} ULP off the fixture (D0-1, >=3.11 behaviour)'}")
    return 0 if exact_ok else 1


if __name__ == "__main__":
    sys.exit(main())
