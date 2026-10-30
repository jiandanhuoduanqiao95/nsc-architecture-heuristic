"""Eighteen numerical/invariant checks for the G045 scorer (A3).

Every check returns a ``CheckResult`` and must be able to fail: the mutation
suite (``checks/mutations.py``) proves each of the seven seeded bugs is caught.
Checks call the scoring functions through the ``ctxnsc.score`` /
``ctxnsc.terms`` / ``ctxnsc.breakdown`` module namespaces at call time (never
via ``from ... import`` bindings made at import time) so that in-process
monkeypatching by the mutation suite is actually observed.

Tolerance ladder (plan A3): bitwise for identities against the starter,
1e-15 for prefix identities, 1e-14 for reorder NSC equality, 1e-9 for the
alpha limit and toy anchors. CH03 is version-aware (see its docstring and
docs/reproduction.md D0-1).
"""
from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ctxnsc  # noqa: E402
import evaluate  # noqa: E402
import nsc  # noqa: E402
from checks.parity import compare_payloads, post_freeze_violations  # noqa: E402
from tools import reorder_pairs  # noqa: E402

# Submodule handles via importlib: ctxnsc/__init__ re-exports a FUNCTION named
# ``breakdown``, which shadows the submodule attribute, so getattr on the
# package is not a safe way to reach the modules (mutation patching needs the
# real module objects).
score_mod = importlib.import_module("ctxnsc.score")
terms_mod = importlib.import_module("ctxnsc.terms")
breakdown_mod = importlib.import_module("ctxnsc.breakdown")
prefix_mod = importlib.import_module("ctxnsc.prefix")
adapter_mod = importlib.import_module("ctxnsc.adapter")

SIZE_CONTROL_MIN_RATIO = 0.90  # MU6 mutates this module global
ALPHA_PROBE = (0.0, 0.25, 0.5, 1.0, 2.0)
ALPHA_LIMIT_PROBE = 1e12
FREEZE_KEYS = {"alpha_star", "beta_star", "alpha_grid", "beta_grid",
               "selection_rule", "tie_break", "tie_handling",
               "size_control_rule", "trials", "pool_rule", "metrics",
               "figures"}
REFERENCE_GRID = [0.0, 0.25, 0.5, 1.0, 2.0]

# Toy anchors (plan §1.7).
TOY_NSC = 121.820169804017
POSITION_LATE_LARGE = 96.957958136308   # FFN [256, 512]
POSITION_EARLY_LARGE = 85.772296569717  # FFN [512, 256]
TOY_PARAMS = 327680
TOY_MACS = 524288
TOY_FLOPS = 1048576

_DATASET: Optional[dict] = None


def load_dataset() -> dict:
    """Read the archive once per process (labels: development only)."""
    global _DATASET
    if _DATASET is not None:
        return _DATASET
    data = REPO / "data"
    configs = json.loads((data / "architectures.json").read_text())
    splits = json.loads((data / "splits.json").read_text())
    dev_labels = json.loads((data / "development_labels.json").read_text())
    expected = json.loads((REPO / "expected_development.json").read_text())
    manifest = []
    for line in (REPO / "docs" / "starter_manifest.sha256").read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            manifest.append((name.strip(), digest))
    provenance = json.loads((data / "provenance.json").read_text())
    _DATASET = {"configs": configs, "splits": splits,
                "dev_labels": dev_labels, "expected": expected,
                "manifest": manifest, "provenance": provenance}
    return _DATASET


@dataclass
class CheckResult:
    """Outcome of one check.

    ``n_failed`` counts FAILING CASES (never failure messages); ``failures``
    is a human-readable display list and may be shorter than n_failed (e.g.
    CH11 shows only the first violating pairs). Invariant, asserted by
    ``run_checks.py``: 0 <= n_failed <= n_cases.
    """

    id: str
    name: str
    passed: bool
    n_cases: int
    n_failed: int
    tolerance: str
    detail: str
    failures: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "passed": self.passed,
                "n_cases": self.n_cases, "n_failed": self.n_failed,
                "tolerance": self.tolerance, "detail": self.detail,
                "failures": self.failures}


def make_result(cid, name, failures, n_cases, tolerance, detail):
    """For checks where one failing case produces exactly one entry."""
    return CheckResult(id=cid, name=name, passed=not failures,
                       n_cases=n_cases, n_failed=len(failures),
                       tolerance=tolerance, detail=detail, failures=failures)


def spec_terms(cfg):
    """Fresh spec/terms/ratios through the (patchable) ctxnsc modules."""
    spec = adapter_mod.spec_from_config(cfg)
    terms = terms_mod.per_layer_terms(spec)
    return spec, terms


