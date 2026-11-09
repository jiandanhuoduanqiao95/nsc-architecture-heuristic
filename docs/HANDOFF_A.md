# HANDOFF — Role A → roles B and C (tag `a-scorer-handoff.1`, 2026-11-10)

Role A's deliverable is on tag **`a-scorer-handoff.1`** (the current handoff
snapshot, English-primary closeout). This file is the entry point: what is done, how to use it, what
B and C still must do, and what is deliberately **not** A's job. The
step-by-step commands for the milestone are in `docs/milestone_runbook.md`.

Tag map (no tag is ever moved again):

| tag | marks |
|---|---|
| `starter-import` | the unmodified starter import |
| `a-scorer-v1` (fc4c49e) | historical: pre-self-review tree |
| `a-scorer-v1.1` (eb42979) | historical: self-review rectification (it was re-pointed once within its own session; recorded in `docs/SELF_REVIEW_A.md`) |
| `a-scorer-final` (e183692) | historical: closeout tree; it was rebuilt ONCE (user-approved) to fix a typo in its results-commit message (it named 4d41ed4…; the recorded run commit is c6166c6…) |
| **`a-scorer-handoff.1`** | **current**: English-primary closeout (this file's state) |
| `a-scorer-handoff` (e340011) | historical: post-P3 closeout with the B/C enablement tools, pre-English |
| `a-scorer-handoff.1` | English-primary closeout: submission-language rule, English 4-page skeleton (`docs/report_template_en.md`), CJK confined to `docs/zh/`, report-pack citation coverage 61/61 (this file's commit) |

For `a-scorer-final` and `a-scorer-handoff`, `results/checks.json` was
generated on the commit directly beneath the tag (`git show
<tag>:results/checks.json | grep git_commit` equals `git rev-parse <tag>^`;
a file cannot contain the hash of the commit that contains it). The same
holds for `a-scorer-v1.1`; `a-scorer-v1`'s copy records an earlier run
(db83a18, its tree's checks were not re-run before tagging) — historical
only. The same holds for `a-scorer-handoff.1` itself: its tree adds
docs/tests/tooling relative to the recorded commit e340011 (checks/ logic
unchanged; 18/18 re-run on the `.1` tree), and `a-scorer-handoff.1` is A's
snapshot, **not** the team milestone tag.

## A-DoD: 12/12 done (evidence per item)

| # | Item | Evidence |
|---|---|---|
| 1 | `check_starter.py` PASS, output = plan §1.7 | `docs/reproduction.md` §2 |
| 2 | dev evaluation matches `expected_development.json` field-by-field | CH03 (3/3) + `docs/reproduction.md` §5 D0-1 (one 1-ULP field on Python ≥3.11, group-approved rule) |
| 3 | unit tests | `Ran 112 tests ... OK` |
| 4 | `checks/run_checks.py` | `18/18 checks passed`, `results/checks.json` |
| 5 | `checks/run_checks.py --mutations` | `7/7 mutations caught` |
| 6 | α=0 exact recovery | CH05: 200/200 bitwise |
| 7 | per-layer identity vs `nsc.layer_capacities` | CH04: 200/200 elementwise bitwise + fsum |
| 8 | reorder controls | CH11: toy + **9,845 pairs, 0 violations**; `results/reorder_pairs.csv`, `docs/reorder_table.md` |
| 9 | size-control rule + 180 pairs (TA 1/2) | CH17 (rule string + 180 + pools 24/65/83/96) |
| 10 | CH18 dry-run + negative tests (TA 1/2) | good fixture passes; wrong-α*, missing-field, `trials=200` rejected; MU7 caught |
| 11 | M3 primitive contract (TA 1) | `tests/test_score.py::test_m3_primitive_bitwise` + `tests/test_position_variants.py` |
| 12 | hygiene | `student_score.py` has exactly ALPHA/score/ablation; starter files byte-identical (CH01, manifest); docs complete; tags exist; cold clone green |

Cold clone (`git clone` → fresh dir): `check_starter.py` PASS,
`checks/run_checks.py` **18/18**, `--mutations` **7/7**, 112 tests OK.

## Handoff additions (2026-11-09) — so B/C can run without A

| what | for | entry point | acceptance |
|---|---|---|---|
| failure-case extractor (TA 1/2) | B → C | `tools/selection_failures.py` (contract: `docs/interface.md`) | `--self-test` → `SELECTION FAILURES OK` |
| M3 position-only variants (TA 1/2) | B | `variants/m3_beta_{0.00,0.25,0.50,1.00,2.00}.py` | `tools/make_position_variants.py --verify` → `M3 VARIANTS OK` |
| freeze template | C | `docs/freeze_template.json` (only α*/β* to fill) | `tests/test_freeze_template.py` |
| conventions draft (C1–C8) | C to sign | `docs/CONVENTIONS_draft.md` | — |
| report pack (every number sourced) | C | `docs/report_pack.md` | `tools/make_report_pack.py --check` |
| figures (SVG) | C | `docs/figures/{reorder_alpha_curve,m2_m3_scores}.svg` | `tools/make_figures.py --check` |
| milestone runbook | B, C | `docs/milestone_runbook.md` | — |
| representative-choice helper | B | `tools.selection_ext.representative_choice` | archive cross-check in `tests/test_selection_failures.py` |

## For role B — start here

```python
import json
from ctxnsc import score_config, scores_for_alphas, breakdown_config

configs = json.load(open("data/architectures.json"))
s = score_config(configs["config_0_j0"], 0.5)          # S(alpha)
grid = scores_for_alphas(configs["config_0_j0"], (0, .25, .5, 1, 2))
bd = breakdown_config(configs["config_0_j0"], 0.5)     # per-layer A/F/c/factor
```

Then follow `docs/milestone_runbook.md` steps B1–B6: α grid
(`variants/dev_alpha_*.py`) and β grid (`variants/m3_beta_*.py`) through
`evaluate.py --student`, α*/β* via `tools/select_alpha.py --method
cumulative|position`, the six-method × 1,000-trial export
`results/selection_1000.json` (contract in `docs/interface.md`), and the
failure table via `tools/selection_failures.py`. Rules: M3 uses
`score_with_ratios` + `position_ratios` (never reimplemented); M1/M4 call
`nsc.original_nsc` / `nsc.position_example` directly; every method goes
through `evaluate.canonical`; all methods + random use the same pools and
`repeats=1000`; do not edit `student_score.ALPHA` — sweep via `variants/`.

## For role C — acceptance commands

```sh
python3 checks/run_checks.py --no-write --only CH17          # size-control rule + 180 pairs
python3 checks/run_checks.py --no-write --only CH18          # dry-run now; strict once freeze.json exists
python3 checks/run_checks.py --no-write --only CH18 --freeze # strict validation after you write freeze.json
python3 tools/make_report_pack.py --check                    # report pack equals the artifacts
python3 tools/make_figures.py --check                        # SVGs equal the artifacts
sha256sum -c docs/starter_manifest.sha256                    # starter integrity
python3 tools/check_py39.py                                  # stdlib-only gate
```

A full `checks/run_checks.py` rewrites `results/checks.json`
(timestamp/git_commit); seeing exactly that file as modified afterwards is
expected — pass `--no-write` for pure verification runs.

`freeze.json` (your file, repository root): copy `docs/freeze_template.json`
and fill `alpha_star` / `beta_star` from `results/dev_grid_cumulative.json`
/ `results/dev_grid_position.json` (`selected`); every other field is
pre-filled with the plan's A8.2 values. CH18 strict additionally requires
`student_score.ALPHA == alpha_star`. The template under `docs/` is never read
by CH18 strict.

## What B and C still must do (A does not do these)

| owner | task | due |
|---|---|---|
| B | six-method evaluator (M1–M6 + ablation + random) on the 1,000-trial protocol; export `results/selection_1000.json` | before the milestone |
| B | α grid + β grid through the harness; α*, β* with the C4 rule (`results/dev_grid_{cumulative,position}.json`) | before the milestone |
| B | six-method development table; failure table (`tools/selection_failures.py`) | before the milestone |
| C | public remote + push (decide the author email first, runbook C0) | before the milestone |
| C | 4-page draft from `docs/report_pack.md` + B's tables; milestone tag on the team commit | 2026-11-19 23:59 BJT |
| C | `freeze.json` + `CONVENTIONS.md` (from the draft) + `ALPHA` + `freeze` tag (CH18 `--freeze` must pass) | 2026-11-26 |
| B | `--split final` once, after the freeze tag; final failure cases with `--allow-final` | after the freeze |
| C | final 4-page report and graded tag | 2026-12-03 23:59 BJT |

## Explicitly out of scope for A

- α/β tuning on dev, M3/M4 evaluators, 1,000-trial execution (B)
- `freeze.md` / `freeze.json` / `CONVENTIONS.md` / `freeze` tag (C)
- `--split final` and the real failure-case analysis (B/C)
- final report text and repository publication (C)

## Known limitations (already quantified, keep them in the report)

1. M2 ≈ M3 (Pearson ≥ 0.9997 on dev): the attribution test has little power;
   the two-layer configurations separate them most (`docs/report_pack.md` §4).
2. `c_l ≈ (l+1)/L` (panel median Pearson 0.99865): the discount is close to
   positional weighting for most architectures.
3. `resources.total` includes adaptive embeddings (up to 57.85× projection
   parameters): budget scope ≠ scoring scope (audit item 7).
4. Even at α=2 the score correlates with S0 at ρ=0.9957: our mechanism is a
   small perturbation of NSC ordering; sensitivity ≠ prediction.
5. Fixture pstdev ULP artifact on Python ≥ 3.11 (D0-1) — documented, encoded
   in CH03, bitwise on 3.9/3.10.
6. **Pending user decision (do not act unilaterally):** the git author email
   is currently `72655576@my.cityu.edu.hk` (inferred by role A); the actual
   course account is `72655576@cityu-dg.edu.cn`. Options and consequences
   (keep / `.mailmap` / history rewrite, which changes every hash and tag)
   are in `docs/milestone_runbook.md` C0; decide BEFORE the first public push.

## Contact

Role A (Congyang Feng, 72655576) — respond within 24 h on group chat; interface
changes to `ctxnsc/` require A's sign-off per `AGENTS.md`.

## Group message template

```
@B @C Role A handoff complete: tag a-scorer-handoff.1 (historical tags
a-scorer-v1 / v1.1 / final are frozen and never moved).
Start with docs/milestone_runbook.md. B runs B1-B6: the alpha grid via
variants/dev_alpha_*, the beta grid via variants/m3_beta_*, alpha*/beta* via
tools/select_alpha.py, the six-method 1,000-trial export to
results/selection_1000.json (contract in docs/interface.md), and failure
cases via tools/selection_failures.py.
C: decide the author email before pushing the public remote (runbook C0);
the 4-page material is docs/report_pack.md (every number sourced, three
[[B: ...]] slots left for B); figures in docs/figures/; freeze template
docs/freeze_template.json; conventions draft docs/CONVENTIONS_draft.md
awaiting signature.
Acceptance: checks/run_checks.py --no-write -> 18/18; --mutations -> 7/7;
all unit tests pass; check_starter PASS.
Do not edit student_score.py's ALPHA (C changes it at the freeze and writes
freeze.json, validated by CH18 --freeze); --split final runs once, by B,
only after the freeze tag.
```
