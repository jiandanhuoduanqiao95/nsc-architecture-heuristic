"""The single source of truth for the Python 3.9 / stdlib-only rule (CH15).

Both ``tools/check_py39.py`` (manual CLI) and ``checks/checks.py`` (CH15)
call these functions; the rule itself must not be duplicated.

Two checks per file:

1. Syntax: ``ast.parse(source, feature_version=(3, 9))`` — rejects any
   post-3.9 grammar (match statements, ``X | Y`` annotations, ...).
2. Imports: every top-level import root must be standard library (or
   ``__future__``) or a module of this repository. Third-party roots are
   reported by name.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LOCAL_ROOTS = {"nsc", "evaluate", "check_starter", "student_score",
               "ctxnsc", "checks", "tests", "tools", "variants"}

# Fallback for Python 3.9, which lacks sys.stdlib_module_names. Verified by
# running CH15 under a real 3.9 interpreter (self-review R1/SR-1): any import
# root our repo uses must be listed here or CH15 fails on 3.9 only.
_FALLBACK_STDLIB = {
    "__future__", "argparse", "array", "ast", "asyncio", "base64", "bisect",
    "builtins", "calendar", "cmath", "collections", "concurrent", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib",
    "fractions",
    "enum", "functools", "gc", "getopt", "gettext", "glob", "gzip", "hashlib",
    "heapq", "html", "http", "importlib", "inspect", "io", "itertools", "json",
    "keyword",
    "linecache", "locale", "logging", "math", "mimetypes", "multiprocessing",
    "numbers", "operator", "os", "pathlib", "pdb", "pickle", "platform",
    "pprint", "queue", "random", "re", "reprlib", "shutil", "signal",
    "site", "socket", "sqlite3", "ssl", "stat", "statistics", "string",
    "struct", "subprocess", "sys", "tarfile", "tempfile", "textwrap",
    "threading", "time", "timeit", "tkinter", "traceback", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid", "warnings", "wave", "weakref",
    "xml", "zipfile", "zipimport", "zlib",
}


def stdlib_names():
    names = getattr(sys, "stdlib_module_names", None)
    return set(names) | {"__future__"} if names else set(_FALLBACK_STDLIB)


def iter_repo_py_files(root=None):
    root = Path(root) if root else REPO
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        yield path


def scan_file(path):
    """Return (syntax_errors, import_violations) for one .py file."""
    source = path.read_text(encoding="utf-8")
    syntax_errors, violations = [], []
    try:
        tree = ast.parse(source, filename=str(path), feature_version=(3, 9))
    except SyntaxError as exc:
        return [f"{path}: syntax not Python 3.9: {exc}"], []
    allowed = stdlib_names() | LOCAL_ROOTS
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the repo: always local
                continue
            roots = [node.module.split(".")[0]] if node.module else []
        else:
            continue
        for root in roots:
            if root not in allowed:
                violations.append(f"{path}: import {root!r} is not stdlib "
                                  f"or local (line {node.lineno})")
    return syntax_errors, violations


def scan_tree(root=None):
    """Scan every repo .py file; return the combined violation list."""
    errors = []
    for path in iter_repo_py_files(root):
        syntax, imports = scan_file(path)
        errors.extend(syntax)
        errors.extend(imports)
    return errors
