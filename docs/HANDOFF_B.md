# Role B development handoff (2026-11-17)

Development experiments B1-B6 have been generated on Windows with CPython
3.10.22. The current checkout has two pre-existing portability problems;
this is **not** a claim of clean full-suite acceptance. No final evaluation
was performed. C's freeze, final scorer setting, report and remote remain C's work.

## Reproduce in the PyCharm terminal

Select `D:\AIcourseAPP\envs\nsc-role-b\python.exe` as the existing interpreter.
From the repository root, after activating that conda environment:

```bat
python -X utf8 role_b_experiments.py --stage grids
python -X utf8 role_b_experiments.py --stage analysis
python -X utf8 role_b_experiments.py --check
python -X utf8 role_b_experiments.py --stage acceptance
python -X utf8 role_b_experiments.py --stage checkout-check
```

The first command runs the ten official development harness evaluations,
both variant verifiers and both pre-specified selectors. Each harness run
took about 0.64-0.65 seconds on this machine. The second exports and validates
the main 1,000-trial experiments, the ranking table and failure analysis.
The third recomputes and compares every B analysis artifact without rewriting
it (about 2.1 seconds). `--stage all` combines grids and analysis.
The acceptance stage records **every** exit and returns 1 when any check
fails; in this checkout it takes about 24 seconds and returns 1.
It does not conceal the Windows failures.

`--stage checkout-check` clones the committed starter into a retained
temporary directory with `core.autocrlf=false`, overlays only the explicitly
named B artifacts and doc-count update, and validates them there. On this
fresh LF checkout, the official starter check passed, **18/18 checks passed**,
**7/7 mutations were caught**, and every B artifact matched a fresh
computation. Total validation work was about 20 seconds. See
`results/role_b_logs/lf_checkout.txt` for the path and raw evidence. This
does not repair the active working tree's CRLF files or A's Windows path test.

Only Python's standard library is used. The experiment entry point is at
the repository root because `tools/`, tests and core scoring belong to A.
`tools/check_docs_counts.py --fix` was run after adding the entry point;
the current source gate reports `CH15 61/61`.

## Deliverables for C

| artifact | purpose |
|---|---|
| `results/dev_grid/*.json` | ten official 200-trial harness outputs (appendix protocol) |
| `results/dev_grid_cumulative.json` | alpha grid and alpha*=2, tie_break_used=false |
| `results/dev_grid_position.json` | beta grid and beta*=1, tie_break_used=false |
| `results/dev_ranking.{json,csv}` | M1-M6 and ablation, all-pair and 180-pair size-control statistics |
| `results/selection_1000.json` | 64 cells: seven scored methods/ablation plus random, eight budget/k cells |
| `results/selection_1000_table.csv` | compact selection results for plotting/reporting |
| `results/selection_200_appendix.json` | all 64 real streams have exact 200-trial prefixes and official-harness parity |
| `results/selection_failures.csv`, `docs/selection_failures.md` | independently validated 43 failures among 56 non-random entries |
| `docs/role_b_development.md` | report-ready grids, ranking, selection, three distinct failure cases, separate C3 table |
| `results/role_b_logs/*.txt` | actual commands, raw outputs, exit codes and wall times |
| `results/role_b_acceptance.json` | machine-readable acceptance summary, including failures |

The main selection protocol has 1,000 trials for **all** methods. Seeds,
pools and canonical tie-handling match A's supplied implementation. Every
method's representative choice, pool, PPL and regret are checked again by
`tools.selection_failures.analyse`. Four corruptions of the real export
(wrong best PPL, empty pool, wrong chosen PPL and 200 trials) were rejected.
The mutation audit requires each of MU1-MU7's designated catchers, excluding
the unrelated pre-existing CH01 failure; 7/7 designated catchers were observed.

## Findings and limits

M2 at alpha=2 improves development Spearman rho from 0.969744974 to
0.972745275. Controlled tau-b declines from 0.622222222 to 0.611111111.
M3 at beta=1 has rho=0.971185119 and controlled tau-b=0.611111111.
No selection tie-break was needed when choosing either grid value.
Alpha=2 is the largest pre-specified value; this is only a grid optimum.

In the 10M, k=1 cell, M2 reduces original NSC's regret from 1.940792 PPL to
zero. The other seven cells have equal mean regret. M2 and M3 have identical
mean regret in all eight cells, so this experiment does not attribute the
gain specifically to cumulative capacity. The three distinct M2 failure
episodes are tabulated in `docs/role_b_development.md`; the full failure
tool's top-five list can contain repeated architecture choices across methods.

Do not describe these tuned development results as holdout evidence, trial
SD as training-seed uncertainty, synthetic reorder sensitivity as predictive
success, shared-cache scoring times as fair benchmarks, or total parameters
as projection-only parameters. The separate C3 table reports a normalization
side effect, not mechanism validation.

## Windows acceptance blockers for A/C

1. `check_starter.py` exits 1 and CH01 fails: Git's system
   `core.autocrlf=true` checked LF blobs out as CRLF, changing protected byte
   hashes. CH02-CH18 pass. The protected working files have not been rewritten.
   For a new checkout, use `git -c core.autocrlf=false clone <repository-url>`.
   C should make a repository-wide checkout policy explicit, without changing
   the original starter blobs or manifest. Do not bypass the hash checks.
2. `unittest` runs 113 cases with one failure:
   `tests.test_selection_failures.SelfTestTests.test_self_test_passes`.
   A's `_source_label()` uses `str(path.relative_to(REPO))`, yielding Windows
   backslashes; the committed generated example has forward slashes. The
   concrete A-owned portability fix is:

   ```diff
   -        return str(path.relative_to(REPO))
   +        return path.relative_to(REPO).as_posix()
   ```

   Apply through A, regenerate examples via their generator, then rerun its
   self-test, the full suite and mutations. This handoff does not modify A's
   generator, tests or generated example files. B's report rendering passes
   an explicit portable source label and is verified by `--check`.

`tools/make_figures.py --check`, `tools/make_report_pack.py --check`,
the standard-library gate, the doc-count gate and B artifact verification
pass. The existing report pack deliberately retains C's three B placeholders;
C should fill its report from the B deliverables, respecting the generator
ownership rule. No tags, remote, `student_score.ALPHA` or freeze choices
were changed. Existing `.idea/` is retained and excluded via `.gitignore`.

## Before final evaluation

C must set and validate `freeze.json`, coordinate the A-owned scorer's
alpha setting, and create the freeze tag. The current B entry point supports
development only; a post-freeze final export needs a separately reviewed
implementation and a single authorized execution. Do not adapt it by simply
replacing the label filename or using final outcomes to revise choices.
