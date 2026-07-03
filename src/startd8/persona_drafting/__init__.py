# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Persona-drafting toolkit — shared primitives for the persona-drafting siblings.

Extracted (behavior-preserving) from the Requirements Panel + Stakeholder Panel so the three siblings
(Stakeholder Panel, Requirements Panel, Manifest Suggester) stop triplicating them. Deliberately
mechanics-only — grounding, synthesis, and readiness stay feature-owned (NR-PD-2). See
``docs/design/persona-drafting/PERSONA_DRAFTING_TOOLKIT_REQUIREMENTS.md``.
"""

from __future__ import annotations

from startd8.persona_drafting.owner_resolution import resolve_bounded_owner
from startd8.persona_drafting.sanitize import (
    has_unsafe_heading,
    neutralize_headings,
)
from startd8.persona_drafting.staging import JsonSessionStore, safe_session_component

__all__ = [
    "neutralize_headings",
    "has_unsafe_heading",
    "JsonSessionStore",
    "safe_session_component",
    "resolve_bounded_owner",
]
