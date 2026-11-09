# Milestone runbook — what B and C run next (prepared by role A, 2026-11-09)

Milestone deadline: **2026-11-19 23:59 BJT** (baseline reproduction + new score
+ preliminary evaluation running). Freeze (internal): 2026-11-26. Final:
2026-12-03 23:59 BJT. Role A's tag **`a-scorer-handoff` is A's handoff
snapshot, NOT the team milestone tag** — the milestone tag goes on the team
commit that contains B's results and C's draft (step C3).

Timings below were measured on the A machine (Python 3.14.6, laptop CPU)
for the same or an equivalent command; none of A's measurements ran the
α/β grids, which are B's job.

## Step 0 — everyone, once (≈ 15 s)

```sh
git clone <repo-url> nsc-g045 && cd nsc-g045
python3 check_starter.py                    # PASS + toy 121.820169804 / 96.957958136 vs 85.772296570 (0.3 s)
python3 checks/run_checks.py --no-write     # 18/18 checks passed (1.8 s)
python3 -m unittest discover -s tests -t .  # all tests OK (≈ 2 s)
```

`--no-write` keeps `results/checks.json` untouched (a plain full run rewrites
its timestamp/git_commit, which makes `git status` dirty by design).

## Role C — public repository

**C0. Decide the author email BEFORE the first push** (pending user decision,
`docs/HANDOFF_A.md` item 6). Options and consequences:

| option | command sketch | consequence |
|---|---|---|
| keep the current address | nothing | history and tags unchanged |
| display-only mapping | add `.mailmap`: `Congyang Feng <72655576@cityu-dg.edu.cn> <72655576@my.cityu.edu.hk>` | `git log`/`shortlog` show the new address; hashes unchanged; GitHub/Gitee web UIs ignore `.mailmap` |
| rewrite history | `git filter-repo --mailmap .mailmap` (external tool) | EVERY commit hash and tag changes: `results/checks.json` `git_commit` and the hashes quoted in docs (fc4c49e, c6166c6, e183692, …) become stale; re-run `python3 checks/run_checks.py` and fix the docs; must happen before anyone clones the public remote |

**C1. Create the remote and push** (GitHub shown; Gitee is identical with its URL):

```sh
git remote add origin https://github.com/<owner>/nsc-g045.git   # or https://gitee.com/<owner>/nsc-g045.git
git push -u origin master
git push origin --tags        # starter-import, a-scorer-v1, a-scorer-v1.1, a-scorer-final, a-scorer-handoff
```

Expected: the remote shows `master` and the five tags; a fresh clone passes
Step 0. Set the repository to **public** (course requirement).

## Role B — runs (≈ 10 s of compute in total)

