# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Core data models for the Requirements Panel (REQUIREMENTS_PANEL_REQUIREMENTS.md v0.4).

Owns the capability's new vocabulary — *requirement candidate*, *requirement doc*, per-FR
*provenance* — deliberately **not** reusing ``stakeholder_panel.models.Recommendation`` (that carries
value-scalar semantics). Two load-bearing decisions from CRP triage:

* **Per-FR provenance (R2-F3).** One doc mixes ``$0``-baseline stubs, role-drafted FRs, and human
  edits — a doc-level stamp cannot say *which FR is which*, so provenance rides on each candidate.
  Three distinguishable values (:data:`PROV_BASELINE` / :data:`PROV_ESTIMATE` / :data:`PROV_HUMAN`);
  the baseline constant is **distinct** from ``ESTIMATE_PROVENANCE`` (whose ``is_estimate`` requires a
  ``panel:<role>`` origin a no-LLM stub lacks, ``recommend_provenance.py:44-46``).
* **Content-hash FR-IDs (R1-F4).** ``FR-<AREA>-<hash>`` is derived from the requirement's normalized
  text, **not** re-ordinal-assigned, so a re-elicit never renumbers existing FRs (they are the anchors
  CRP later depends on).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

__all__ = [
    "PROV_BASELINE",
    "PROV_ESTIMATE",
    "PROV_HUMAN",
    "PROVENANCES",
    "NEEDS_OWNER",
    "normalize_slug",
    "fr_id",
    "asserts_mandate",
    "RequirementCandidate",
    "RequirementDoc",
]

# Per-FR provenance tier (R2-F3). NOT stakeholder_panel's ESTIMATE_PROVENANCE — a $0 baseline stub has
# no persona origin, so it needs its own constant that `is_estimate` would (correctly) reject.
PROV_BASELINE = "baseline"  # $0 deterministic scaffold stub (no LLM, no persona)
PROV_ESTIMATE = "estimate"  # role-drafted by a persona (paid)
PROV_HUMAN = "human"  # post-approve human authorship
PROVENANCES = (PROV_BASELINE, PROV_ESTIMATE, PROV_HUMAN)

# The placeholder a $0 baseline stub carries until a human/role decides the real intent. The readiness
# gate (FR-RP-6) blocks promoting a stub that still contains it.
NEEDS_OWNER = "<needs-owner>"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
# A requirement *asserts a mandate* when it uses a normative keyword — the P1 boundary invariant only
# bites on MUST/SHALL-class intent, not on descriptive notes.
_MANDATE_RE = re.compile(r"\b(MUST|SHALL|REQUIRED|MUST NOT|SHALL NOT)\b")


def normalize_slug(text: str) -> str:
    """Lowercase, collapse every non-alphanumeric run to a single hyphen, strip ends.

    The dedupe identity (R1-F3): two titles collide **iff** their slugs are byte-equal — near-but-not-
    equal slugs are treated as distinct so dedupe can never silently drop a real FR.
    """
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


def fr_id(area: str, title: str) -> str:
    """A stable, content-hash-derived id ``FR-<AREA>-<hash6>`` (R1-F4 — never re-ordinal-assigned)."""
    area_tok = normalize_slug(area).upper().replace("-", "") or "GEN"
    digest = hashlib.sha256(normalize_slug(title).encode("utf-8")).hexdigest()[:6]
    return f"FR-{area_tok}-{digest}"


def asserts_mandate(text: str) -> bool:
    """True iff *text* uses a normative keyword (MUST/SHALL/…) — the P1 boundary invariant trigger."""
    return bool(_MANDATE_RE.search(text or ""))


@dataclass
class RequirementCandidate:
    """One candidate requirement — a $0 baseline stub or a role-drafted FR, staged for human approval.

    ``flags`` holds rendered grounding-guard strings (advisory metadata, FR-RP-4); the candidate
    ``body``/``rationale`` text is **never** mutated by grounding ("soften" = flags-only, R1-F2).
    """

    area: str
    title: str
    body: str
    rationale: str = ""
    entities_referenced: Tuple[str, ...] = ()
    provenance: str = PROV_BASELINE
    role_id: str = ""
    model: str = ""
    cost_usd: float = 0.0
    session_id: str = ""
    created_at: str = ""
    flags: List[str] = field(default_factory=list)

    @property
    def fr_id(self) -> str:
        return fr_id(self.area, self.title)

    @property
    def needs_owner(self) -> bool:
        """A $0 baseline stub still carrying the ``<needs-owner>`` placeholder (unowned intent)."""
        return NEEDS_OWNER in self.body

    @property
    def slug(self) -> str:
        return normalize_slug(self.title)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "area": self.area,
            "title": self.title,
            "body": self.body,
            "rationale": self.rationale,
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
    def from_dict(d: Dict[str, Any]) -> "RequirementCandidate":
        prov = str(d.get("provenance", PROV_BASELINE))
        if (
            prov not in PROVENANCES
        ):  # a persisted draft can never silently upgrade to an unknown tier
            prov = PROV_BASELINE
        return RequirementCandidate(
            area=str(d.get("area", "")),
            title=str(d.get("title", "")),
            body=str(d.get("body", "")),
            rationale=str(d.get("rationale", "")),
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


@dataclass
class RequirementDoc:
    """An assembled requirements document: a problem statement, ordered FR candidates, NRs, OQs.

    Rendered to markdown (:meth:`render`) with per-FR provenance carried as an **HTML comment** right
    after each FR heading — invisible to markdown heading parsing (so it does not pollute the
    ``####``-anchored CRP appendix, FR-RP-8) yet recoverable on re-parse (R2-F3).
    """

    title: str
    problem: str = ""
    candidates: List[RequirementCandidate] = field(default_factory=list)
    non_requirements: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def provenance_manifest(self) -> Dict[str, str]:
        """Out-of-band ``{fr_id: provenance}`` map — surfaced by ``review`` alongside the bytes."""
        return {c.fr_id: c.provenance for c in self.candidates}

    def render(self) -> str:
        lines: List[str] = [f"# {self.title}", ""]
        lines += ["## Problem Statement", "", self.problem or "_(to be authored)_", ""]
        lines += ["## Requirements", ""]
        for area in _ordered_areas(self.candidates):
            lines.append(f"### {area.title()}")
            lines.append("")
            for c in [x for x in self.candidates if x.area == area]:
                lines.append(f"#### {c.fr_id} — {c.title}")
                lines.append(f"<!-- prov: {c.provenance} -->")
                lines.append("")
                lines.append(c.body)
                if c.rationale:
                    lines.append("")
                    lines.append(f"_Rationale: {c.rationale}_")
                lines.append("")
        lines += ["## Non-Requirements", ""]
        lines += [f"- {nr}" for nr in self.non_requirements] or ["_(none)_"]
        lines += ["", "## Open Questions", ""]
        lines += [f"- {oq}" for oq in self.open_questions] or ["_(none)_"]
        lines.append("")
        return "\n".join(lines)


def _ordered_areas(candidates: List[RequirementCandidate]) -> List[str]:
    """Areas in first-seen order (deterministic — dicts preserve insertion order)."""
    seen: Dict[str, None] = {}
    for c in candidates:
        seen.setdefault(c.area, None)
    return list(seen.keys())
