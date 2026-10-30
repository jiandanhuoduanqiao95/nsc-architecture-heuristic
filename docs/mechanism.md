# Mechanism: context-discounted NSC (report material, role A draft)

> Source for the report's "method" and "controlled checks" sections. Every
> number below is script-generated and reproducible: `results/`
> (`weighting_diagnostic.csv`, `normalization_probe.csv`, `reorder_pairs.csv`,
> `data_audit.csv`) and `checks/run_checks.py`.

## 1. Statement

Within the residual stream, the more context has already accumulated, the
smaller the **marginal** capacity an additional FFN block contributes. We use
the architecture's own normalized preceding capacity `c_l` as the proxy for
"context already accumulated" and discount each FFN term by
`1/(1 + α·c_l)`:

```
A_l = 3·h_l·ψ(d, d//h_l) + ψ(d, d)          # attention (per-head QKV + output proj)
F_l = 2·ψ(d, f_l)                            # the two FFN projections, discounted as a block
S0 = Σ_l (A_l + F_l)                         # original NSC
c_l = C_<l / S0,  C_<l = Σ_{i<l} (A_i + F_i) # strict prefix, C_<1 = 0
S(α) = Σ_l [ A_l + F_l / (1 + α·c_l) ]
```

## 2. Exact accounting (TA 1: "define exactly which baseline terms enter …")

| Quantity | Included | Explicitly excluded |
|---|---|---|
| `A_l` | `3·h_l·ψ(d, d//h_l)` (per-head Q/K/V) + `ψ(d, d)` (attention output projection) | bias, LayerNorm, dropout, softmax |
| `F_l` | `2·ψ(d, f_l)` (both FFN projections, discounted as one block) | bias, activation |
| `C_<l` | only layers `i < l`; `C_<1 = 0` | the current layer's `A_l`/`F_l`; embeddings; vocab head |
| `S0` | all layers `i = 1..L` | embeddings, bias, norms, vocab head (same scope as official §2.1) |
| `c_l` | `C_<l / S0`; the denominator is the architecture's **own** S0 | fixed constants, panel means, batch statistics, clamps, epsilons |

The per-layer expressions mirror `nsc.layer_capacities`'s
`((3·h·ψ + ψ) + 2·ψ)` associativity exactly, cross-layer sums use
`math.fsum`; CH04 verifies the identity elementwise (bitwise, 200/200) and
`ψ` comes only from the starter's `psi_mp` (sigma 0.02, 512 steps).

## 3. Assumptions

