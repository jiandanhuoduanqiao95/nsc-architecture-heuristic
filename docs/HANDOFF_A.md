# HANDOFF — Role A → roles B and C (tag `a-scorer-v1`, 2026-10-31)

Role A's full deliverable is on tag `a-scorer-v1`. This file is the entry
point: what is done, how to use it, what is deliberately **not** done.

## A-DoD: 12/12 done (evidence per item)

| # | Item | Evidence |
|---|---|---|
| 1 | `check_starter.py` PASS, output = plan §1.7 | `docs/reproduction.md` §2 |
| 2 | dev evaluation matches `expected_development.json` field-by-field | CH03 (3/3) + `docs/reproduction.md` §5 D0-1 (one 1-ULP field on Python ≥3.11, group-approved rule) |
| 3 | unit tests | `Ran 72 tests ... OK` |
| 4 | `checks/run_checks.py` | `18/18 checks passed`, `results/checks.json` |
| 5 | `checks/run_checks.py --mutations` | `7/7 mutations caught` |
| 6 | α=0 exact recovery | CH05: 200/200 bitwise |
| 7 | per-layer identity vs `nsc.layer_capacities` | CH04: 200/200 elementwise bitwise + fsum |
| 8 | reorder controls | CH11: toy + **9,845 pairs, 0 violations**; `results/reorder_pairs.csv`, `docs/reorder_table.md` |
| 9 | size-control rule + 180 pairs (TA 1/2) | CH17 (rule string + 180 + pools 24/65/83/96) |
| 10 | CH18 dry-run + negative tests (TA 1/2) | good fixture passes; wrong-α*, missing-field, `trials=200` rejected; MU7 caught |
| 11 | M3 primitive contract (TA 1) | `tests/test_score.py::test_m3_primitive_bitwise` — 10 sampled configs × β∈{0,.25,.5,1,2}, bitwise vs independent formula |
| 12 | hygiene | `student_score.py` has exactly ALPHA/score/ablation; starter files byte-identical (CH01, manifest); docs complete; tag exists; cold clone green (below) |

Cold clone (`git clone` → fresh dir): `check_starter.py` PASS,
`checks/run_checks.py` **18/18**, `--mutations` **7/7**, 72 tests OK.

## For role B — 5-line starter

```python
import json
from ctxnsc import score_config, scores_for_alphas, breakdown_config

configs = json.load(open("data/architectures.json"))
s = score_config(configs["config_0_j0"], 0.5)          # S(alpha)
grid = scores_for_alphas(configs["config_0_j0"], (0, .25, .5, 1, 2))
bd = breakdown_config(configs["config_0_j0"], 0.5)     # per-layer A/F/c/factor
```

then, from the shell:

```sh
python3 evaluate.py --split development --student variants/dev_alpha_0.50.py --output results/dev_alpha_0.50.json
python3 tools/select_alpha.py --method cumulative --grid 0,0.25,0.5,1,2   # M2 grid (C4 rule)
python3 tools/select_alpha.py --method position   --grid 0,0.25,0.5,1,2   # M3 grid (same rule)
python3 tools/selection_ext.py            # 1,000-trial reference: select_trials_ext(..., repeats=1000)
python3 tools/make_variants.py --verify   # variant contract check
```

Contract details: `docs/interface.md`. Rules: M3 must use
`score_with_ratios` + `position_ratios` (never reimplemented); M1/M4 call
`nsc.original_nsc` / `nsc.position_example` directly; every method goes
through `evaluate.canonical`; all six methods + random use the same pools and
`repeats=1000` (`tools/selection_ext.py`, whose 200-trial prefix parity is
self-tested); do not edit `student_score.ALPHA` — sweep via `variants/`.

## For role C — acceptance commands

```sh
python3 checks/run_checks.py --only CH17          # size-control rule + 180 pairs
python3 checks/run_checks.py --only CH18          # dry-run now; strict once freeze.json exists
python3 checks/run_checks.py --only CH18 --freeze # strict validation after you write freeze.json
sha256sum -c docs/starter_manifest.sha256         # starter integrity
python3 tools/check_py39.py                       # stdlib-only gate
```

`freeze.json` schema (your file, CH18's rules): keys exactly
`alpha_star, beta_star, alpha_grid, beta_grid, selection_rule, tie_break,
tie_handling, size_control_rule, trials, pool_rule, metrics, figures`;
`alpha_star == results/dev_grid_cumulative.json:selected`, `beta_star ==
results/dev_grid_position.json:selected`, grids `[0,0.25,0.5,1,2]`,
`trials == 1000`, `size_control_rule` mentions 0.90 and 180, and
`student_score.ALPHA == alpha_star`. A template lives at
`tests/fixtures/freeze_example.json`.

## Explicitly out of scope for A (do not wait on A for these)

- α/β tuning on dev (B), M3/M4 evaluators (B), 1,000-trial execution (B)
- `freeze.md` / `freeze.json` / `CONVENTIONS.md` / `freeze` tag (C)
- `--split final` and failure-case analysis (B/C)
- final report text, figures and repo publication (C)

## Known limitations (already quantified, keep them in the report)

1. M2 ≈ M3 (Pearson ≥ 0.9997 on dev): the attribution test has little power;
   report as limitation + analyze the most-different subgroups.
2. `c_l ≈ (l+1)/L` (panel median Pearson 0.99865): the discount is close to
   positional weighting for most architectures.
3. `resources.total` includes adaptive embeddings (up to 57.85× projection
   parameters): budget scope ≠ scoring scope (audit item 7).
4. Even at α=2 the score correlates with S0 at ρ=0.9957: our mechanism is a
   small perturbation of NSC ordering; sensitivity ≠ prediction.
5. Fixture pstdev ULP artifact on Python ≥ 3.11 (D0-1) — documented, encoded
   in CH03, bitwise on 3.9/3.10.
6. **Pending group decision (do not act unilaterally):** the git author
   email is currently `72655576@my.cityu.edu.hk` (inferred by role A). The
   actual course account is `72655576@cityu-dg.edu.cn`. If the group confirms
   the school address, rewrite history with git-filter-repo/mailmap BEFORE
   pushing to the public remote; until the user decides, the inferred
   address stays and this file records the question.

## Contact

Role A (Congyang Feng, 72655576) — respond within 24 h on group chat; interface
changes to `ctxnsc/` require A's sign-off per `AGENTS.md`.

## Group message template

```
@B @C 角色 A 已交接：tag a-scorer-v1。
接口：docs/interface.md（score_config / scores_for_alphas / breakdown_config / score_with_ratios）。
验收：checks/run_checks.py → 18/18；--mutations → 7/7；CH17/CH18 已过（CH18 为 dry-run）。
已完成：check_starter PASS；dev 与 expected 逐字段一致；α=0 逐位一致；恒等式 200/200；重排 9,845 对 0 违例。
TA 工具：tools/select_alpha.py（α/β 网格，B 跑）；tools/normalization_probe.py（C3，B 写报告）；tools/selection_ext.py（1,000 次，B 的六方法全用它）。
α 网格用 variants/ 跑 evaluate.py --student；不要改 student_score.py 的 ALPHA（冻结时由 C 改，同时写 freeze.json，我用 CH18 校验）。
需要我配合：M1/M4 必须直调 nsc；M3 用 ctxnsc.score_with_ratios + position_ratios（同网格同规则）。
```
