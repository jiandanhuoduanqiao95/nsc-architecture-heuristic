# NSC-G045 — context-discounted Neural Spectral Capacity as an architecture-design heuristic

CS5491 Artificial Intelligence, course project, Group G045
(Congyang Feng, Langqi Zhong, Zijian Yang). Course topic: *Neural Spectral
Capacity as a Heuristic for Architecture Design*.

**One-sentence summary.** We keep the starter's NSC scoring convention and add
one motivated change: each layer's FFN capacity is discounted by the
architecture's own normalized *preceding* capacity, `S(α) = Σ_l [A_l +
F_l/(1+α·c_l)]` with strict-prefix ratios `c_l = C_<l/S0`; α=0 recovers the
original NSC bit-for-bit, and every analysis choice is machine-checked
(18 checks, 7 mutation tests).

## Environment

- Python **3.9+** (developed on 3.14.6; see the interpreter note below),
  **no third-party dependencies** (`requirements.txt` is a comment).
- CPU only; the full acceptance suite runs in ~15 s on a laptop.

> Interpreter note (D0-1): `expected_development.json`'s random-baseline
> `sd_best_ppl` differs by exactly 1 ULP on Python ≥ 3.11 because CPython
> changed `statistics.pstdev`'s accumulation (the fixture value is the
> correctly rounded one, reproduced bitwise on 3.9/3.10). CH03 encodes this
> documented artifact; every other field is bit-exact everywhere. See
> `docs/reproduction.md` §5.

## Quick start

```sh
python3 check_starter.py                                   # official self-check
python3 evaluate.py --split development                    # baseline + our scorer
python3 checks/run_checks.py                               # 18/18 checks
python3 checks/run_checks.py --mutations                   # 7/7 seeded bugs caught
python3 -m unittest discover -s tests -t .                 # 96 tests (unittest)
```

> Note: a full `checks/run_checks.py` rewrites `results/checks.json`
(timestamp/git_commit), so `git status` showing that one modified file
afterwards is expected — use `--no-write` for verification runs.

## Exact reproduction commands

Every result in the repository traces to one of these commands (measured on
the dev machine; times are wall-clock):

| Command | Expected | Time |
|---|---|---|
| `python3 check_starter.py` | `PASS: MP identities/convergence, ...` + toy `121.820169804` / `96.957958136 vs 85.772296570` | 0.27 s |
| `python3 evaluate.py --split development --output results/dev_with_scorer.json` | 6-row ranking table; `100 development architectures; 8 budget/k combinations` | 0.44 s |
| `python3 tools/compare_expected.py results/dev_with_scorer.json expected_development.json` | `PARITY OK` on ≤3.10; `PARITY OK (D0-1: 1 tolerated ULP at …)` on ≥3.11; `--strict` enforces pure bitwise | <0.1 s |
| `python3 -m unittest discover -s tests -t .` | `Ran 96 tests ... OK` | 1.8 s |
| `python3 checks/run_checks.py` | `18/18 checks passed`, writes `results/checks.json` | 1.8 s |
| `python3 checks/run_checks.py --mutations` | `7/7 mutations caught` | 9.0 s |
| `python3 tools/reorder_pairs.py --write results/reorder_pairs.csv` | 13-row CSV + `docs/reorder_table.md`; `pairs=9845, violations=0` | 1.4 s |
| `python3 tools/audit_data.py` | 12/12 checklist; writes `results/data_audit.csv`, `docs/data_audit.md` | 0.25 s |
| `python3 tools/show_breakdown.py config_0_j0 0.5` | per-layer A/F/c/factor; `S(0.5)=517.201199027`; `exact -> True` | <0.1 s |
| `python3 tools/weighting_diagnostic.py` | label-free M2/M3 diagnostics (mechanism.md §6) | 0.6 s |
| `python3 tools/normalization_probe.py` | C3 identity check, untouched-layer displacement | 0.3 s |
| `python3 tools/select_alpha.py --self-test` | `TIE-BREAK OK` + `SELECTION OK` | <0.1 s |
| `python3 tools/selection_ext.py --self-test` | `PARITY OK` + `PREFIX OK` + `TRIALS OK` | 0.1 s |
| `python3 tools/make_variants.py` / `--verify` | 5 grid variants / `VARIANTS OK` | <0.1 s |
| `python3 tools/check_py39.py` | `PY39 OK` | <0.5 s |

The final split (`--split final`) is run **once**, after the group's `freeze`
tag, by role B. Nothing here reads `data/final_labels.json` beyond the
official byte-level hash check.

## Repository layout

```
nsc.py evaluate.py check_starter.py expected_development.json  # starter (read-only)
student_score.py        # our scorer: ALPHA + score() + ablation()  (thin wrapper)
ctxnsc/                 # core library: specs, mp, terms, prefix, score, breakdown, adapter
checks/                 # 18-check suite + 7-mutation proof + CLI (+ fixtures under tests/fixtures)
tests/                  # 96 stdlib unit tests
tools/                  # audit, breakdown, diagnostics, alpha selector, C3 probe,
                        #   1,000-trial selection reference, variant generator, py39 gate
variants/               # fixed-alpha modules for the dev grid (evaluate.py --student)
docs/                   # reproduction, interface, mechanism, data_audit, reorder_table,
                        #   starter README archive, starter manifest (SHA-256)
results/                # generated JSON/CSV artifacts (script outputs, never hand-edited;
                        #   *_summary.json carry the aggregates mechanism.md quotes)
```

## Method in one paragraph

FFN capacity is discounted by the architecture's own accumulated preceding
capacity: `c_l = C_<l/S0` (strict prefix, the architecture's own S0 as
denominator, no clamps), factor `1/(1+α·c_l)`. The limit is `ΣA + F_1`
(the first layer is never discounted). Sensitivity to graph structure
(9,845 controlled reorderings, 0 direction violations) is reported strictly
separately from predictive validity; the mechanism's diagnostics, the
matched position-only control (M3), the C3 normalization side effect and the
1,000-trial selection protocol are documented in `docs/mechanism.md`. The
starter README (baseline conventions and official protocol) is archived at
`docs/starter_README.md`.

## References

- Zhu, Zhao, Lu. *Neural Spectral Capacity* — arXiv:2609.23087
- Javaheripi et al. *LiteTransformerSearch* — arXiv:2203.02094 (panel source)
