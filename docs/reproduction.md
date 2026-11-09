# Reproduction record — CS5491 G045 Role A

> All commands are run from the repository root (`nsc-g045/`) unless noted.
> `--split final` is **never** run before the group's `freeze` tag; this rule
> is restated in `AGENTS.md`. All Role-A work uses `--split development` only.

## 1. Environment

| Item | Value |
|---|---|
| OS | Linux 6.8.0-138-generic x64 (Ubuntu) |
| `python3 -V` (repo default) | Python 3.14.6 (miniconda base) |
| Interpreter parity note | see §5 Deviations: fixture parity is exact on Python ≤ 3.10, 1-ULP off on ≥ 3.11 |
| Third-party dependencies | none (standard library only; `requirements.txt` is a comment) |
| Starter archive | `nsc-starter.zip`, SHA-256 `0ec560225cbac0acbc84be1cee656aed7bb6f7ee7078545d5c422e873fedee12`, downloaded 2026-10-30 |
| Starter version | `data/provenance.json` → `CS5491-202627A-v1` |

## 2. Command table

| Command | Expected | Measured | Time |
|---|---|---|---|
| `python3 check_starter.py` | 2 PASS lines + 2 Toy lines | identical (below) | 0.27 s |
| `python3 evaluate.py --split development --output results/dev_baseline.json` | 6 ranking rows + summary | identical (below) | 0.30 s |
| `python3 tools/compare_expected.py results/dev_baseline.json expected_development.json` | `PARITY OK` on 3.9/3.10; `PARITY OK (D0-1: 1 tolerated ULP at …)` on ≥3.11; `--strict` fails on any diff (§5) | <0.1 s |
| `sha256sum -c docs/starter_manifest.sha256` | all `OK` | all `OK` | <0.1 s |

### `python3 check_starter.py`

```
PASS: MP identities/convergence, reorder controls, resource arithmetic,
rank ties, selection, 200 configurations, split separation and data hashes.
Toy original NSC: 121.820169804 (both orders)
Toy position example: 96.957958136 vs 85.772296570
```

### `python3 evaluate.py --split development` (Python 3.14.6)

```
original_nsc         rho=  0.969745 tau=  0.861414 controlled_tau=  0.622222
position_example     rho=  0.970069 tau=  0.865051 controlled_tau=  0.622222
student              rho=  0.969745 tau=  0.861414 controlled_tau=  0.622222
ablation             rho=  0.969745 tau=  0.861414 controlled_tau=  0.622222
reported_parameters  rho=  0.727873 tau=  0.575758 controlled_tau=  0.133333
reference_flops      rho=  0.967948 tau=  0.858471 controlled_tau=  0.622222
100 development architectures; 8 budget/k combinations
```

## 3. Anchor numbers (§ plan 1.7)

| Quantity | Expected | Measured |
|---|---:|---:|
| toy original NSC (both orders) | 121.820169804 | 121.820169804017 |
| positional `[256,512]` | 96.957958136 | 96.957958136308 |
| positional `[512,256]` | 85.772296570 | 85.772296569717 |
| projection parameters | 327,680 | 327,680 |
| reference MACs/token | 524,288 | 524,288 |
| reference FLOPs/token | 1,048,576 | 1,048,576 |

ψ anchors (repr): `psi_mp(128,32)=1.5884174437376406`, `psi_mp(128,128)=6.2439440357298475`,
`psi_mp(128,256)=12.209734987417995`, `psi_mp(128,512)=23.395396554008926`.

Dev-pool anchors cross-checked while auditing: 10M: 24, 20M: 65, 30M: 83, 50M: 96;
size-controlled dev pairs: 180 (`evaluate.py` `matched_rule`).

## 4. Starter integrity

`docs/starter_manifest.sha256` covers `nsc.py`, `evaluate.py`,
`check_starter.py`, `expected_development.json` and all six `data/*.json`
(deliberately **not** `student_score.py`, the only editable starter file).
`sha256sum -c` passes; the five data-file hashes equal
`data/provenance.json` → `hashes`. The starter `README.md` is archived
verbatim at `docs/starter_README.md`.

