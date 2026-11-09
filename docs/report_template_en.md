# Report template (English primary) — 4-page skeleton for role C

> **Language rule.** The submitted report is this English document, compiled
> to **PDF** (Times New Roman 12 pt, 2.5 cm margins, A4, single spacing,
> 4 pages excluding references). Do not submit the Chinese translation; the
> English PDF is the primary. Any Chinese working copy lives under `docs/zh/`
> and is a non-submitted reference.
>
> **Numbers.** Every number below is quoted from `docs/report_pack.md` — the
> bracketed ids ([S5], [P3], …) refer to that file's *Sources* table, which
> `python3 tools/make_report_pack.py --check` proves current. Do not
> introduce numbers from anywhere else; if an artifact changes, re-render the
> pack and re-check the ids. `[[B: …]]` slots are role B's pending results.

Page budget (≈ 4.0 pages; references excluded, three inline figures ≈ 0.8
pages included in the section budgets):

| section | words | pages |
|---|---:|---|
| 1 Motivation and problem | ≈ 140 | 0.3 |
| 2 Method | ≈ 430 + table | 1.0 |
| 3 Controlled checks | ≈ 230 | 0.45 |
| 4 Effect sizes | ≈ 130 + table | 0.4 |
| 5 C3 normalization side effect | ≈ 110 | 0.25 |
| 6 Results (B's slots) | ≈ 450 + tables | 0.9 |
| 7 Limitations | ≈ 120 | 0.25 |
| figures (3, inline in §§3, 4, 6) | — | 0.45 |
| **total** | **≈ 1,610** | **≈ 4.0** |

---

## 1. Motivation and problem (~140 words)

Draft: Neural Spectral Capacity (NSC) estimates a network's capacity from its
specification alone by summing Marchenko–Pastur matrix capacities, and is
blind to computation-graph structure: permuting FFN widths across layers
leaves NSC unchanged, although a later FFN block reads a residual stream that
earlier blocks have already populated. Our hypothesis: capacity that
accumulates before layer l dilutes the marginal value of that layer's FFN, so
we discount FFN terms by the architecture's own preceding-capacity share and
ask two independent questions — does the change distinguish graphs, and does
it improve ranking or fixed-budget selection of trained architectures?
Sensitivity is not predictive validity, and a careful negative result is a
valid outcome.

## 2. Method (~430 words + formula block + accounting table)

Draft: keep the starter's NSC conventions (per-head Q/K/V, attention output
projection, both FFN projections, init std 0.02, ψ from the starter's MP
integral) and discount each FFN term by the strict-prefix share
c_l = C_<l / S0:

```
A_l = 3·h_l·ψ(d, d//h_l) + ψ(d, d)      F_l = 2·ψ(d, f_l)
S0  = Σ_l (A_l + F_l)                   C_<l = Σ_{i<l} (A_i + F_i),  C_<1 = 0
c_l = C_<l / S0                         S(α) = Σ_l [ A_l + F_l / (1 + α·c_l) ]
```