**B1. α grid through the official harness** (M2; `results/dev_grid/` is B's directory):

```sh
mkdir -p results/dev_grid
for a in 0.00 0.25 0.50 1.00 2.00; do
  python3 evaluate.py --split development --student variants/dev_alpha_$a.py \
      --output results/dev_grid/dev_alpha_$a.json
done
python3 tools/make_variants.py --verify     # VARIANTS OK (cross-checks results/dev_grid/)
```

Expected per run: the 6-row table and `100 development architectures; 8
budget/k combinations`; 0.44 s each (measured for `dev_alpha_0.50`).

**B2. β grid (M3, the matched position-only control)**:

```sh
for b in 0.00 0.25 0.50 1.00 2.00; do
  python3 evaluate.py --split development --student variants/m3_beta_$b.py \
      --output results/dev_grid/m3_beta_$b.json
done
python3 tools/make_position_variants.py --verify   # M3 VARIANTS OK (0.5 s)
```

**B3. Select α* and β* with the frozen C4 rule** (same grid, rule, tie-break):

```sh
python3 tools/select_alpha.py --method cumulative --grid 0,0.25,0.5,1,2   # -> results/dev_grid_cumulative.json
python3 tools/select_alpha.py --method position   --grid 0,0.25,0.5,1,2   # -> results/dev_grid_position.json
```

Expected: 5 `alpha=… rho=…` rows, then `selected=…  tie_break_used=…`, about
1 s each (estimate: same scoring work as `tools/weighting_diagnostic.py`).
Keep both JSON files — C3 freezes their `selected` values and CH18 re-checks
them.

**B4. Six-method × 1,000-trial selection** — B owns the evaluator. Every
method (M1 `original_nsc`, M2 at α*, M3 at β*, M4 `position_example`, M5
reported parameters, M6 reference FLOPs, the ablation) and the random
baseline use the same pools, seeds `202627 + cap + k` and tie-handling, via
`tools/selection_ext.py: select_trials_ext(..., repeats=1000)`. Export
`results/selection_1000.json` in the contract of `docs/interface.md`
("Selection export contract"). Validated export shape (run by A in a scratch
directory with M1 + random only):

```python
scores = {cid: evaluate.canonical(score_fn(cid)) for cid in keys}   # None for random
pool = [cid for cid in keys if total[cid] <= cap]                     # split order
seed = 202627 + cap + k
chosen = representative_choice(pool, scores, k, seed)                # trial 1
agg = select_trials_ext(pool, scores, k, ppl, seed, repeats=1000)
entries.append({"method": name, "cap": cap, "k": k, "seed": seed, "pool": pool,
                "chosen": chosen, "chosen_ppl": [ppl[c] for c in chosen],
                "best_ppl": min(ppl[c] for c in chosen),
                "oracle_ppl": min(ppl[p] for p in pool),
                "regret": min(ppl[c] for c in chosen) - min(ppl[p] for p in pool),
                "mean_best_ppl": agg["mean_best_ppl"], "mean_regret": agg["mean_regret"],
                "sd_best_ppl": agg["sd_best_ppl"]})
# then: {"split": "development", "trials": 1000, "entries": entries}
```

Cost: 9.0 ms per `select_trials_ext` call on a 96-design pool → ≈ 0.6 s for
8 cells × (7 methods + random) (measured micro-benchmark). Name methods
canonically (`original_nsc`, `ablation`, `position_example`,
`reported_parameters`, `reference_flops`, `m2_alpha_<a>`, `m3_beta_<b>`) so
the failure tool can recompute scores, or add a top-level `scores` map.

**B5. Failure cases** (TA 1/2: at least three concrete cases):

```sh
python3 tools/selection_failures.py --selection results/selection_1000.json \
    --split development --out-csv results/selection_failures.csv \
    --out-md docs/selection_failures.md
```

Expected: `entries analysed: …; failures: …`, a 13-column CSV and an MD with
candidate cases (format: `docs/examples/selection_failures_example.md`);
any contract violation exits 1 with the offending entry named.

**B6. Six-method development table** for the report: Spearman ρ, Kendall
τ-b, ties, size-controlled τ-b (180 pairs) for M1–M6 + ablation, taken from
the `results/dev_grid/*.json` runs at α* / β* (M1, M4, M5, M6 and the
ablation are identical in every run). Hand C: both grid JSONs, the six-method
table, `selection_1000.json`, `selection_failures.{csv,md}`. Commit them and
re-run Step 0 (all green, `git status` clean).

## Submission language and format (applies to C2 and C3)

The milestone draft and the final report are submitted in **English**.
Course format: Times New Roman 12 pt, 2.5 cm margins, A4, single spacing,
4 pages excluding references, submitted as **PDF**.

A Chinese translation, if the team wants one for internal discussion, lives
under `docs/zh/` (for example `docs/zh/report_zh.md`) and is a
**non-submitted reference copy** — never replace the English primary with
it, and never submit it. `docs/report_pack.md` and
`docs/report_template_en.md` are English; C writes English first and
translates only afterwards as a secondary copy.

## Role C — 4-page draft and milestone tag

**C2. Draft** (owner C): start from `docs/report_pack.md` (every number is
sourced; `python3 tools/make_report_pack.py --check` proves it is current),
replace its three B slots with B6 / B4 / B5, use `docs/figures/*.svg` plus a
selection-regret figure (spec in the pack, Section 8). Format: Times New Roman
12 pt, 2.5 cm margins, A4, single spacing, 4 pages excluding references;
cite NSC (arXiv:2609.23087) and LiteTransformerSearch (arXiv:2203.02094);
separate reproduction from contribution; keep the 1,000-trial variance
separate from training-seed uncertainty. Target 11/17, review 11/18.

**C3. Milestone tag** on the team commit containing B's results and the draft:

```sh
git tag -a milestone-2026-11-19 -m "G045 milestone: baseline + new score + preliminary evaluation" <commit>
git push origin milestone-2026-11-19
```

Submit the public repository URL + this tag (or its commit hash) before
2026-11-19 23:59 BJT.

## After the milestone — freeze, then final (for reference)

1. C copies `docs/freeze_template.json` to the repository root as
   `freeze.json`, fills `alpha_star` / `beta_star` from B3's JSONs, sets
   `ALPHA` in `student_score.py` to α*, and signs `docs/CONVENTIONS_draft.md`
   into `CONVENTIONS.md`.
2. `python3 checks/run_checks.py --only CH18 --freeze` must pass, then
   `python3 checks/run_checks.py` 18/18; C tags `freeze`.
3. Only then B runs `python3 evaluate.py --split final --output
   results/final_results.json` **once**; final failure cases need
   `tools/selection_failures.py --split final --allow-final`.