## 5. Deviations

### D0-1  `expected_development.json` vs Python ≥ 3.11: one field, 1 ULP (`statistics.pstdev`)

- **Command**: `python3 evaluate.py --split development --output results/dev_baseline.json && python3 tools/compare_expected.py results/dev_baseline.json expected_development.json`
- **Expected (fixture)**: `$.selection[2].methods.random.sd_best_ppl = 11.825936547801547` (budget 20M, k=1, `random` baseline; pool = 65 dev architectures, seed 202627+20000000+1)
- **Actual (Python 3.14.6)**: `11.825936547801545` — every other field of the whole result is bit-identical to the fixture.
- **Root cause**: reconstructed the exact trial list (deterministic RNG stream) and compared three computation paths —
  exact `Fraction` arithmetic and the `math.fsum` float path both give `11.825936547801547` (the correctly rounded value, = fixture);
  `statistics.pstdev` on Python 3.11.15 / 3.12.3 / 3.14.6 gives `11.825936547801545` (1 ULP low);
  `statistics.pstdev` on Python 3.9.25 / 3.10.22 gives the fixture value.
  CPython changed `statistics.pstdev`'s accumulation between 3.10 and 3.11; for this input the newer
  implementation is 1 ULP below the exactly rounded result. The fixture was generated with the ≤ 3.10 behavior.
- **Interpreter matrix (full dev run vs fixture)**: 3.9.25 → `PARITY OK`; 3.10.22 → `PARITY OK`;
  3.11.15 / 3.12.3 / 3.14.6 → exactly this 1 field differs by 1 ULP.
- **Same-interpreter rule**: parity holds when the harness output is produced
  *and* compared by the same interpreter (verified 2026-10-31: 3.9.25 and
  3.10.22 runs of `evaluate.py` compare `PARITY OK` against the fixture).
  JSON artifacts generated on 3.14 (e.g. `results/dev_*.json`) differ from
  the fixture by that same 1 ULP no matter which interpreter compares them.
- **Impact**: the differing field belongs to the uniform-random baseline of the selection experiment;
  no scored method (original_nsc / position_example / student / ablation / reported_parameters /
  reference_flops) and no ranking statistic is affected. Not a starter bug, not a formula issue;
  no starter file was or will be modified because of it.
- **Diagnostic** (`python3 tools/d0_1_diagnose.py`, exit 0 — reconstructs the
  exact trial list and evaluates the three computation paths):

```
trial list: 200 samples, pool=65, seed=20202628
1. statistics.pstdev      : 11.825936547801545
2. math.fsum float path   : 11.825936547801547
3. exact Fraction path    : 11.825936547801547
fixture sd_best_ppl       : 11.825936547801547
python                    : 3.14.6
fsum == exact == fixture  : True
pstdev on this python     : 1 ULP off the fixture (D0-1, >=3.11 behaviour)
```

- **Resolution** (group decision, 2026-10-30): version-aware rule in CH03.
  (1) Python < 3.11: every field bit-equal, zero tolerance (verified: 3.9.25
  and 3.10.22 give `PARITY OK`). (2) Python ≥ 3.11: every field bit-equal
  except `selection[*].methods.random.sd_best_ppl`, which may differ by ≤ 1 ULP
  (integer ULP distance counted via `math.nextafter`); CH03 prints each
  tolerated field with path, observed/expected and the ULP distance. Any other
  field differing by even 1 ULP fails. (3) Reverse tests run inside CH03:
  perturbing any non-tolerated field by 1 ULP must fail the comparator, and
  perturbing `sd_best_ppl` by 2 ULP must fail it. (4) `results/checks.json`
  records `python_version`. (5) On CPython 3.14.6: expected
  `11.825936547801547`, observed `11.825936547801545`, ULP distance 1; cause is
  the ≥ 3.11 `statistics.pstdev` rounding change; Python 3.9/3.10 reproduce all
  fields bit-exactly. (6) Starter files, `expected_development.json` and the
  fixture are untouched.