Include the C1/C2 accounting table from `docs/report_pack.md` §2 (includes /
excludes per quantity: no bias, norm, embeddings or vocabulary head in the
score; c_l uses the architecture's own S0; no clamps or epsilons).

State the three structural facts, each with its check: the zero-strength
ablation is exact — S(0) equals `original_nsc` bit-for-bit on every archived
configuration with no special-case branch [S1]; the per-layer decomposition
matches the starter elementwise and bitwise [S2]; and the limit is
lim_(α→∞) S(α) = ΣA + F_1, not the attention-only sum, because c_1 = 0 —
checked at α = 10^12 [P1] with worst relative error 2.36e-11 [S4] on all
configurations [S3].

State the protocol: α and β are chosen on the development split only, over
the grid [P2], by the frozen rule (canonical 12-significant-digit scores,
max average-rank Spearman ρ against negative PPL, ties → smaller value);
the matched position-only control M3 discounts by the layer index alone.

## 3. Controlled checks (~230 words)

Draft: the official toy pair (d = 128 [S5], FFN [256, 512] vs [512, 256])
has identical NSC [S8], identical projection parameters [S9] and MACs [S10]
in both orders, while S(α = 0.5) separates the orders [S12] vs [S13]
(Δ = +2.354910 [S14]) — the direction lemma (moving the larger FFN earlier
strictly raises S(α)) holds on every differing layer pair across all
archived structures, 9,845 pairs with 0 violations [S15], [S16], reading no
labels. A single-layer architecture is invariant for every α [S17]; all
scores are finite and positive [S18] and S(α) decreases strictly in α [S19].
Insert Figure 1 (`docs/figures/reorder_alpha_curve.svg`): the two S(α)
curves meet at the α = 0 tie and separate as α grows. Caption: sensitivity
to FFN order — not predictive validity.

## 4. Effect sizes (~130 words + table)

Draft: the discount is a small perturbation of the NSC ordering. Quote the
table from `docs/report_pack.md` §4: S(2)/S0 spans [S20]–[S22]; Spearman
against S0 stays at [S23]–[S26]; Pearson(M2, M3) reaches [S27]–[S30];
Pearson(c_l, (l+1)/L) median [S32]; max deviation median [S33] with 71 of
100 configurations above 0.10 [S35], [S36]; deeper models are discounted
more [S37]. Insert Figure 2 (`docs/figures/m2_m3_scores.svg`): M2 vs M3 at
the reference strength α = β = 2, log–log with the y = x line. Caption: the
strength is a grid reference, not a tuned value.

## 5. C3 normalization side effect (~110 words)

Draft: because c_l divides by the architecture's own total, changing only
the last layer's FFN moves every earlier ratio (Δc_l = C_<l·(1/S0′ − 1/S0));
on the probe configurations [S41] with the last FFN scaled by [S42], the
untouched layers' factors move by up to [S43] and contributions by up to
[S44] (identity verified per row, worst residual [S45], [S46] violations).
Report this as its own table and as a limitation: a structural side effect
of normalizing by total capacity, not evidence for the mechanism.

## 6. Results (~450 words + tables)

### 6.1 Development ranking

[[B: dev ranking table]]

Draft around it: Spearman ρ, Kendall τ-b and ties for M1–M6 and the
ablation, on all pairs and on the 180 size-controlled pairs [S47] (rule:
same d_model, min/max(total) ≥ 0.90); both 5-row grids (α for M2, β for M3)
with α*, β* and whether the tie-break fired. Say explicitly what the
difference between M2 and M3 means given the near-collinearity
([S27]–[S30]) and the two-layer subgroup ([S38]–[S40]).

### 6.2 Selection under parameter caps

[[B: selection table]]

Draft around it: best selected PPL and regret per method and for the random
baseline at caps [P3], k ∈ [P4], from the 1,000-trial protocol [P5]; the
feasible pools are [S48]–[S51]; the harness's 200 trials [P6] are the exact
prefix of the same stream and appear in an appendix only. Insert Figure 3
(to be drawn from `results/selection_1000.json`: regret by cap, one line
per method).

### 6.3 Failure cases

[[B: failure cases]]

Draft around it: at least three concrete cases from
`docs/selection_failures.md` — which design was chosen, which was best, the
PPL gap, and the reason (score rank of the optimum, budget-edge choice,
depth/width mismatch, tie at the k-th rank, embedding-share artifact).

## 7. Limitations (~120 words)

Draft: the score uses `d_model` while `d_embed` differs in [S52] of [S53]
configurations, and the selection cap uses reported totals that include
adaptive embeddings — up to [S54]× the scored parameters — so budget scope
and scoring scope differ (the smallest cap's pool has no width-512 design
[S55]); the archive has one outcome per architecture, so the 1,000-trial
variance measures selection and tie-breaking randomness only, never
training-seed uncertainty; M2 and M3 are nearly collinear, so attribution
has low power; the final split is evaluated once, after freezing.

## References (not counted in the 4 pages)

Zhu, Zhao and Lu, *Neural Spectral Capacity* (arXiv:2609.23087);
Javaheripi et al., *LiteTransformerSearch*, NeurIPS 2022
(arXiv:2203.02094); the course starter/repository.