# ---------------------------------------------------------------------------
# CH01 starter_integrity
# ---------------------------------------------------------------------------

def ch01_starter_integrity(dataset, ctx) -> CheckResult:
    failures = []
    for name, digest in dataset["manifest"]:
        path = REPO / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            failures.append(f"{name}: sha256 {actual} != manifest {digest}")
    for name, expected_digest in dataset["provenance"]["hashes"].items():
        actual = hashlib.sha256((REPO / "data" / name).read_bytes()).hexdigest()
        if actual != expected_digest:
            failures.append(f"data/{name}: sha256 != provenance hash")
    return make_result("CH01", "starter_integrity", failures,
                       len(dataset["manifest"]) + len(dataset["provenance"]["hashes"]),
                       "byte-exact", "manifest + provenance hashes verified")


# ---------------------------------------------------------------------------
# CH02 toy_conventions
# ---------------------------------------------------------------------------

def ch02_toy_conventions(dataset, ctx) -> CheckResult:
    failures = []
    cfg = {"d_model": 128, "n_layer": 2, "n_head": [4, 4],
           "d_inner": [256, 512], "weight_init_std": 0.02}
    reverse = copy.deepcopy(cfg)
    reverse["d_inner"].reverse()
    for tag, c, expected_nsc, expected_pos in (
            ("late", cfg, TOY_NSC, POSITION_LATE_LARGE),
            ("early", reverse, TOY_NSC, POSITION_EARLY_LARGE)):
        if not math.isclose(nsc.original_nsc(c), expected_nsc, rel_tol=1e-9):
            failures.append(f"toy[{tag}]: original_nsc != {expected_nsc}")
        if not math.isclose(nsc.position_example(c), expected_pos, rel_tol=1e-9):
            failures.append(f"toy[{tag}]: position_example != {expected_pos}")
    res = nsc.resource_estimate(cfg)
    for field_name, expected in (("projection_parameters", TOY_PARAMS),
                                 ("reference_macs_per_token", TOY_MACS),
                                 ("reference_flops_per_token", TOY_FLOPS)):
        if res[field_name] != expected:
            failures.append(f"toy resource {field_name}: {res[field_name]} != {expected}")
    return make_result("CH02", "toy_conventions", failures, 7, "relative 1e-9",
                       "toy NSC/position anchors + resource arithmetic")


# ---------------------------------------------------------------------------
# CH03 expected_dev_parity (version-aware, D0-1; shared comparator)
# ---------------------------------------------------------------------------

def parity_failure_entries(expected, actual, alpha):
    """Comparator + post-freeze filtering + case accounting for CH03.

    Returns (failures, violations, tolerated, n_sd_checked) where ``failures``
    has at most one entry per case (main compare / two reverse probes are
    handled by the caller), so n_failed <= n_cases always holds.
    """
    violations, tolerated, n_sd_checked = compare_payloads(expected, actual)
    if alpha != 0.0:
        # Post-freeze: student/ablation diffs are the expected effect of the
        # tuned scorer; EVERYTHING else (baseline methods, random baselines,
        # eligible/oracle_ppl, structure) must still be bit-equal.
        violations = post_freeze_violations(violations)
    failures = []
    if violations:
        shown = "; ".join(violations[:3])
        more = "" if len(violations) <= 3 else f" (+{len(violations) - 3} more)"
        failures.append(f"field parity: {len(violations)} differing field(s): "
                        f"{shown}{more}")
    return failures, violations, tolerated, n_sd_checked


