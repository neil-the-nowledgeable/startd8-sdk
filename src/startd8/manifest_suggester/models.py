# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Core models for the Manifest Suggester (MANIFEST_SUGGESTER_REQUIREMENTS.md v0.3 + CRP triage).

A :class:`ScreenCandidate` is a proposed **composite view / non-entity page** (authoring-contract prose)
staged for human approval — the manifest analogue of the Requirements Panel's ``RequirementCandidate``
and the Stakeholder Panel's ``Recommendation``. Per-provenance marker (never silently promoted,
FR-MS-6); a **distinct `$0`-baseline constant** (not the panel's ``ESTIMATE_PROVENANCE``, which requires
a ``panel:<role>`` origin a no-LLM baseline lacks — the same R2-F3/R2-S3 lesson as the Requirements
Panel). Slug identity uses the extractor's own ``nfkd_kebab`` so dedupe matches how the round-trip gate
routes names (R1-F5/R1-S7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from startd8.manifest_extraction.grammar import nfkd_kebab

__all__ = [
    "KIND_PAGE",
    "KIND_VIEW",
    "PROV_BASELINE",
    "PROV_ESTIMATE",
    "PROVENANCES",
    "ScreenCandidate",
]

KIND_PAGE = "page"
KIND_VIEW = "view"

PROV_BASELINE = (
    "baseline"  # $0 deterministic schema-grounded starter (no LLM, no persona)
)
PROV_ESTIMATE = "estimate"  # role-drafted by a persona (paid)
PROVENANCES = (PROV_BASELINE, PROV_ESTIMATE)


@dataclass
class ScreenCandidate:
    """A proposed screen (composite view or non-entity page) as authoring-contract prose.

    ``prose`` is the ``### view: <Name>`` / ``## Pages`` markdown the extractor round-trips; the loop
    never writes it directly — an approved candidate applies via the existing ``manifest`` proposal kind
    (FR-MS-5). ``entities_referenced`` are the declared entities the prose names (grounding input).
    """

    kind: str  # KIND_PAGE | KIND_VIEW
    name: str
    prose: str
    entities_referenced: Tuple[str, ...] = ()
    provenance: str = PROV_BASELINE
    role_id: str = ""
    model: str = ""
    cost_usd: float = 0.0
    session_id: str = ""
    created_at: str = ""
    flags: List[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Extractor-derived slug (``nfkd_kebab``) — the dedupe identity (R1-F5/R1-S7)."""
        return nfkd_kebab(self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "prose": self.prose,
            "entities_referenced": list(self.entities_referenced),
            "provenance": self.provenance,
            "role_id": self.role_id,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "flags": list(self.flags),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ScreenCandidate":
        prov = str(d.get("provenance", PROV_BASELINE))
        if prov not in PROVENANCES:
            prov = PROV_BASELINE
        return ScreenCandidate(
            kind=str(d.get("kind", KIND_VIEW)),
            name=str(d.get("name", "")),
            prose=str(d.get("prose", "")),
            entities_referenced=tuple(
                str(e) for e in (d.get("entities_referenced") or [])
            ),
            provenance=prov,
            role_id=str(d.get("role_id", "")),
            model=str(d.get("model", "")),
            cost_usd=float(d.get("cost_usd", 0.0) or 0.0),
            session_id=str(d.get("session_id", "")),
            created_at=str(d.get("created_at", "")),
            flags=[str(f) for f in (d.get("flags") or [])],
        )
