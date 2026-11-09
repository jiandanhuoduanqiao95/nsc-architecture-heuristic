# CONVENTIONS — draft for role C to sign (CS5491 G045)

> **Status: DRAFT — C to sign.** Prepared by role A from the execution
> manual v1.2 (Table 2, C1–C8), the plan §1.4 accounting table and
> `docs/mechanism.md` §2. Role C copies this into the repository-root
> `CONVENTIONS.md` after the group meeting confirms it; from the freeze tag
> on, changes need group consent and a dated note in `freeze.md`.

## C1 — preceding (cumulative) capacity C_<l

`C_<l = Σ_{i<l} (A_i + F_i)`, strict prefix: the current layer's `A_l` and
`F_l` are excluded and `C_<1 = 0`. `A_i` = per-head Q/K/V
(`3·h_i·ψ(d, d//h_i)`) + the attention output projection (`ψ(d, d)`);
`F_i` = both FFN projections (`2·ψ(d, f_i)`), discounted as one block.

## C2 — normalizer

`c_l = C_<l / S0` with `S0 = Σ_{i=1..L} (A_i + F_i)` of **the same
architecture**. No epsilon, no clamp, no panel-level constant.

| quantity | includes | excludes |
|---|---|---|
| `A_l` | `3·h_l·ψ(d, d//h_l)` + `ψ(d, d)` | bias, LayerNorm, dropout, softmax |
| `F_l` | `2·ψ(d, f_l)` | bias, activation |
| `C_<l` | layers `i < l` only; `C_<1 = 0` | current layer; embeddings; vocab head |
| `S0` | all layers `1..L` | embeddings, bias, norms, vocab head |
| `c_l` | `C_<l / S0`, own `S0` | constants, panel means, clamps, epsilons |

ψ is the starter's `nsc.psi_mp` (σ = 0.02, 512 Simpson steps, unchanged);
widths come from `d_model` via `nsc.layers` — never `d_embed`.

## C3 — normalization side effect (TA 2, mandatory separate table)

Changing only a later layer moves every earlier layer's ratio because the
denominator changes: `Δc_l = C_<l · (1/S0′ − 1/S0)`. Reported as its own
table (`tools/normalization_probe.py` → `results/normalization_probe.csv`)
and written up as a limitation — a structural side effect of normalizing by
total capacity, not evidence for the mechanism.

## C4 — α / β selection rule and tie-break (TA 2)

On the development split only: scores → `evaluate.canonical` (12
significant digits) → average-rank Spearman ρ against negative dev PPL →
largest ρ wins; if two grid values' ρ are equal at 12 significant digits
the **smaller** α (β) wins and `tie_break_used` is recorded. Grid
`{0, 0.25, 0.5, 1, 2}` for both α (M2) and β (M3); all 5 rows of both grids
are kept (`results/dev_grid_cumulative.json`, `results/dev_grid_position.json`,
produced by `tools/select_alpha.py`).

## C5 — feasible pools and tie-handling (TA 2)

Every method (M1–M6, ablation) and the random baseline use the same pool
`reported total <= cap` and the harness tie-handling (canonical scores;
shuffle with `Random(202627 + cap + k)`, then stable sort descending).

## C6 — ranking metrics

Spearman ρ (average ranks), Kendall τ-b and tie counts, all against
**negative** PPL, on all pairs and on the size-controlled pairs
(`same d_model; min(total)/max(total) >= 0.90` — 180 development pairs).

## C7 — random trials (TA 1/2)

Main protocol: **1,000** fixed-seed trials for every method and the random
baseline (`tools/selection_ext.py: select_trials_ext(..., repeats=1000)`).
The harness's 200 trials are the bitwise prefix of the same RNG stream and
appear only as an appendix consistency check; `evaluate.py`'s `REPEATS` is
never edited. Trial variance measures selection/tie-breaking randomness,
not training-seed uncertainty (one outcome per architecture).

## C8 — reproduction

Python version, seeds and exact commands are in `README.md` /
`docs/reproduction.md`; one command per result; `--split final` runs once,
after the `freeze` tag.

## Additional conventions adopted during role A's work (need sign-off)

| id | convention | evidence |
|---|---|---|
| D0-1 | On Python ≥ 3.11 the fixture's `selection[*].methods.random.sd_best_ppl` may differ by ≤ 1 ULP (CPython `statistics.pstdev` rounding change); every other field is bit-exact; ≤ 3.10 is bit-exact everywhere | `docs/reproduction.md` §5, `tools/d0_1_diagnose.py`, CH03 |
| C3-tol | the C3 identity is verified in the cross-multiplied form `c_l·S0 == C_<l` (bound 4·ulp); the literal factored form is not float64-achievable at 1e-15 | `docs/mechanism.md` §9 |
| CH11 | the reorder sweep uses the structures of all 200 archived configurations (dev 4,961 + final 4,884 = 9,845 pairs) and reads no label file | `docs/reproduction.md` §9 |

## Sign-off

| role | name | date | signature |
|---|---|---|---|
| C (owner) |  |  |  |
| A |  |  |  |
| B |  |  |  |
