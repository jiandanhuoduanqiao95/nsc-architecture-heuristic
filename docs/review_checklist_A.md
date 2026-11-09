# Role A — 16-item cross-review checklist (A8.1)

Status legend: **PASS** = verified on tag `a-scorer-handoff`; **READY** = A's tool
check exists and passes, the B/C artifact it audits does not exist yet (run
the listed command when it does); **PENDING** = needs the report/evaluator
that B/C will produce.

| # | Check (TA ref) | Status | Evidence / command |
|---|---|---|---|
| 1 | M1 calls `nsc.original_nsc`, not our reimplementation (T1-1) | PASS (harness) / READY (B's evaluator) | `evaluate.py:17,117` imports and dispatches `original_nsc` from `nsc`; when B's evaluator lands: `grep -RIn "def original_nsc\|original_nsc =" evaluator/` |
| 2 | M4 calls `nsc.position_example` (T2-2) | PASS (harness) / READY (B) | `evaluate.py:17,117` same as #1 |
| 3 | M2 = `student_score.score`; `ablation` bitwise = M1 on 200 configs (T1-1) | PASS | run 2026-10-31: `ablation == original_nsc` on 200/200; CH03 shows `student` ≡ `original_nsc` at ALPHA=0 |
| 4 | M3 = `score_with_ratios(config, β, (i+1)/L)`, not rewritten (T1-4/T2-2) | PASS (variants) / READY (B's evaluator) | `variants/m3_beta_*.py` call the primitive; `tools/make_position_variants.py --verify` → `M3 VARIANTS OK` (bitwise vs primitive + independent formula, ablation == NSC, β=0 == NSC); on B's evaluator: sample 10 configs vs `ctxnsc.score_with_ratios(cfg, β, position_ratios(L))` |
| 5 | every method passes `evaluate.canonical` (12 sig digits) (T2-4) | PASS (harness) / READY (B) | `evaluate.py:122` canonicalizes every scored method; B's evaluator must reuse `evaluate.canonical` |
| 6 | size-control: same `d_model`, `min/max(total) ≥ 0.90`, dev = 180 (T1-5/T2-5) | PASS | CH17 (independent recompute + rule string vs `expected.matched_rule`) |
| 7 | selection: same pool/k/seed scheme; random uses same pool; all methods `repeats=1000` (T2-4) | PASS (tooling) / READY (B) | `tools/selection_ext.py --self-test` → PARITY/PREFIX/TRIALS OK; on B's `selection_1000.json`: `{k: v['trials'] for ...} == 1000` |
| 8 | report's main protocol is 1,000; 200 only as prefix appendix (T1-7/T2-4) | PENDING | when the report draft exists, check the main tables say `trials: 1000` and the 200-run appears only as harness consistency |
| 9 | scorer reads no labels, no ID lookups (—) | PASS | CH14 (AST scan + runtime guard, 0 occurrences) |
| 10 | `evaluate.py` / `nsc.py` / `check_starter.py` / `expected_development.json` / `data/` unmodified (T1-1) | PASS | `git diff --stat starter-import -- nsc.py evaluate.py check_starter.py expected_development.json data` = empty; CH01 15/15 byte-exact |
| 11 | every report number traces to `results/*.json` (—) | PASS (A's material) / PENDING (C's draft) | `docs/report_pack.md`: 66 values, each with a source id; `tools/make_report_pack.py --check` + `tests/test_report_pack.py` (42 re-resolved independently); spot-check C's draft against the pack's Sources table |
| 12 | after freeze: `ALPHA`/`beta_star` equal the two dev-grid argmaxes (T1-6/T2-1) | READY | `python3 checks/run_checks.py --only CH18 --freeze` after C writes `freeze.json` + B writes `results/dev_grid_*.json` |
| 13 | M3 vs M2: identical grid/rule/tie-break (T1-4/T2-1) | READY | both grids come from the same `tools/select_alpha.py` (`--method cumulative|position`, same DEFAULT_GRID and C4 rule); diff the two `results/dev_grid_*.json`; CH18 validates `beta_star` == position-grid argmax |
| 14 | C3 has its own table; `Δc_l` identity holds (T2-3) | PASS | `results/normalization_probe.csv` + `tools/normalization_probe.py` (identity worst rel 1.37e-16 in the stable form; literal-form caveat in `docs/mechanism.md` §9) |
| 15 | ≥3 concrete selection-failure cases (who was chosen / who was best / gap / reason) (T1-8/T2-6) | READY (tool) / PENDING (B's data, C's text) | `tools/selection_failures.py` (`--self-test` → `SELECTION FAILURES OK`) turns B's `results/selection_1000.json` into who/best/gap/why rows + ≥3 candidate cases; A reviews specificity in C's report |
| 16 | 1,000-trial variance vs training-seed uncertainty stated separately (T1-7/T2-7) | PASS (draft) / PENDING (report) | `docs/mechanism.md` §10 carries the two-sentence split; final wording check on C's report |

**Summary at `a-scorer-handoff`** (16 rows): PASS 5 (rows 3, 6, 9, 10, 14) · PASS on A's side with a B/C follow-up 7 (rows 1, 2, 4, 5, 7, 11, 16) · READY 2 (rows 12, 13) · READY tool, data pending 1 (row 15) · PENDING 1 (row 8) — every
non-PASS row has a named owner and a runnable command; nothing is blocked on role A.
