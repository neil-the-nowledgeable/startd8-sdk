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

from .classify import classify, health_check
from .extract import extract_candidates
from .models import Candidate, Lane, TriageReport
from .route import build_triage

__all__ = [
    "Candidate",
    "Lane",
    "TriageReport",
    "extract_candidates",
    "classify",
    "health_check",
    "build_triage",
]