### Source-reading notes (A0.6)

`nsc.py` / `student_score.py` / `evaluate.py` / `check_starter.py` were read
line by line against plan §1.5/§1.6. Confirmed, among others: `psi_mp` requires
positive ints (rejects bools), sorts `(m,n)` internally, is `lru_cache`d with
`steps=512`; `layers()` validates `d_model % h == 0` and per-layer list lengths;
`evaluate.canonical` uses `float(format(value, '.12g'))`; `select_trials`
creates `random.Random(202627 + budget + k)` per method, shuffles then stable-sorts
descending; `REPEATS = 200` is a module constant; `check_starter.py` does not
import `student_score`. No mismatches with the plan were found beyond D0-1.

## 6. Fresh-clone check

`rm -rf /tmp/fresh && git clone "$REPO" /tmp/fresh` (2026-10-31, tag
`a-scorer-final` tree), then in `/tmp/fresh`:

```
python3 check_starter.py       -> PASS (4 lines, identical to §2)
python3 checks/run_checks.py   -> 18/18 checks passed (1.80 s)
python3 -m unittest discover -s tests -t . -> OK (108 tests)
python3 checks/run_checks.py --mutations -> 7/7 mutations caught
```

## 7. A1 — archive data audit

`python3 tools/audit_data.py` (0.25 s) → 12/12 checklist items PASS
(counts, list lengths, divisibility, width histogram 49/51/53/47,
`d_embed != d_model` 141, constant fields, p10/p50/p90/max = 1.35/2.85/12.83/57.85
via `statistics.quantiles(n=10)`, >2/5/10/20 = 130/51/24/9, 0 duplicate specs,
dev PPL 24.35/38.34/74.38, pools 24/65/83/96, 180 size-controlled pairs).
Outputs: `results/data_audit.csv` (201 lines) + `docs/data_audit.md`.
Files opened: architectures/resources/splits/development_labels only.
Plan §1.8 medians (`pearson 0.9986`, `maxdev 0.1412`) are full-200-panel
quantities; the A1 supplementary table quotes both scopes.

