#!/usr/bin/env python3
"""1,000-trial selection reference implementation (TA 2 / A5.5).

``select_trials_ext`` mirrors ``evaluate.select_trials`` line by line — same
``random.Random(seed)`` per call, same shuffle-then-stable-sort for scored
methods, same ``rng.sample`` for the uniform random baseline, same
``statistics.mean`` / ``pstdev`` and oracle — with the number of trials as a
parameter. The official harness's REPEATS=200 stays untouched; the main
protocol for every method (M1-M6 and random) is repeats=1000, and the 200
runs are exactly the first 200 draws of the same RNG stream (verified below).

Self-test:

    python3 tools/selection_ext.py --self-test

prints ``PARITY OK`` (aggregates identical to evaluate.select_trials on 20
random cases), ``PREFIX OK`` (the 1,000-trial run's first 200 best-PPL trials
equal the 200-trial run's trials, bitwise) and ``TRIALS OK``.
"""
import argparse
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import evaluate  # noqa: E402  (starter module; only its select_trials is compared)


def select_trials_ext(pool, scores, k, ppl, seed, repeats=1000,
                      return_trials=False):
    """Best revealed PPL after choosing k designs; randomize only score ties.

    Mirrors evaluate.select_trials with repeats as a parameter. scores=None
    gives uniform random selection without replacement. Variability measures
    random selection/tie-breaking, NOT training noise.
    """
    rng = random.Random(seed)
    best = []
    for _ in range(repeats):
        if scores is None:
            chosen = rng.sample(pool, k)
        else:
            order = list(pool)
            rng.shuffle(order)
            order.sort(key=lambda i: scores[i], reverse=True)
            chosen = order[:k]
        best.append(min(ppl[i] for i in chosen))
    oracle = min(ppl[i] for i in pool)
    result = {'mean_best_ppl': statistics.mean(best),
              'mean_regret': statistics.mean(best) - oracle,
              'sd_best_ppl': statistics.pstdev(best), 'trials': repeats}
    if return_trials:
        result['best_ppl_trials'] = best
    return result


def self_test() -> int:
    """PARITY / PREFIX / TRIALS: the three guarantees B's evaluator relies on."""
    rng = random.Random(0)
    failures = []
    # PARITY: 20 randomized cases, repeats=200, full aggregate dicts equal.
    for case in range(20):
        n = rng.randrange(6, 25)
        pool = rng.sample(range(n), rng.randrange(2, n + 1))
        scores = (None if rng.random() < 0.3 else
                  [round(rng.uniform(50, 500), 6) for _ in range(n)])
        k = rng.choice((1, 3))
        ppl = [round(rng.uniform(20, 80), 6) for _ in range(n)]
        seed = rng.randrange(0, 10 ** 6)
        mine = select_trials_ext(pool, scores, k, ppl, seed, repeats=200)
        theirs = evaluate.select_trials(pool, scores, k, ppl, seed)
        if mine != theirs:  # exact float equality, all keys
            failures.append(f"parity case {case}: {mine} != {theirs}")
    if failures:
        for line in failures[:5]:
            print(line)
        print("PARITY FAILED")
        return 1
    print("PARITY OK")

    # PREFIX: same seed, the first 200 trials of a 1,000-trial run equal the
    # 200-trial run bitwise (list comparison, not aggregates).
    n, pool = 30, list(range(30))
    scores = [round(random.Random(7).uniform(50, 500), 6) for _ in range(n)]
    ppl = [round(random.Random(8).uniform(20, 80), 6) for _ in range(n)]
    long_run = select_trials_ext(pool, scores, 3, ppl, 202627, repeats=1000,
                                 return_trials=True)
    short_run = select_trials_ext(pool, scores, 3, ppl, 202627, repeats=200,
                                  return_trials=True)
    if long_run["best_ppl_trials"][:200] != short_run["best_ppl_trials"]:
        print("PREFIX FAILED")
        return 1
    print("PREFIX OK")

    # TRIALS: the 1,000-trial run reports trials == 1000.
    if long_run["trials"] != 1000:
        print("TRIALS FAILED")
        return 1
    print("TRIALS OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="run the PARITY/PREFIX/TRIALS checks")
    args = parser.parse_args()
    if not args.self_test:
        parser.print_help()
        return 2
    return self_test()


if __name__ == "__main__":
    sys.exit(main())
