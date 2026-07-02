# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Stakeholder Panel roster contracts (FR-2).

A :class:`Roster` is the human-authored declaration of the project stakeholders the panel role-plays;
each :class:`PersonaBrief` is the **sole substantive knowledge source** for one persona (FR-2/FR-7,
Decision D-3). The JSON form is canonical (``to_dict``/``from_dict``); the on-disk authoring form is
YAML (see :mod:`startd8.stakeholder_panel.roster`).

These are M0 (authoring-surface) contracts. The query-time contracts (``PanelQuestion`` /
``PanelAnswer`` and the synthetic ``LabeledClaim`` provenance of FR-10) arrive with the live panel in
a later increment; they are intentionally **not** defined here so M0 carries no LLM/agent coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

__all__ = [
    "PROTOCOL_VERSION",
    "ROLE_ID_PATTERN",
    "PersonaBrief",
    "Roster",
    "Grounding",
    "PanelQuestion",
    "PanelAnswer",
]

# Bumped on a contract *shape* change, independent of the SDK version (VIPP/FDE parity).
PROTOCOL_VERSION = "1.0"

# role_id is an address (used to route a question to a persona and to key cost/telemetry later), so
# it must be a stable single-token slug: lowercase alphanumerics separated by single hyphens.
ROLE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def _str_list(value: Any) -> List[str]:
    """Coerce a YAML/JSON scalar-or-sequence into a clean ``list[str]`` (drops blanks).

    Authors may write a single string or a list; ``None``/absent becomes ``[]``. Kept permissive on
    input shape but strict on element type so validation (:func:`validate_roster`) sees normalized
    data.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        # A mapping or number where a list was expected — surface as one stringified element so
        # validation can flag the shape rather than silently dropping it.
        items = [value]
    return [str(item).strip() for item in items if str(item).strip()]


def _as_int(value: Any, default: int = 0) -> int:
    """Tolerant int coercion — a malformed persisted field must not crash a transcript load."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    """Tolerant float coercion (see :func:`_as_int`)."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class PersonaBrief:
    """One stakeholder persona (FR-2). The brief bounds what the persona may answer (FR-7)."""

    role_id: str
    display_name: str
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    known_positions: List[str] = field(default_factory=list)
    out_of_scope: List[str] = field(default_factory=list)
    # Optional routing hint (FR-9c / OQ-9): value_path or entity prefixes this persona answers for.
    # Empty means "match by heuristic against goals/positions"; it is never a security boundary.
    answers_for: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "display_name": self.display_name,
            "goals": list(self.goals),
            "constraints": list(self.constraints),
            "known_positions": list(self.known_positions),
            "out_of_scope": list(self.out_of_scope),
            "answers_for": list(self.answers_for),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PersonaBrief":
        return PersonaBrief(
            role_id=str(d.get("role_id", "")).strip(),
            display_name=str(d.get("display_name", "")).strip(),
            goals=_str_list(d.get("goals")),
            constraints=_str_list(d.get("constraints")),
            known_positions=_str_list(d.get("known_positions")),
            out_of_scope=_str_list(d.get("out_of_scope")),
            answers_for=_str_list(d.get("answers_for")),
        )

    @property
    def is_empty(self) -> bool:
        """A brief with no substantive content (FR-4 "no empty briefs").

        role_id/display_name alone do not make a usable persona — there must be at least one goal,
        constraint, or known position for the persona to have anything to say.
        """
        return not (self.goals or self.constraints or self.known_positions)


@dataclass(frozen=True)
class Roster:
    """The project's stakeholder roster (FR-1). Canonical JSON via ``to_dict``/``from_dict``."""

    personas: List[PersonaBrief] = field(default_factory=list)
    provenance_default: str = "authored"
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "domain": "stakeholders",
            "provenance_default": self.provenance_default,
            "personas": [p.to_dict() for p in self.personas],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Roster":
        raw_personas = d.get("personas") or []
        if not isinstance(raw_personas, (list, tuple)):
            # Preserve the shape error for validation rather than crashing the load.
            raw_personas = []
        return Roster(
            personas=[
                PersonaBrief.from_dict(p) for p in raw_personas if isinstance(p, dict)
            ],
            provenance_default=str(d.get("provenance_default", "authored")).strip()
            or "authored",
            protocol_version=str(d.get("protocol_version", PROTOCOL_VERSION)).strip()
            or PROTOCOL_VERSION,
        )

    def persona(self, role_id: str) -> "PersonaBrief | None":
        return next((p for p in self.personas if p.role_id == role_id), None)


