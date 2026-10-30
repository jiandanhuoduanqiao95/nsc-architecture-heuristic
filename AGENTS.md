# AGENTS.md — non-negotiable rules for any agent or member touching this repo

Owner map: `ctxnsc/ checks/ tests/ tools/` and `student_score.py` belong to
role A (changes go through A); `variants/`, `results/dev_grid*` and
`results/selection_1000.json` to B; `CONVENTIONS.md`, `freeze.*`, the final
`README.md` and the remote to C.

## Workflow rules

1. Before touching anything in `ctxnsc/`, run `python3 checks/run_checks.py`
   and confirm 18/18. Re-run it after every change; a change that breaks a
   check is a failed change.
2. Never modify `nsc.py`, `evaluate.py`, `check_starter.py`,
   `expected_development.json`, `data/*`, or `docs/starter_manifest.sha256`
   (byte-exact, CH01). The only editable starter file is `student_score.py`.
3. Never run `python3 evaluate.py --split final`. The final split is run
   once, by role B, only after C's `freeze` tag.
4. Never read `data/final_labels.json`'s content from your own code (byte
   hash checks by `check_starter.py`/CH01 are the only permitted touch).
5. Any change that makes a check pass must be accompanied by evidence that
   the check can fail — the mutation suite (`--mutations`, 7/7) is that
   evidence; extend checks, never delete mutations.
6. Commit at the end of every stage; `git status` must be clean.

## Hard constraints

1. Starter files above are read-only; only `student_score.py` may change.
2. No `--split final`; no label files inside scorers; no config-ID lookups.
3. Python 3.9+ standard library only — no numpy/pandas/scipy/pytest
   (CH15 enforces syntax + import whitelist).
4. No special case for `alpha == 0`; use `math.fsum` across layers; do not
   change `psi_mp`'s default `steps=512`.
5. Use `d_model`, never `d_embed` (they differ on 141/200 configs); never use
   `resources.total` as a projection-parameter count (it includes adaptive
   embeddings, up to 57.85× projection).
6. `ablation` always returns `nsc.original_nsc`.
7. The α→∞ limit is `ΣA + F_1` (first layer is never discounted, `c_1 = 0`),
   not `ΣA`.
8. Reorder direction rule is frozen: large FFN moved earlier ⇒ `S(α>0)`
   increases; α=0 comparisons use rel ≤ 1e-14, not bitwise.
9. Every "passing" modification must first prove the checks can fail
   (mutations).
10. Main selection protocol is 1,000 trials (`tools/selection_ext.py`); the
    harness's 200 are a prefix-consistency appendix only; `REPEATS` is
    untouchable.
11. M3 uses `ctxnsc.score_with_ratios` + `position_ratios`, same grid, same
    selection rule, same tie-break as M2.
12. Size-control reports the rule `same d_model; min(total)/max(total)>=0.90`
    and 180 dev pairs.
13. `freeze.json` must cover every analysis choice and pass CH18 (`--freeze`)
    before the final run.
14. The C3 normalization side effect is reported as its own table, never
    folded into the mechanism argument.
15. `docs/reproduction.md` carries every acceptance command with its real
    output; keep it current.

## Anti-patterns (each one has a catcher)

| # | Anti-pattern | Caught by |
|---|---|---|
| 1 | Editing the four starter files | CH01 |
| 2 | Running `--split final` early | process (this file + review) |
| 3 | Importing numpy/pytest/... | CH15 |
| 4 | Special-casing α=0 | MU1 / CH05 |
| 5 | `sum` instead of `fsum` | CH05 (1-ULP drift) |
| 6 | Writing `3*psi*h` instead of `3*h*psi` | CH04 |
| 7 | Dropping the `ψ(d,d)` output projection | MU3 / CH04 |
| 8 | Reading `d_embed` as the width | CH04 |
| 9 | `resources.total` as projection params | reorder schema / review |
| 10 | 0-based or current-layer-inclusive `c_l` | CH07 / MU2 |
| 11 | Asserting bitwise NSC equality across reorders | (it fails: non-associativity) use 1e-14 |
| 12 | Asserting the limit is `ΣA` | CH10 |
| 13 | Labels/IDs inside a scorer | CH14 |
| 14 | `ablation` returning our score | CH03 |
| 15 | Editing `expected_development.json` | CH01 |
| 16 | Raw-float tie handling (harness uses 12-sig-digit canonical) | review #5 |
| 17 | Reporting `scoring_seconds` as fair timing | docs review |
| 18 | Calling trial variance "training-seed uncertainty" | review #16 |
| 19 | Calling synthetic reorder gains "better prediction" | mechanism doc |
| 20 | Mixing `d_embed`/`total` scopes into the report | audit + review |
| 21 | Presenting 200 trials as the main protocol | review #8 |
| 22 | M3 on a different grid/rule than M2 | CH18 / review #13 |
| 23 | Omitting the C3 normalization table | review #14 |