def ch03_expected_dev_parity(dataset, ctx) -> CheckResult:
    student_path = REPO / "student_score.py"
    actual = evaluate.evaluate("development", student_path)
    expected = dataset["expected"]
    module_spec = importlib.util.spec_from_file_location(
        "student_module_ch03", student_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    alpha = float(getattr(module, "ALPHA", 0.0))
    failures, violations, tolerated, n_sd = parity_failure_entries(
        expected, actual, alpha)
    if alpha != 0.0:
        detail = (f"ALPHA={alpha:g}: post-freeze — baselines (4 methods, "
                  f"random, eligible/oracle_ppl) must match; "
                  f"student/ablation recorded as changed")
    else:
        detail = ("full parity" if not tolerated else
                  f"parity; differing-but-tolerated field(s): "
                  + "; ".join(tolerated))

    # Reverse tests: prove the comparator still bites (meaningful only when
    # the main comparison is a full-parity one, i.e. ALPHA == 0).
    if not failures and alpha == 0.0:
        probe = copy.deepcopy(expected)
        rho = probe["ranking"]["original_nsc"]["spearman_rho"]
        probe["ranking"]["original_nsc"]["spearman_rho"] = math.nextafter(rho, math.inf)
        rev_violations, _t, _n = compare_payloads(probe, actual)
        if not rev_violations:
            failures.append("reverse test failed: 1-ULP perturbation of a "
                            "non-tolerated field was NOT rejected")
        probe = copy.deepcopy(expected)
        sd = probe["selection"][0]["methods"]["random"]["sd_best_ppl"]
        two_up = math.nextafter(math.nextafter(sd, math.inf), math.inf)
        probe["selection"][0]["methods"]["random"]["sd_best_ppl"] = two_up
        rev_violations, _t, _n = compare_payloads(probe, actual)
        if not rev_violations:
            failures.append("reverse test failed: 2-ULP perturbation of "
                            "sd_best_ppl was NOT rejected")
    return make_result("CH03", "expected_dev_parity", failures, 3,
                       "bitwise (D0-1: 1 ULP)", detail)


# ---------------------------------------------------------------------------
# CH04 layer_identity / CH05 alpha0_exact
# ---------------------------------------------------------------------------

def ch04_layer_identity(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    for key in sorted(configs):
        cfg = configs[key]
        _spec, terms = spec_terms(cfg)
        caps = nsc.layer_capacities(cfg)
        problems = []
        for l, (term, cap) in enumerate(zip(terms, caps)):
            if term.attn + term.ffn != cap:
                problems.append(f"layer {l + 1} A+F {term.attn + term.ffn!r} "
                                f"!= layer_capacities {cap!r}")
                break
        if not problems and math.fsum(t.attn + t.ffn for t in terms) \
                != nsc.original_nsc(cfg):
            problems.append("fsum(A+F) != original_nsc")
        if problems:  # one entry per failing case (= per config)
            failures.append(f"{key}: " + "; ".join(problems))
    return make_result("CH04", "layer_identity", failures, len(configs),
                       "bitwise", "200 configs, elementwise vs nsc.layer_capacities")


def ch05_alpha0_exact(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    for key in sorted(configs):
        cfg = configs[key]
        if score_mod.score_config(cfg, 0.0) != nsc.original_nsc(cfg):
            failures.append(f"{key}: S(0) != original_nsc")
    return make_result("CH05", "alpha0_exact", failures, len(configs),
                       "bitwise", "S(0) bit-identical to nsc.original_nsc")


# ---------------------------------------------------------------------------
# CH06 finite_positive / CH07 prefix_properties
# ---------------------------------------------------------------------------

def ch06_finite_positive(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    for key in sorted(configs):
        cfg = configs[key]
        spec, terms = spec_terms(cfg)
        ratios = prefix_mod.cumulative_ratios(terms)
        s0 = prefix_mod.s0_from_terms(terms)
        problems = []
        if not (math.isfinite(s0) and s0 > 0.0):
            problems.append("S0 not finite/positive")
        if not all(math.isfinite(c) for c in ratios):
            problems.append("non-finite ratio")
        for alpha, score in score_mod.scores_for_alphas(cfg, ALPHA_PROBE).items():
            if not (math.isfinite(score) and score > 0.0):
                problems.append(f"S(alpha={alpha}) not finite/positive")
        if problems:  # one entry per failing case (= per config)
            failures.append(f"{key}: " + "; ".join(problems))
    return make_result("CH06", "finite_positive", failures, len(configs),
                       "isfinite", "S0>0, ratios finite, 5 alphas finite>0")


def ch07_prefix_properties(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    for key in sorted(configs):
        cfg = configs[key]
        _spec, terms = spec_terms(cfg)
        ratios = prefix_mod.cumulative_ratios(terms)
        if ratios[0] != 0.0:
            failures.append(f"{key}: ratios[0] = {ratios[0]!r} != 0.0")
            continue
        problems = []
        if any(a >= b for a, b in zip(ratios, ratios[1:])):
            problems.append("ratios not strictly increasing")
        if not ratios[-1] < 1.0:
            problems.append(f"ratios[-1] = {ratios[-1]!r} >= 1")
        s0 = prefix_mod.s0_from_terms(terms)
        expected_last = 1.0 - (terms[-1].attn + terms[-1].ffn) / s0
        if abs(ratios[-1] - expected_last) > 1e-15:
            problems.append(f"ratios[-1] != 1-(A_L+F_L)/S0 "
                            f"(|d|={abs(ratios[-1] - expected_last):.2e})")
        if problems:  # one entry per failing case (= per config)
            failures.append(f"{key}: " + "; ".join(problems))
    return make_result("CH07", "prefix_properties", failures, len(configs),
                       "bitwise / 1e-15", "strict prefixes, c_1=0, c_L<1")


# ---------------------------------------------------------------------------
# CH08 single_layer
# ---------------------------------------------------------------------------

def ch08_single_layer(dataset, ctx) -> CheckResult:
    failures = []
    n_cases = 0
    for d in (64, 128, 256, 512):
        for h in (1, 2, 4, 8):
            if d % h:
                continue
            for f in (64, 1024):
                n_cases += 1
                cfg = {"d_model": d, "n_layer": 1, "n_head": h, "d_inner": f,
                       "weight_init_std": 0.02}
                _spec, terms = spec_terms(cfg)
                ratios = prefix_mod.cumulative_ratios(terms)
                s0 = prefix_mod.s0_from_terms(terms)
                tag = f"L1 d={d} h={h} f={f}"
                problems = []
                if ratios != [0.0]:
                    problems.append(f"ratios {ratios} != [0.0]")
                if s0 != nsc.original_nsc(cfg):
                    problems.append("S0 != original_nsc")
                for alpha in ALPHA_PROBE:
                    if score_mod.score_config(cfg, alpha) != s0:
                        problems.append(f"S({alpha}) != S0")
                if problems:  # one entry per failing case
                    failures.append(f"{tag}: " + "; ".join(problems))
    return make_result("CH08", "single_layer", failures, n_cases,
                       "bitwise", "single-layer S(alpha) == S0 for all alpha")


# ---------------------------------------------------------------------------
# CH09 alpha_monotone / CH10 alpha_limit
# ---------------------------------------------------------------------------

def ch09_alpha_monotone(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    strictly = 0
    for key in sorted(configs):
        cfg = configs[key]
        scores = [score_mod.score_config(cfg, a) for a in ALPHA_PROBE]
        problems = []
        if any(b > a for a, b in zip(scores, scores[1:])):
            problems.append("S(alpha) increases somewhere")
        if cfg["n_layer"] >= 2 and all(b == a for a, b in zip(scores, scores[1:])):
            problems.append("S(alpha) constant for L>=2")
        if any(b < a for a, b in zip(scores, scores[1:])):
            strictly += 1
        if problems:  # one entry per failing case (= per config)
            failures.append(f"{key}: " + "; ".join(problems))
    detail = f"strictly decreasing on {strictly}/{len(configs)} configs"
    return make_result("CH09", "alpha_monotone", failures, len(configs),
                       "1e-15", detail)


def ch10_alpha_limit(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    worst = 0.0
    for key in sorted(configs):
        cfg = configs[key]
        _spec, terms = spec_terms(cfg)
        expected = math.fsum(t.attn for t in terms) + terms[0].ffn
        value = score_mod.score_config(cfg, ALPHA_LIMIT_PROBE)
        rel = abs(value - expected) / abs(expected)
        worst = max(worst, rel)
        sum_attn = math.fsum(t.attn for t in terms)
        problems = []
        if rel > 1e-9:
            problems.append(f"S(1e12) rel err {rel:.2e} vs sum(A)+F_1")
        if abs(value - sum_attn) <= 1e-3 * abs(expected - sum_attn):
            problems.append("S(1e12) collapsed to sum(A) (limit bug)")
        if problems:  # one entry per failing case (= per config), even if
            failures.append(f"{key}: " + "; ".join(problems))  # both sub-checks hit
    return make_result("CH10", "alpha_limit", failures, len(configs), "1e-9",
                       f"max rel err {worst:.2e} vs sum(A)+F_1")


# ---------------------------------------------------------------------------
# CH11 reorder_controls
# ---------------------------------------------------------------------------

def ch11_reorder_controls(dataset, ctx) -> CheckResult:
    failures = []
    # toy pair: full S(alpha) table from plan 1.7 (rel 1e-9) + invariants
    toy_expected = {
        (0.0, "late"): 121.820169804, (0.0, "early"): 121.820169804,
        (0.25, "late"): 117.487538338, (0.25, "early"): 118.672843897,
        (0.5, "late"): 113.889274555, (0.5, "early"): 116.244184056,
        (1.0, "late"): 108.257252069, (1.0, "early"): 112.741286801,
        (2.0, "late"): 100.790156278, (2.0, "early"): 108.583607933,
        (ALPHA_LIMIT_PROBE, "late"): 75.029376696,
        (ALPHA_LIMIT_PROBE, "early"): 97.400699829,
    }
    toy_problems = []
    for (alpha, tag), expected in toy_expected.items():
        cfg = reorder_pairs.TOY_A if tag == "late" else reorder_pairs.TOY_B
        if not math.isclose(score_mod.score_config(cfg, alpha), expected,
                            rel_tol=1e-9):
            toy_problems.append(f"toy[{tag}] S({alpha:g}) != {expected}")
    info = reorder_pairs.pair_scores(reorder_pairs.TOY_A, reorder_pairs.TOY_B, 0.5)
    if info["projection_params"] != TOY_PARAMS or info["reference_macs"] != TOY_MACS:
        toy_problems.append("toy pair: resource invariants broken")
    if not info["s_a05_after"] > info["s_a05"]:
        toy_problems.append("toy pair: direction violated at alpha=0.5")

    configs = dataset["configs"]
    count, sweep = reorder_pairs.full_sweep_violations(0.5, configs=configs)
    violating_pairs = sorted({pair_key for pair_key, _msg in sweep})
    # The toy pair is ONE case; collapse its sub-findings into one entry.
    toy_failures = [f"{len(toy_problems)} toy findings: "
                    + "; ".join(toy_problems[:4])] if toy_problems else []
    failures = toy_failures + [f"{pair_key}: " + msg
                               for pair_key, msg in sweep[:10]]
    if len(sweep) > 10:
        failures.append(f"... {len(sweep) - 10} more violation entries on "
                        f"{len(violating_pairs)} pairs")
    n_failed = len(toy_failures) + len(violating_pairs)
    detail = (f"toy table + {count} full-panel layer pairs "
              f"(dev 4,961 + final 4,884 = 9,845; structure only, no final "
              f"label file read; n = 1 + 9,845 = 9,846), "
              f"{len(sweep)} violation entries on {len(violating_pairs)} pairs")
    return CheckResult(id="CH11", name="reorder_controls",
                       passed=n_failed == 0, n_cases=1 + count,
                       n_failed=n_failed, tolerance="1e-14 / exact",
                       detail=detail, failures=failures)


# ---------------------------------------------------------------------------
# CH12 width_monotone
# ---------------------------------------------------------------------------

def ch12_width_monotone(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    widths = sorted({cfg["d_model"] for cfg in configs.values()})
    for d in widths:
        f_values = sorted({f for cfg in configs.values() if cfg["d_model"] == d
                           for f in (cfg["d_inner"] if isinstance(cfg["d_inner"], list)
                                     else [cfg["d_inner"]])})
        caps = [2 * nsc.psi_mp(d, f) for f in f_values]
        if any(b <= a for a, b in zip(caps, caps[1:])):
            failures.append(f"d={d}: F(d,f) not strictly increasing over "
                            f"{len(f_values)} observed widths")
    return make_result("CH12", "width_monotone", failures, len(widths),
                       "strict", "F(d,f)=2psi(d,f) increasing per width")


# ---------------------------------------------------------------------------
# CH13 determinism
# ---------------------------------------------------------------------------

DETERMINISM_SCRIPT = (
    "import json, sys; sys.path.insert(0, '.'); import ctxnsc, nsc\n"
    "configs = json.load(open('data/architectures.json'))\n"
    "keys = sorted(configs)[:5]\n"
    "print(repr([ctxnsc.score_config(configs[k], 0.5) for k in keys]))\n"
    "print(repr([nsc.original_nsc(configs[k]) for k in keys]))\n"
)


def ch13_determinism(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    keys = sorted(configs)[:5]
    first = [score_mod.score_config(configs[k], 0.5) for k in keys]
    second = [score_mod.score_config(configs[k], 0.5) for k in keys]
    if repr(first) != repr(second):
        failures.append("same-process repr differs between two runs")
    outputs = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        # NB: no -I/-E here — both would ignore PYTHONHASHSEED entirely.
        proc = subprocess.run([sys.executable, "-c", DETERMINISM_SCRIPT],
                              cwd=str(REPO), env=env, capture_output=True,
                              text=True, timeout=120)
        if proc.returncode != 0:
            failures.append(f"subprocess PYTHONHASHSEED={seed} failed: "
                            f"{proc.stderr.strip()[:200]}")
        outputs.append(proc.stdout)
    if len(outputs) == 2 and outputs[0] != outputs[1]:
        failures.append("subprocess outputs differ across PYTHONHASHSEED 0/1")
    return make_result("CH13", "determinism", failures, 3, "bitwise",
                       "in-process repr + two subprocess hash seeds")


# ---------------------------------------------------------------------------
# CH14 no_label_access
# ---------------------------------------------------------------------------

LABEL_CALL_ATTRS = {"open", "read_text", "read_bytes"}


def ast_label_violations(paths) -> List[str]:
    violations = []
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in LABEL_CALL_ATTRS:
                    literals = [a.value for a in node.args
                                if isinstance(a, ast.Constant)
                                and isinstance(a.value, str)]
                    literals += [kw.value.value for kw in node.keywords
                                 if isinstance(kw.value, ast.Constant)
                                 and isinstance(kw.value, str)]
                    if any("label" in s.lower() for s in literals):
                        violations.append(f"{path}: line {node.lineno} opens a "
                                          f"label-looking literal {literals}")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names]
                if node.__class__.__name__ == "ImportFrom" and node.module:
                    names.append(node.module)
                if any("label" in n.lower() for n in names):
                    violations.append(f"{path}: imports label module {names}")
    return violations


def ch14_no_label_access(dataset, ctx) -> CheckResult:
    targets = sorted((REPO / "ctxnsc").glob("*.py")) + [REPO / "student_score.py"]
    violations = ast_label_violations(targets)
    # runtime guard: scoring must not open any file
    opened = []
    real_open = builtins.open

    def guarded_open(*args, **kwargs):
        opened.append(args[0] if args else kwargs.get("file"))
        raise AssertionError("scorer opened a file during scoring")

    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def guarded_read_text(self, *args, **kwargs):
        opened.append(str(self))
        raise AssertionError("scorer read a file during scoring")

    def guarded_read_bytes(self, *args, **kwargs):
        opened.append(str(self))
        raise AssertionError("scorer read a file during scoring")

    builtins.open = guarded_open
    Path.read_text = guarded_read_text
    Path.read_bytes = guarded_read_bytes
    try:
        configs = dataset["configs"]
        for key in sorted(configs)[:5]:
            score_mod.score_config(configs[key], 0.5)
    finally:
        builtins.open = real_open
        Path.read_text = real_read_text
        Path.read_bytes = real_read_bytes
    if opened:
        failures.append(f"runtime guard caught {len(opened)} file opens")
    # n_failed counts the two CASES (AST scan / runtime guard), not messages.
    n_failed = (1 if violations else 0) + (1 if opened else 0)
    return CheckResult(id="CH14", name="no_label_access", passed=n_failed == 0,
                       n_cases=2, n_failed=n_failed, tolerance="0 occurrences",
                       detail=(f"AST scan of ctxnsc/+student_score "
                               f"({len(violations)} findings) and runtime "
                               f"guard over 5 configs ({len(opened)} opens)"),
                       failures=violations + (["runtime guard caught "
                                               f"{len(opened)} file opens"]
                                              if opened else []))


# ---------------------------------------------------------------------------
# CH15 python39_stdlib
# ---------------------------------------------------------------------------

def ch15_python39_stdlib(dataset, ctx) -> CheckResult:
    from checks.py39_rules import iter_repo_py_files, scan_file
    files = list(iter_repo_py_files())
    by_file = {}
    for path in files:
        syntax, imports = scan_file(path)
        if syntax or imports:
            by_file[str(path)] = syntax + imports
    # n_failed counts failing FILES (one case per file); all findings shown.
    display = [finding for findings in by_file.values() for finding in findings]
    return CheckResult(id="CH15", name="python39_stdlib",
                       passed=not by_file, n_cases=len(files),
                       n_failed=len(by_file), tolerance="0 violations",
                       detail=(f"{len(files)} .py files parse as 3.9, "
                               f"stdlib-only imports"),
                       failures=display)


# ---------------------------------------------------------------------------
# CH16 breakdown_consistency
# ---------------------------------------------------------------------------

def ch16_breakdown_consistency(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    keys = sorted(configs)[:: max(1, len(configs) // 20)][:20]
    n_cases = 0
    for key in keys:
        cfg = configs[key]
        _spec, terms = spec_terms(cfg)
        ratios = prefix_mod.cumulative_ratios(terms)
        for alpha in ALPHA_PROBE:
            n_cases += 1
            bd = breakdown_mod.breakdown(terms, alpha)
            problems = []
            if bd.total != score_mod.score_config(cfg, alpha):
                problems.append("breakdown total != score")
            if bd.s0 != nsc.original_nsc(cfg):
                problems.append("breakdown S0 != original_nsc")
            if math.fsum(item.contribution for item in bd.items) != bd.total:
                problems.append("fsum(contributions) != total")
            for item, c in zip(bd.items, ratios):
                if item.ratio != c:
                    problems.append(f"ratio mismatch layer {item.layer}")
                if item.factor != 1.0 / (1.0 + alpha * c):
                    problems.append(f"factor mismatch layer {item.layer}")
            if problems:  # one entry per failing case (= per (config, alpha))
                failures.append(f"{key} alpha={alpha}: " + "; ".join(problems))
    return make_result("CH16", "breakdown_consistency", failures, n_cases,
                       "bitwise", "20 configs x 5 alphas, contributions/ratios/factors")


# ---------------------------------------------------------------------------
# CH17 size_control_count (TA 1/2)
# ---------------------------------------------------------------------------

def ch17_size_control_count(dataset, ctx) -> CheckResult:
    failures = []
    configs = dataset["configs"]
    resources = json.loads((REPO / "data" / "resources.json").read_text())
    dev_keys = dataset["splits"]["development"]
    totals = [resources[k]["total"] for k in dev_keys]
    matched = 0
    for i in range(len(dev_keys)):
        for j in range(i):
            if (configs[dev_keys[i]]["d_model"] == configs[dev_keys[j]]["d_model"]
                    and min(totals[i], totals[j]) / max(totals[i], totals[j])
                    >= SIZE_CONTROL_MIN_RATIO):
                matched += 1
    if matched != 180:
        failures.append(f"dev size-controlled pairs = {matched} != 180")
    pools = [sum(t <= b for t in totals)
             for b in (10_000_000, 20_000_000, 30_000_000, 50_000_000)]
    if pools != [24, 65, 83, 96]:
        failures.append(f"dev pools {pools} != [24, 65, 83, 96]")
    matched_rule = dataset["expected"]["matched_rule"]
    if matched_rule != "same d_model; min(total)/max(total)>=0.90":
        failures.append(f"matched_rule drifted: {matched_rule!r}")
    n_cases = 1 + len(pools) + 1
    return make_result("CH17", "size_control_count", failures, n_cases, "exact",
                       f"pairs={matched}, pools={pools}, rule {matched_rule!r}")


# ---------------------------------------------------------------------------
# CH18 freeze_consistency (TA 1/2)
# ---------------------------------------------------------------------------

def load_freeze(mode: str) -> Tuple[dict, dict, dict]:
    """Return (freeze, dev_grid_cumulative, dev_grid_position) for the mode."""
    if mode == "strict":
        freeze = json.loads((REPO / "freeze.json").read_text())
        grid_cum = json.loads((REPO / "results" / "dev_grid_cumulative.json").read_text())
        grid_pos = json.loads((REPO / "results" / "dev_grid_position.json").read_text())
        return freeze, grid_cum, grid_pos
    fx = REPO / "tests" / "fixtures"
    freeze = json.loads((fx / "freeze_example.json").read_text())
    grid_cum = json.loads((fx / "dev_grid_cumulative_example.json").read_text())
    grid_pos = json.loads((fx / "dev_grid_position_example.json").read_text())
    return freeze, grid_cum, grid_pos


def validate_freeze(freeze, grid_cum, grid_pos, check_alpha_constant) -> List[str]:
    problems = []
    if not isinstance(freeze, dict):
        return ["freeze payload is not an object"]
    missing = FREEZE_KEYS - set(freeze)
    extra = set(freeze) - FREEZE_KEYS
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    if extra:
        problems.append(f"unexpected fields: {sorted(extra)}")
    if problems:
        return problems

    def is_number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if not is_number(freeze["alpha_star"]):
        problems.append("alpha_star is not a number")
    if not is_number(freeze["beta_star"]):
        problems.append("beta_star is not a number")
    if not isinstance(freeze["trials"], int) or isinstance(freeze["trials"], bool):
        problems.append("trials is not an integer")
    elif freeze["trials"] != 1000:
        problems.append(f"trials == {freeze['trials']} != 1000")
    for key in ("alpha_grid", "beta_grid"):
        grid = freeze[key]
        if (not isinstance(grid, list) or len(grid) != len(REFERENCE_GRID)
                or not all(is_number(v) for v in grid)
                or [float(v) for v in grid] != REFERENCE_GRID):
            problems.append(f"{key} != {REFERENCE_GRID}")
    for key in ("selection_rule", "tie_break", "tie_handling", "pool_rule"):
        if not isinstance(freeze[key], str) or not freeze[key].strip():
            problems.append(f"{key} is not a non-empty string")
    if not isinstance(freeze["metrics"], list) or not freeze["metrics"]:
        problems.append("metrics is not a non-empty list")
    if not isinstance(freeze["figures"], list) or not freeze["figures"]:
        problems.append("figures is not a non-empty list")
    rule = freeze["size_control_rule"]
    if not isinstance(rule, str) or "0.90" not in rule or "180" not in rule:
        problems.append("size_control_rule must state the 0.90 ratio and 180 pairs")
    if not problems:
        selected_cum = float(grid_cum["selected"])
        selected_pos = float(grid_pos["selected"])
        if float(freeze["alpha_star"]) != selected_cum:
            problems.append(f"alpha_star {freeze['alpha_star']} != dev grid "
                            f"cumulative argmax {selected_cum}")
        if float(freeze["beta_star"]) != selected_pos:
            problems.append(f"beta_star {freeze['beta_star']} != dev grid "
                            f"position argmax {selected_pos}")
        if grid_cum.get("grid") and [float(v) for v in grid_cum["grid"]] != REFERENCE_GRID:
            problems.append("dev grid cumulative grid != reference grid")
        if grid_pos.get("grid") and [float(v) for v in grid_pos["grid"]] != REFERENCE_GRID:
            problems.append("dev grid position grid != reference grid")
    if check_alpha_constant and not problems:
        student_path = REPO / "student_score.py"
        source = student_path.read_text()
        match = re.search(r"^ALPHA\s*=\s*([0-9.eE+-]+)\s*$", source, re.M)
        if not match:
            problems.append("student_score.py has no ALPHA constant")
        elif float(match.group(1)) != float(freeze["alpha_star"]):
            problems.append(f"student_score.ALPHA {match.group(1)} != "
                            f"freeze alpha_star {freeze['alpha_star']}")
    return problems


def ch18_freeze_consistency(dataset, ctx) -> CheckResult:
    mode = ctx["freeze_mode"]
    failures = []
    if mode == "strict":
        missing = [name for name in
                   ("freeze.json", "results/dev_grid_cumulative.json",
                    "results/dev_grid_position.json")
                   if not (REPO / name).exists()]
        if missing:
            return make_result(
                "CH18", "freeze_consistency",
                [f"strict mode: {', '.join(missing)} not found yet "
                 f"(written by B/C at G4; run --dry-run before the freeze)"],
                1, "exact", "strict: required freeze artifacts missing")
        freeze, grid_cum, grid_pos = load_freeze("strict")
        problems = validate_freeze(freeze, grid_cum, grid_pos, True)
        failures.extend(problems)
        n_cases = 1
        detail = "strict: freeze.json vs real dev grids + student_score.ALPHA"
    else:
        freeze, grid_cum, grid_pos = load_freeze("dry-run")
        problems = validate_freeze(freeze, grid_cum, grid_pos, False)
        if problems:
            failures.append(f"good fixture rejected: {problems}")
        bad_names = ["freeze_example_bad_alpha.json",
                     "freeze_example_bad_missing_field.json",
                     "freeze_example_bad_trials.json"]
        for name in bad_names:
            payload = json.loads((REPO / "tests" / "fixtures" / name).read_text())
            bad_problems = validate_freeze(payload, grid_cum, grid_pos, False)
            if not bad_problems:
                failures.append(f"bad fixture {name} was NOT rejected")
        n_cases = 4
        detail = ("dry-run: fixture schema/argmax validated; 3 bad fixtures "
                  "(wrong alpha*, missing field, trials=200) rejected")
    return make_result("CH18", "freeze_consistency", failures, n_cases, "exact",
                       detail)


CHECKS: List[Tuple[str, str, Callable]] = [
    ("CH01", "starter_integrity", ch01_starter_integrity),
    ("CH02", "toy_conventions", ch02_toy_conventions),
    ("CH03", "expected_dev_parity", ch03_expected_dev_parity),
    ("CH04", "layer_identity", ch04_layer_identity),
    ("CH05", "alpha0_exact", ch05_alpha0_exact),
    ("CH06", "finite_positive", ch06_finite_positive),
    ("CH07", "prefix_properties", ch07_prefix_properties),
    ("CH08", "single_layer", ch08_single_layer),
    ("CH09", "alpha_monotone", ch09_alpha_monotone),
    ("CH10", "alpha_limit", ch10_alpha_limit),
    ("CH11", "reorder_controls", ch11_reorder_controls),
    ("CH12", "width_monotone", ch12_width_monotone),
    ("CH13", "determinism", ch13_determinism),
    ("CH14", "no_label_access", ch14_no_label_access),
    ("CH15", "python39_stdlib", ch15_python39_stdlib),
    ("CH16", "breakdown_consistency", ch16_breakdown_consistency),
    ("CH17", "size_control_count", ch17_size_control_count),
    ("CH18", "freeze_consistency", ch18_freeze_consistency),
]


def run_checks(only=None, freeze_mode=None) -> List[CheckResult]:
    dataset = load_dataset()
    if freeze_mode is None:
        freeze_mode = "strict" if (REPO / "freeze.json").exists() else "dry-run"
    ctx = {"freeze_mode": freeze_mode}
    results = []
    for cid, name, function in CHECKS:
        if only and cid not in only:
            continue
        results.append(function(dataset, ctx))
    return results
