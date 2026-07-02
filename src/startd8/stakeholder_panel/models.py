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
from typing import Any, Dict, List

__all__ = [
    "PROTOCOL_VERSION",
    "ROLE_ID_PATTERN",
    "PersonaBrief",
    "Roster",
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
