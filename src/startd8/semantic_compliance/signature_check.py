# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic missing-required-symbol backstop (FR-17).

A named public symbol declared in the seed ``api_signatures`` that is **absent** from the
generated code is a critical, fail-worthy violation — the code is missing its primary deliverable.
Run-029 proved an LLM verdict can under-weight this (PI-001 omitted ``jobs_dashboard`` /
``job_workspace`` yet the reviewer passed it as a *low* issue, while app boot crashed). So the SCR
checks it deterministically and overrides a lenient verdict.

Runs on the **full** (untruncated) code so input truncation can't cause a false "missing."
"""

from __future__ import annotations

import ast
import re
from typing import List

# Pull the symbol name out of an api_signature entry, e.g.
#   "def jobs_dashboard(request) -> Response" -> "jobs_dashboard"
#   "async def run(x) -> None"               -> "run"
#   "class JobsRouter"                        -> "JobsRouter"
#   "router = APIRouter()"                    -> "router"
_NAME_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+(?P<fn>\w+)"
    r"|^\s*class\s+(?P<cls>\w+)"
    r"|^\s*(?P<var>\w+)\s*[:=(]"
)


def required_symbol_names(api_signatures: List[str]) -> List[str]:
    """Extract the declared public symbol names from ``api_signatures`` entries."""
    names: List[str] = []
    for sig in api_signatures or []:
        m = _NAME_RE.match(str(sig))
        if not m:
            continue
        name = m.group("fn") or m.group("cls") or m.group("var")
        if name and name not in names:
            names.append(name)
    return names


def _defined_names(code: str) -> set[str]:
    """Module-level names the code binds: defs, classes, assignments, and imported names.

    Imported names count as "present" — re-exporting a required symbol satisfies the surface and
    avoids false positives. Returns an empty set when the code does not parse (skip the backstop;
    syntax errors are the post-mortem/repair pipeline's job, not the SCR's).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()

    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def missing_required_symbols(code: str, api_signatures: List[str]) -> List[str]:
    """Required ``api_signatures`` symbol names absent from the generated code (FR-17)."""
    required = required_symbol_names(api_signatures)
    if not required:
        return []
    defined = _defined_names(code)
    if not defined:  # unparseable code → skip backstop, let the LLM verdict stand
        return []
    return [name for name in required if name not in defined]
