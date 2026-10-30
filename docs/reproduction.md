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
| `python3 tools/compare_expected.py results/dev_baseline.json expected_development.json` | `PARITY OK` | 1-field 1-ULP diff on Python ≥ 3.11; `PARITY OK` on 3.9/3.10 (§5) | <0.1 s |
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
- **Impact**: the differing field belongs to the uniform-random baseline of the selection experiment;
  no scored method (original_nsc / position_example / student / ablation / reported_parameters /
  reference_flops) and no ranking statistic is affected. Not a starter bug, not a formula issue;
  no starter file was or will be modified because of it.
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

(filled at A7/A8)
