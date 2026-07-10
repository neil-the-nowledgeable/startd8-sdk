# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Panel-synthesis → VIPP bridge (increment 1: the NON-DECIDABLE router).

A stakeholder-panel synthesis is free-text markdown (risk register, tensions, recommendations, open
questions). This package turns it into a structured **triage**: extract the discrete items, classify
each into a lane (FIELD-LEVEL — a candidate for a VIPP ``capture`` proposal — vs NON-DECIDABLE —
narrative/governance/human-decision), and route the NON-DECIDABLE ones to a report with a reason and
a suggested owner, so nothing is silently dropped.

Increment 1 is the **always-firing, ``$0``, deterministic core**: extraction is a heuristic markdown
parse (no LLM), classification/routing are pure functions. The FIELD-LEVEL → VIPP-envelope lane
(staging + ``serialize_buffer``) is increment 2, gated on a non-empty ``allowed_value_paths()``.

Design: ``docs/design/panel-synthesis-bridge/`` (requirements v0.3 + plan v1.0).
"""

from __future__ import annotations

from .ask_all import (
    is_ask_all_session,
    list_ask_all_sessions,
    load_ask_all_session,
    triage_ask_all,
)
from .backlog import (
    AppendResult,
    BacklogAppendError,
    append_backlog,
    compute_append,
    render_backlog_section,
)
from .classify import classify, health_check
from .extract import extract_candidates
from .extract_llm import extract_field_mappings
from .kind_llm import refine_input_kinds
from .models import Candidate, InputKind, Lane, TriageReport
from .route import build_triage
from .stage import serialize_accepted_to_vipp, stage_recommendations

__all__ = [
    "Candidate",
    "InputKind",
    "Lane",
    "TriageReport",
    "extract_candidates",
    "classify",
    "health_check",
    "build_triage",
    # Q1 — ask-all triage unification (typed, role-tagged)
    "triage_ask_all",
    "list_ask_all_sessions",
    "load_ask_all_session",
    "is_ask_all_session",
    # E — residual capture + backlog render/append (FR-6/FR-7/FR-14)
    "render_backlog_section",
    "append_backlog",
    "compute_append",
    "AppendResult",
    "BacklogAppendError",
    # LLM Tier-2 (FR-12)
    "refine_input_kinds",
    # increment 2 — FIELD-LEVEL lane
    "extract_field_mappings",
    "stage_recommendations",
    "serialize_accepted_to_vipp",
]
