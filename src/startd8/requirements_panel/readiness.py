# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Pre-CRP readiness gate (FR-RP-6 / Step 6.5 — `$0` deterministic, BLOCKING).

Breaks the FR-RP-6/P6 circularity (a generator whose only check is the CRP it feeds) with a
deterministic gate that **blocks** ``approve`` — it never auto-approves and never judges *quality*
(CRP's job), only *readiness*. It blocks when (R1-S2, refined by R2-S5):

* a **non-baseline** candidate that **asserts a mandate** (MUST/SHALL) carries an unresolved **high**
  grounding flag — the P1 boundary invariant (intent must be brief/schema-traceable or ``<needs-owner>``);
* a ``<needs-owner>`` stub is being promoted (its unowned intent placeholder still present);
* a **surviving line-start heading** remains in any candidate text — a blockquote-demoted ``> ## x``
  passes; a bare ``^## x`` fails (R2-S5, reconciles FR-RP-7's neutralize-by-demote with this gate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from startd8.requirements_panel.grounding import SEV_HIGH
from startd8.requirements_panel.models import (
    PROV_BASELINE,
    RequirementDoc,
    asserts_mandate,
)
from startd8.requirements_panel.sanitize import has_unsafe_heading

__all__ = ["ReadinessResult", "check_readiness"]


@dataclass
class ReadinessResult:
    ok: bool
    blockers: List[str] = field(default_factory=list)


def _has_high_flag(candidate) -> bool:
    return any(f.startswith(SEV_HIGH + ":") for f in candidate.flags)


def check_readiness(doc: RequirementDoc) -> ReadinessResult:
    """Return a blocking result for the assembled *doc* (empty blockers ⇒ ``approve`` may proceed)."""
    blockers: List[str] = []
    for c in doc.candidates:
        if c.needs_owner:
            blockers.append(
                f"{c.fr_id}: unowned stub — '<needs-owner>' must be resolved before approve"
            )
        if (
            c.provenance != PROV_BASELINE
            and asserts_mandate(c.body)
            and _has_high_flag(c)
        ):
            blockers.append(
                f"{c.fr_id}: ungrounded MUST/SHALL — a high grounding flag is unresolved "
                "(brief/schema-traceable or <needs-owner> required, P1)"
            )
        if has_unsafe_heading(c.body) or has_unsafe_heading(c.rationale):
            blockers.append(
                f"{c.fr_id}: an un-demoted line-start heading survived sanitization"
            )
    return ReadinessResult(ok=not blockers, blockers=blockers)
