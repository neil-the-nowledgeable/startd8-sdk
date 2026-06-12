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
from typing import Any, List, Optional

# Pull the symbol name out of an api_signature entry, e.g.
#   "def jobs_dashboard(request) -> Response" -> "jobs_dashboard"
#   "async def run(x) -> None"               -> "run"
#   "class JobsRouter"                        -> "JobsRouter"
#   "router = APIRouter()"                    -> "router"
#
# FR-CL-3 (E1, narrowed): the forward manifest is the structured parse of
# api_signatures, so the *function/class* names are now sourced from the manifest
# contracts (``required_symbol_names_from_contracts``). This regex is retained
# only for (a) the variable/constant arm, which the manifest cannot represent as
# an api-sig-sourced symbol (OQ-5 — variable specs carry no contract), and (b) the
# no-manifest degrade path. It is therefore the lone allowlisted re-parser of
# api_signatures (FR-CL-3c).
_NAME_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+(?P<fn>\w+)"
    r"|^\s*class\s+(?P<cls>\w+)"
    r"|^\s*(?P<var>\w+)\s*[:=(]"
)


def _classify_names(api_signatures: List[str]) -> tuple[List[str], List[str]]:
    """Split api_signature symbol names into (function/class, variable/constant).

    Single pass over the one retained regex so callers can take func/class names
    from the structured contract while keeping the variable residual here.
    """
    func_class: List[str] = []
    variables: List[str] = []
    for sig in api_signatures or []:
        m = _NAME_RE.match(str(sig))
        if not m:
            continue
        fc = m.group("fn") or m.group("cls")
        if fc:
            if fc not in func_class:
                func_class.append(fc)
        elif m.group("var") and m.group("var") not in variables:
            variables.append(m.group("var"))
    return func_class, variables


def required_symbol_names(api_signatures: List[str]) -> List[str]:
    """All declared public symbol names from ``api_signatures`` (regex backstop).

    Used on the no-manifest degrade path and by parity tests. When the forward
    manifest is available the orchestrator prefers
    :func:`required_symbol_names_from_contracts` for the function/class subset and
    keeps only :func:`variable_symbol_names` from here (FR-CL-3 narrowed E1).
    """
    func_class, variables = _classify_names(api_signatures)
    names: List[str] = list(func_class)
    for v in variables:
        if v not in names:
            names.append(v)
    return names


def variable_symbol_names(api_signatures: List[str]) -> List[str]:
    """Variable/constant names from ``api_signatures`` — the residual the manifest
    cannot carry (OQ-5). Kept on the regex by design (FR-CL-3 narrowed E1)."""
    _func_class, variables = _classify_names(api_signatures)
    return variables


def required_symbol_names_from_contracts(
    contracts: List[Any],
    feature_id: Optional[str],
) -> List[str]:
    """Function/class symbol names from the api-sig-derived manifest contracts.

    The structured authority for the function/class subset (E1): the extractor
    already parsed ``api_signatures`` into ``InterfaceContract``s tagged
    ``source_reference == "deterministic"``; reading those here removes the SCR's
    duplicate parse of the same raw strings. Scoped to the feature via
    ``applicable_task_ids`` (empty list = project-wide). Dotted method names
    (``Foo.bar``) are skipped — they are not module-level symbols the backstop
    checks. Variable/constant contracts do not exist (OQ-5), so variables are not
    returned here; the caller unions :func:`variable_symbol_names`.
    """
    names: List[str] = []
    for c in contracts or []:
        if getattr(c, "source_reference", None) != "deterministic":
            continue
        applicable = getattr(c, "applicable_task_ids", None) or []
        if applicable and feature_id is not None and feature_id not in applicable:
            continue
        name = getattr(c, "function_name", None) or getattr(c, "class_name", None)
        if not name or "." in name:  # skip methods (non-module-level)
            continue
        if name not in names:
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


def missing_required_symbols(
    code: str,
    api_signatures: List[str],
    *,
    contracts: Optional[List[Any]] = None,
    feature_id: Optional[str] = None,
) -> List[str]:
    """Required ``api_signatures`` symbol names absent from the generated code (FR-17).

    When ``contracts`` (the run's forward-manifest contracts) are supplied, the
    function/class names come from that structured contract and only the
    variable/constant residual is taken from the regex (FR-CL-3 narrowed E1). With
    no contracts the full regex backstop is used unchanged (degrade path).
    """
    if contracts is not None:
        required = list(
            dict.fromkeys(
                required_symbol_names_from_contracts(contracts, feature_id)
                + variable_symbol_names(api_signatures)
            )
        )
    else:
        required = required_symbol_names(api_signatures)
    if not required:
        return []
    defined = _defined_names(code)
    if not defined:  # unparseable code → skip backstop, let the LLM verdict stand
        return []
    return [name for name in required if name not in defined]