NSC's additive per-matrix capacity is preserved; the discount applies to FFN
terms only (attention terms carry the recurrence of the graph and stay
undiscounted); the init std stays at the archived `s = 0.02` and the matrix
grouping is unchanged (TA 1's "preserve the starter's matrix grouping").

## 4. Falsifiable predictions

- **Reorder direction**: moving the larger FFN earlier strictly increases
  `S(α>0)` (direction lemma: `ΔS = [F(f_j) − F(f_i)]·[1/(1+αc_i) − 1/(1+αc_j)] > 0`
  since `F` is increasing in `f` and `c_i < c_j`). Verified on 9,845 synthetic
  layer pairs, 0 violations (CH11); the official toy pair gives
  +2.354909500822373 at α=0.5.
- **Zero strength**: α=0 recovers NSC bit-for-bit (CH05, 200/200) — the
  ablation removes exactly our mechanism.
- **Attribution**: M2 (cumulative capacity) vs M3 (layer index only) can be
  separated *in principle*; in practice see item 8.

## 5. Limit behavior

`c_1 = 0` exactly (strict prefix), so the first layer's factor is 1 for every
α and `lim_{α→∞} S(α) = Σ_l A_l + F_1` — **not** the attention-only sum ΣA.
(The execution manual v1.1 stated the wrong limit; v1.2 corrected it; do not
"fix" the formula to match the old sentence.) CH10 verifies at α=1e12 with
rel ≤ 1e-9 on all 200 configs, and asserts the limit is *not* ΣA.

## 6. Effect sizes (label-free diagnostics, dev split unless stated)

| Diagnostic | Value | Source |
|---|---|---|
| `S(2)/S0` | 0.61719 / 0.71833 / 0.89939 (min/med/max) | `results/weighting_summary.json` |
| `Spearman(S(α), S0)`, α = .25/.5/1/2 | 0.99945 / 0.99864 / 0.99760 / 0.99574 | `results/weighting_summary.json` (`per_alpha`) |
| `Pearson(M2, M3)`, α = .25/.5/1/2 | 0.99998 / 0.99995 / 0.99988 / 0.99974 | `results/weighting_summary.json` (`per_alpha`) |
| `Pearson(c_l, (l+1)/L)` per config (panel 200) | min 0.98673, median 0.99865, max 1.00000 | `results/weighting_summary.json` |
| `max_l |c_l − (l+1)/L|` (panel 200) | median 0.14122, max 0.60393; 71/100 dev configs > 0.10 | `results/weighting_summary.json` |
| `Pearson(S(2)/S0, n_layer)` | -0.469 (deeper models are discounted more) | `results/weighting_summary.json` |

## 7. Honest reading of item 6

Our mechanism is a **small perturbation of the NSC ordering** (ρ(S(α), S0) ≥
0.9957 even at α=2) because S0 spans two orders of magnitude across the
panel. Sensitivity to the graph (reorderings) is **not** predictive validity.
M2 and M3 are nearly collinear (r ≥ 0.9997), so the attribution test has
very low statistical power; the report must state this as a limitation and
analyze the most-different subgroups (`L=2` configs and configs with large
`max_l |c_l − (l+1)/L|`).

## 8. M2 vs M3 matched comparison (TA 1/2 core demand)

Same 5-value grid `{0, 0.25, 0.5, 1, 2}`, same canonicalization (12
significant digits), same selection rule (max dev ρ), same tie-break
(smaller α/β wins, `tie_break_used` recorded). Role B runs
`tools/select_alpha.py --method cumulative` and `--method position`, keeps
both `results/dev_grid_*.json` (5 rows each), and reports α*, β* and whether
β* hit a boundary or a tie. Role C freezes both into `freeze.json`; CH18
re-derives the argmax and rejects any drift. M4 (the starter's
`position_example`) is retained untouched alongside M3.

## 9. Normalization side effect (TA 2 / C3, mandatory separate table)

When only the last layer's FFN width changes (×0.5 / ×1.25 / ×2.0 on three
deterministic dev configs), **every** earlier layer's ratio and factor moves,
because the denominator S0 changes:

```
Δc_l = C_<l · (1/S0' − 1/S0)      (verified per row; see tolerance note)
```

Measured (`results/normalization_probe.csv`, 60 rows; aggregates in `results/normalization_summary.json`): untouched-layer
max |Δfactor| = 6.775e-03, max |Δcontribution| = 3.734 — i.e. "only changing
a later layer" moves earlier discounts materially. *Tolerance note:* the
identity is verified in the algebraically identical cross-multiplied form
`c_l·S0 == C_<l` with a 4·ulp bound (worst observed rel 1.37e-16); the literal
factored form amplifies the rounding of `(1/S0' − 1/S0)` when S0' ≈ S0
(worst observed 2.67e-14), so a 1e-15 rel tolerance on the literal form is
not achievable in float64 by any implementation. This is a **structural side
effect of normalizing by total capacity, not evidence for the graph
mechanism** — the report must keep it as a limitation, never cite it as
predictive support.

## 10. 1,000 trials vs training-seed uncertainty (TA 1/2 wording)

The 1,000 fixed-seed random-selection trials (`tools/selection_ext.py`,
same pools, same seed scheme, same tie-handling for every method; the
harness's 200 are the bitwise prefix of the same RNG stream) measure
**selection and tie-breaking randomness only**. The archive has exactly one
recorded outcome per architecture — no seeds, no training tokens, no hardware
variance — so **training-seed uncertainty cannot be estimated from this
panel**. The two statements must appear separately in the report; do not
describe the trial variance as training noise.

## 11. Reproduction vs contribution

Reproduced: NSC scoring and its anchors, the positional teaching example,
resource arithmetic, the harness protocol (all bitwise against
`expected_development.json` up to the documented pstdev ULP artifact,
`docs/reproduction.md` D0-1). Ours: the strict-prefix capacity discount,
its spec-only implementation (`ctxnsc/`), the 18-check/7-mutation
verification rig, the label-free diagnostics, the reorder study, and the
matched M3/C3/1,000-trial tooling.
