"""Kickoff Experience — the deterministic, conversational/visual kickoff surface.

This package is the SDK's *own* front-end for the project-kickoff process. It is a surface
**over** the existing manifest-extraction grammar (it never defines a second grammar), and it is
generated deterministically (``$0``, no LLM) from SDK-internal config.

The architecture, settled by the reflective-requirements loop + 6 CRP rounds, separates concerns:

* **M1 (this module's ``state``)** — the read-only *canonical view-model*: one serializer over the
  extraction records that BOTH the web (M4) and the TUI (M5) consume, so cross-surface parity
  (FR-3) is a property of a single fold, not two renderers. The derived "ambiguity" label is
  computed here exactly once (R1-F8 / R1-S7).
* **M2 (``readiness``)** — wraps the concierge readiness assessment.
* **M3 (``manifest``)** — the SDK-internal step/field config (NOT a grammar kind).

Public read-only API (the data spine):
    build_kickoff_state(docs, live_schema_text=None) -> KickoffState
    field_states(result) -> list[FieldState]
"""

from __future__ import annotations

from .manifest import (
    FieldDef,
    KickoffExperienceConfig,
    LintIssue,
    StepDef,
    WriteTarget,
    default_config,
    lint_config,
)
from .readiness import (
    BUDGET_INITIAL_MS,
    BUDGET_REFRESH_MS,
    BUDGET_RENDER_MS,
    PerfSample,
    ReadinessView,
    build_readiness,
)
from .state import (
    Attention,
    Ambiguity,
    FieldState,
    KickoffState,
    SourceInventory,
    build_kickoff_state,
    classify_ambiguity,
    field_states,
    source_inventory,
)

__all__ = [
    # M1 — extraction state
    "Attention",
    "Ambiguity",
    "FieldState",
    "KickoffState",
    "SourceInventory",
    "build_kickoff_state",
    "classify_ambiguity",
    "field_states",
    "source_inventory",
    # M2 — readiness
    "BUDGET_INITIAL_MS",
    "BUDGET_REFRESH_MS",
    "BUDGET_RENDER_MS",
    "PerfSample",
    "ReadinessView",
    "build_readiness",
    # M3 — experience config
    "FieldDef",
    "KickoffExperienceConfig",
    "LintIssue",
    "StepDef",
    "WriteTarget",
    "default_config",
    "lint_config",
]