## 8. A2 — core library and tools

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -t .` | `Ran 108 tests ... OK` (1.8 s; suite size history: 51 at A2, 59 after self-review SR-6, 72 at a-scorer-final, then the handoff-tool tests) |
| `python3 tools/show_breakdown.py config_0_j0 0` | 5 layers, `S0=589.868164872 S(0)=589.868164872`, `exact: S(0) == original_nsc -> True` |
| `python3 tools/show_breakdown.py config_0_j0 0.5` | per-layer A/F/c/factor equal to the plan's hand-check to the printed digit; `S(0.5)=517.201199027 sumA=126.526016726 sumA+F1=216.446042162` |
| `python3 tools/select_alpha.py --self-test` | `TIE-BREAK OK` + `SELECTION OK` |
| `python3 tools/normalization_probe.py` | identity (stable cross-multiplied form) worst rel `1.37e-16`, 0 violations; untouched-layer max `|Δfactor| = 6.775e-03`, max `|Δcontribution| = 3.734e+00`; 9 variant rows, no S0-vs-S order flip at α=1 |
| `python3 tools/weighting_diagnostic.py` | panel-200: `pearson(c_l,(l+1)/L)` median `0.99865`, `maxdev` median `0.14122` max `0.60393`; dev: 71/100 configs `>0.10`; `S(2)/S0` 0.61719/0.71833/0.89939; `pearson(S(2)/S0, L) = -0.469`; `spearman(S(a),S0)` 0.99945/0.99864/0.99760/0.99574; `pearson(M2,M3)` 0.99998/0.99995/0.99988/0.99974 |
| `python3 tools/check_py39.py` | `PY39 OK` |

Notes:
- Toy S(α) table (§1.7, both orders, α ∈ {0,.25,.5,1,2,1e12}) reproduced to
  9 decimals inside `tests/test_score.py`; limits are `ΣA + F_1`.
- `tools/normalization_probe.py` checks the analytic identity in the
  cross-multiplied form `c_l·S0 == C_<l` (bound 4·ulp ≈ 8.9e-16) because the
  literal form `C_<(1/S0' − 1/S0)` amplifies the rounding of `1/S0' − 1/S0`
  when S0' ≈ S0 (measured worst rel 2.67e-14 — unachievable at 1e-15 in
  float64 for ANY implementation). The algebraic identity is the same; the
  literal form's residual is printed as an informational line.
- `nsc.psi_mp`'s `lru_cache` keys alias int/float (`hash(128.0)==hash(128)`),
  so `psi_mp(128.0, 32)` returns the cached `ψ(128,32)` without re-running
  int validation once the int call is cached. Scoring always passes ints;
  the unit test for float rejection uses never-cached prime dimensions.

## 9. A3 — check suite and mutation proof

`python3 checks/run_checks.py` (1.8 s) → `18/18 checks passed`, exit 0,
`results/checks.json` written (python_version / git_commit / timestamp /
freeze_mode / per-check records). Per-check: CH01 15/15 byte-exact;
CH02 7/7; CH03 3/3 (bitwise, D0-1 tolerated field, reverse tests); CH04/05
200/200 bitwise; CH06 200/200; CH07 200/200; CH08 32/32; CH09 200/200;
CH10 200/200 max rel 1e-9 vs ΣA+F₁; CH11 9846/9846; CH12 4/4; CH13 3/3;
CH14 2/2; CH15 60/60 (the file count grows as tools/tests are added: 31 at A3, 44 at a-scorer-final); CH16 100/100; CH17 6/6 (180 pairs, pools 24/65/83/96);
CH18 4/4 dry-run (good fixture passes; wrong-α*, missing-field, trials=200
rejected).

`python3 checks/run_checks.py --mutations` (9.0 s) → `7/7 mutations caught`,
exit 0, `git status` clean:

```
MU1 alpha0_returns_zero        caught by CH05, CH08, CH09, CH11, CH16 (200/200 cases failed as expected)
MU2 prefix_includes_current    caught by CH07, CH08, CH10, CH11 (200/200 cases failed as expected)
MU3 drop_out_projection        caught by CH04, CH05, CH08, CH11, CH16 (200/200 cases failed as expected)
MU4 uniform_discount           caught by CH08, CH10, CH11, CH16 (128/32 cases failed as expected)
MU5 reverse_weights            caught by CH07, CH08, CH10, CH11 (200/200 cases failed as expected)
MU6 size_control_threshold_095 caught by CH17 (1/6 cases failed as expected)
MU7 freeze_alpha_mismatch      caught by CH18 (1/4 cases failed as expected)
7/7 mutations caught
```

Notes:
- **CH11 scope** (plan v1.2 A4.3, updated): the sweep uses the structures of
  ALL 200 archived configurations — dev 4,961 + final 4,884 = **9,845 pairs** —
  and reads no label file (scores only, never `final_labels.json`).
  CH11's n = 9,846 = 9,845 + the toy pair. At α=0 the two orders compare
  with rel ≤ 1e-14, not bitwise — swapping two FFN widths re-pairs A_l with
  F_l, so the fsum addends round differently (plan anti-pattern #11).
- CH03 comparator bite is self-tested on every run (1-ULP perturbation of a
  non-tolerated field must fail; 2-ULP perturbation of `sd_best_ppl` must
  fail).
- `--only CH18 --freeze` before C writes `freeze.json` fails gracefully with
  a pointer to `--dry-run` (exit 1).

## 10. A4 — controlled reorderings

`python3 tools/reorder_pairs.py --write results/reorder_pairs.csv` (1.4 s)
→ 13 rows (toy + 12 panel sources, A4.2 buckets with eligible-source
replacement), every row `sign_ok=True`, `nsc_rel_diff = 0.0` (math.fsum is
permutation-stable here), per-pair projection params/MACs identical;
`docs/reorder_table.md` generated with the toy S(α) figure data.
Full sweep: **9,845 pairs, 0 violations** (all 200 architectures, see §9 CH11
note). Toy row reproduces §1.7: S(0.5) 113.8892745548438 vs 116.244184056…
(+2.354909500822373).

## 11. A5 — official wiring

`student_score.py` rewritten as the thin wrapper (ALPHA = 0.0, `score` =
`ctxnsc.score_config(config, ALPHA)`, `ablation` = `original_nsc`).
`tools/make_variants.py` generated `variants/dev_alpha_{0.00,0.25,0.50,1.00,2.00}.py`.

| Command | Result |
|---|---|
| `python3 check_starter.py` | output identical to §2 baseline (it never imports student_score) |
| `python3 evaluate.py --split development --output results/dev_with_scorer.json` | six rows identical to baseline (student ≡ original_nsc at ALPHA=0) |
| `python3 tools/compare_expected.py results/dev_with_scorer.json expected_development.json` | `PARITY OK (D0-1: 1 tolerated ULP at $.selection[2]...)` — accepted by CH03 per group decision; `--strict` exits 1 |
| `python3 evaluate.py --split development --student variants/dev_alpha_0.50.py --output results/dev_alpha_0.50.json` | runs; `student` rho=0.970753 |
| `python3 tools/make_variants.py --verify` | `VARIANTS OK`: module scores bitwise equal to `ctxnsc.score_config`; the JSON `student` ranking block equals the recomputation from direct scores (canonical/ranks/tau-b conventions) |
| `python3 tools/selection_ext.py --self-test` | `PARITY OK` + `PREFIX OK` + `TRIALS OK` (0.07 s; 20 randomized parity cases vs `evaluate.select_trials`; 1,000-trial prefix equals 200-trial run bitwise) |
| `python3 checks/run_checks.py` | still 18/18 with the rewired scorer |
| `python3 -m unittest discover -s tests -t .` | 108 OK |

`REPEATS=200` in `evaluate.py` untouched; the 1,000-trial main protocol lives
in `tools/selection_ext.py` for B's evaluator (all methods, same pools, same
seeds, same tie-handling).

## 12. Handoff additions (2026-11-09) — commands and raw outputs

New tools for roles B/C (P0-1 … P2 of the handoff task); each command below
was run on the handoff tree and its output pasted verbatim (re-captured
right before tagging `a-scorer-handoff`; the unittest output is trimmed
to its summary lines).

```
$ python3 tools/selection_failures.py --self-test    # exit 0, 0.05 s
ROWS OK (8 entries, 5 failures, gap = best_ppl - oracle_ppl, all tags present)
OUTPUT OK (13-column CSV, readable MD, committed examples current)
CONTRACT OK (trials=200, wrong chosen_ppl, pool mismatch, non-top-k choice, split mismatch, final without --allow-final: all rejected)
SELECTION FAILURES OK

$ python3 tools/selection_failures.py --selection tests/fixtures/selection_example.json --split development --fixture-world --out-csv /tmp/sf_example.csv --out-md /tmp/sf_example.md    # exit 0, 0.05 s
entries analysed: 8 (random skipped: 0); failures: 5
wrote /tmp/sf_example.csv (5 rows) and /tmp/sf_example.md

$ python3 tools/selection_failures.py --selection tests/fixtures/selection_example.json --split final    # exit 2, 0.05 s
REFUSED: --split final requires --allow-final (role B, only after the group's freeze tag); refusing before reading any file

$ python3 tools/make_position_variants.py --verify    # exit 0, 0.52 s
OK   m3_beta_0.00.py: scores bitwise (primitive + independent formula); ablation == original_nsc on 200; score == original_nsc on 200 (no evaluate.py output yet to cross-check)
OK   m3_beta_0.25.py: scores bitwise (primitive + independent formula); ablation == original_nsc on 200; score < original_nsc on 200 (no evaluate.py output yet to cross-check)
OK   m3_beta_0.50.py: results/dev_m3_beta_0.50.json: student block matches recomputation, ablation == original_nsc, student != original_nsc
OK   m3_beta_0.50.py: scores bitwise (primitive + independent formula); ablation == original_nsc on 200; score < original_nsc on 200
OK   m3_beta_1.00.py: scores bitwise (primitive + independent formula); ablation == original_nsc on 200; score < original_nsc on 200 (no evaluate.py output yet to cross-check)
OK   m3_beta_2.00.py: scores bitwise (primitive + independent formula); ablation == original_nsc on 200; score < original_nsc on 200 (no evaluate.py output yet to cross-check)
M3 VARIANTS OK

$ python3 tools/make_variants.py --verify    # exit 0, 0.20 s
SKIP dev_alpha_0.00.py: no evaluate.py output yet (run evaluate.py --student variants/dev_alpha_0.00.py --output results/dev_grid/dev_alpha_0.00.json)
SKIP dev_alpha_0.25.py: no evaluate.py output yet (run evaluate.py --student variants/dev_alpha_0.25.py --output results/dev_grid/dev_alpha_0.25.json)
OK   dev_alpha_0.50.py: module scores bitwise; results/dev_alpha_0.50.json ranking block matches recomputation
SKIP dev_alpha_1.00.py: no evaluate.py output yet (run evaluate.py --student variants/dev_alpha_1.00.py --output results/dev_grid/dev_alpha_1.00.json)
SKIP dev_alpha_2.00.py: no evaluate.py output yet (run evaluate.py --student variants/dev_alpha_2.00.py --output results/dev_grid/dev_alpha_2.00.json)
VARIANTS OK

$ python3 checks/run_checks.py --no-write --only CH18 --dry-run    # exit 0, 0.06 s
CH18 freeze_consistency     PASS (4/4, exact) [pass]
1/1 checks passed
(--no-write: the default results/checks.json is left untouched)

$ python3 tools/make_figures.py --check    # exit 0, 0.04 s
FIGURES OK (committed SVGs equal a fresh render)

$ python3 tools/make_report_pack.py --check    # exit 0, 0.06 s
REPORT PACK OK (equals a fresh render; 66 cited values; only the 3 [[B: ...]] placeholders)

$ python3 tools/check_docs_counts.py    # exit 0, 0.09 s
live counts: 108 tests, CH15 60/60 .py files
DOC COUNTS OK (no stale counts; current counts present)

$ python3 -m unittest discover -s tests -t .    # exit 0, 1.96 s
Ran 108 tests in 1.877s
OK
```

M3 acceptance run through the official harness (contract check, not a beta
evaluation): `python3 evaluate.py --split development --student
variants/m3_beta_0.50.py --output results/dev_m3_beta_0.50.json` (0.44 s);
programmatic comparison of the JSON blocks — beta=0.5: student ranking ==
original_nsc: False, ablation == original_nsc: True; beta=0.0 (run to /tmp):
student == original_nsc in the ranking block and in all 8 selection cells.

Notes:
- `results/reorder_pairs.csv` gained `s_after_a*` and
  `results/weighting_diagnostic.csv` gained `s0, m2_alpha2, m3_beta2` (figure
  data); both changes are append-only — every pre-existing value is identical
  and the three `*_summary.json` files regenerate byte-identically.
- CH15 on Python 3.9 now derives the stdlib set from the interpreter's own
  stdlib directory (311 roots on 3.9.25) after the hand-curated fallback
  produced false 3.9-only violations three times (builtins/unittest,
  fractions, inspect).
- `tools/check_docs_counts.py` now fails on ANY stale `<n> tests` /
  `CH15 a/b` mention in README/HANDOFF/reproduction (live counts from
  unittest discovery); `--fix` rewrites only those live-count mentions.
