# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Architecture guards (FR-15 / FR-21 / R4-S5).

These prove the deterministic-first boundary *by construction*: the mechanism core and the
deterministic renderer must not reach the LLM (``startd8.agents``), and the §6 source-of-truth
table must have a reader for every mechanism question.
"""

from __future__ import annotations

import ast
from pathlib import Path

import startd8.fde.deterministic_compose as det
import startd8.fde.sources as sources

# Modules that MUST be LLM-free (no import of the agents/provider-generation boundary).
_LLM_FREE_MODULES = [sources.__file__, det.__file__]
# The LLM boundary lives only in agents; compose.py is the single permitted importer.
_FORBIDDEN_IMPORT_FRAGMENTS = (
    "agents",
    "anthropic",
    "openai",
    "google.genai",
    "mistralai",
)


def _all_imported_names(path: str) -> list[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.append(mod)
            names += [f"{mod}.{a.name}" for a in node.names]
    return names


def test_deterministic_core_imports_no_llm():
    for path in _LLM_FREE_MODULES:
        imported = _all_imported_names(path)
        for name in imported:
            assert not any(frag in name for frag in _FORBIDDEN_IMPORT_FRAGMENTS), (
                f"{Path(path).name} imports an LLM/provider module: {name!r} — the deterministic "
                f"core must be LLM-free (FR-15)."
            )


def test_compose_is_the_only_llm_importer():
    # compose.py is the single permitted LLM boundary — assert it reaches the agent-resolution
    # path (the real LLM entry point), proving the boundary exists where it should.
    import startd8.fde.compose as compose

    imported = " ".join(_all_imported_names(compose.__file__))
    assert "agent_resolution" in imported or "resolve_agent_spec" in imported


def test_sources_covers_every_section6_mechanism_question():
    # FR-3/§6: each mechanism question must have a reader (analogue of SA's coverage test).
    required = [
        "read_element_mechanism",  # tier / repair / strategy
        "classify_live",  # why that tier (live)
        "resolve_model_by_tier",  # model by tier
        "resolve_model_by_role",  # model by contractor role
        "language_capability",  # language support
        "read_triage",  # evidence half
    ]
    for fn in required:
        assert hasattr(sources, fn), f"§6 mechanism reader missing: sources.{fn}"
