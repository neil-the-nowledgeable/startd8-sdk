# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Lightweight post-drain checks for reflective-requirements hardening.

The VASI surface only guarantees non-empty markdown paths. These heuristics
catch the common failure mode where a drain stops after v0.2 (plan+reflect)
and skips Phase 4.5 / 4.6. They are intentionally regex-light — not a full
markdown AST — so agents can use slightly varied headings.
"""

from __future__ import annotations

import re
from typing import List

_LESSONS_HEADING = re.compile(
    r"(?im)^\s{0,3}#{1,4}\s*0\.1\b.*lessons[- ]learned",
)
_LESSONS_PHRASE = re.compile(r"(?i)lessons[- ]learned\s+hardening")
_LESSONS_NOOP = re.compile(
    r"(?i)checked.{0,120}(lessons|lesson).{0,80}"
    r"(none applicable|no applicable|n/?a)\b",
)

_PRINCIPLES_HEADING = re.compile(
    r"(?im)^\s{0,3}#{1,4}\s*0\.2\b.*design[- ]principle",
)
_PRINCIPLES_PHRASE = re.compile(r"(?i)design[- ]principle\s+hardening")
_PRINCIPLES_NOOP = re.compile(
    r"(?i)checked.{0,120}(design[- ]principle|principles?).{0,80}"
    r"(none applicable|no applicable|n/?a)\b",
)

_VERSION_031 = re.compile(
    r"(?i)(\*\*version:\*\*|version:)\s*0\.3\.1\b|\bv0\.3\.1\b",
)


def reflective_hardening_gaps(requirements_text: str) -> List[str]:
    """Return human-readable gaps if requirements lack Phase 4.5 / 4.6 markers.

    Empty list means the lightweight gate passes.
    """
    text = requirements_text or ""
    gaps: List[str] = []

    has_lessons = bool(
        _LESSONS_HEADING.search(text)
        or _LESSONS_PHRASE.search(text)
        or _LESSONS_NOOP.search(text)
    )
    has_principles = bool(
        _PRINCIPLES_HEADING.search(text)
        or _PRINCIPLES_PHRASE.search(text)
        or _PRINCIPLES_NOOP.search(text)
    )
    has_v031 = bool(_VERSION_031.search(text))

    if not has_lessons:
        gaps.append(
            "requirements missing Phase 4.5 markers "
            "(§0.1 Lessons-Learned Hardening, or an explicit "
            "'checked lessons; none applicable')"
        )
    if not has_principles:
        gaps.append(
            "requirements missing Phase 4.6 markers "
            "(§0.2 Design-Principle Hardening, or an explicit "
            "'checked design principles; none applicable')"
        )
    # Version string is optional when both harden sections are present.
    if not has_v031 and not (has_lessons and has_principles):
        gaps.append(
            "requirements missing v0.3.1 version marker "
            "(and incomplete §0.1/§0.2 harden sections)"
        )

    return gaps
