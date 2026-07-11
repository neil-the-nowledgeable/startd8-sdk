# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Heading-injection sanitization for the Requirements Panel (FR-RP-7).

The implementation now lives in the shared toolkit (``persona_drafting.sanitize``, FR-PD-1); this module
re-exports it so existing ``requirements_panel.sanitize`` imports keep working (P2 — no behavior change).
"""

from __future__ import annotations

from startd8.persona_drafting.sanitize import (
    ATX_HEADING_RE,
    SETEXT_RE,
    has_unsafe_heading,
    neutralize_headings,
)

__all__ = ["ATX_HEADING_RE", "SETEXT_RE", "neutralize_headings", "has_unsafe_heading"]