# --------------------------------------------------------------------------- #
# Query-time contracts (M1). A persona answers a PanelQuestion with a PanelAnswer; the answer
# carries its own provenance (brief hash, grounding signal, cost) so it can be labeled synthetic
# (FR-10) and audited (FR-12) without reaching back to the panel that produced it.
# --------------------------------------------------------------------------- #


class Grounding(str, Enum):
    """How well an answer is grounded in the persona's brief (FR-7).

    ``grounded``/``uncertain`` mean the persona *answered* (the brief supports it, or it hedged);
    ``deferred`` means the persona declined as out-of-brief; ``unavailable`` means the agent call
    failed (FR-16) — the panel never fabricates a fact in that case.
    """

    GROUNDED = "grounded"
    UNCERTAIN = "uncertain"
    DEFERRED = "deferred"
    UNAVAILABLE = "unavailable"

    @staticmethod
    def coerce(value: Any) -> "Grounding":
        """Best-effort parse of a model-emitted grounding token; unknown ⇒ ``uncertain``."""
        try:
            return Grounding(str(value).strip().lower())
        except ValueError:
            return Grounding.UNCERTAIN


@dataclass(frozen=True)
class PanelQuestion:
    """One question posed to the panel. ``target_role_id`` names a persona; ``value_path`` is the
    manifest symbol the question is about (threaded through to the answer for FR-10/R2-F4).
    """

    text: str
    target_role_id: str = ""
    value_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "target_role_id": self.target_role_id,
            "value_path": self.value_path,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PanelQuestion":
        return PanelQuestion(
            text=str(d.get("text", "")),
            target_role_id=str(d.get("target_role_id", "")).strip(),
            value_path=str(d.get("value_path", "")).strip(),
        )


@dataclass(frozen=True)
class PanelAnswer:
    """A persona's answer plus its provenance (FR-10/FR-12).

    ``brief_hash``+``roster_version`` pin the exact brief revision that produced the answer (R2-F3)
    so a persisted answer stays traceable after ``stakeholders.yaml`` is edited. ``value_path`` rides
    on the answer (R2-F4) so a non-VIPP consumer can read per-field provenance. The answer is
    *synthetic, unratified* input — :mod:`startd8.stakeholder_panel.provenance` renders it as an
    ``OBSERVED (project, synthetic)`` claim.
    """

    role_id: str
    question: str
    text: str
    grounding: Grounding = Grounding.UNCERTAIN
    value_path: str = ""
    brief_hash: str = ""
    roster_version: str = ""
    session_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    created_at: str = ""  # ISO-8601 UTC; stamped by the panel
    # Advisory guard flags (FR-7 / M3): e.g. "unsupported-specifics: $10000, q4" — an independent
    # deterministic check that the answer's asserted specifics trace to the brief. Advisory only.
    flags: List[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        """The persona actually responded (FR-16: an unavailable answer is never a fact)."""
        return self.grounding is not Grounding.UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "question": self.question,
            "text": self.text,
            "grounding": self.grounding.value,
            "value_path": self.value_path,
            "brief_hash": self.brief_hash,
            "roster_version": self.roster_version,
            "session_id": self.session_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "created_at": self.created_at,
            "flags": list(self.flags),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PanelAnswer":
        return PanelAnswer(
            role_id=str(d.get("role_id", "")),
            question=str(d.get("question", "")),
            text=str(d.get("text", "")),
            grounding=Grounding.coerce(d.get("grounding")),
            value_path=str(d.get("value_path", "")),
            brief_hash=str(d.get("brief_hash", "")),
            roster_version=str(d.get("roster_version", "")),
            session_id=str(d.get("session_id", "")),
            model=str(d.get("model", "")),
            input_tokens=_as_int(d.get("input_tokens")),
            output_tokens=_as_int(d.get("output_tokens")),
            cost_usd=_as_float(d.get("cost_usd")),
            created_at=str(d.get("created_at", "")),
            flags=[str(f) for f in (d.get("flags") or [])],
        )
