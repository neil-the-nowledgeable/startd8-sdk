# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Load and validate the stakeholder roster from ``docs/kickoff/inputs/stakeholders.yaml`` (FR-1/FR-4).

Deterministic and ``$0`` — pure YAML parsing plus structural checks. :func:`assess_roster` is the
readiness-facing summary the Concierge ``assess`` path consumes; it reports a roster as
``absent`` / ``invalid`` / ``present`` (FR-4) and never grades content quality (parity with the other
kickoff input domains, which report honestly rather than scoring).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import ROLE_ID_PATTERN, Roster

__all__ = [
    "RosterError",
    "load_roster",
    "validate_roster",
    "assess_roster",
]

logger = get_logger(__name__)

_ROLE_ID_RE = re.compile(ROLE_ID_PATTERN)


class RosterError(ValueError):
    """The roster file is missing, unreadable, or not a YAML mapping (a *load* failure).

    Distinct from *validation* issues (a well-formed file with bad content), which
    :func:`validate_roster` returns as a list rather than raising.
    """


def load_roster(path: Path | str) -> Roster:
    """Parse *path* into a :class:`Roster`. Raises :class:`RosterError` on a load failure.

    A load failure is I/O, malformed YAML, or a non-mapping top level. Content problems (duplicate
    ``role_id``, empty brief) are *not* load failures — they surface via :func:`validate_roster`.
    """
    p = Path(path).expanduser()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RosterError(f"cannot read roster {p}: {exc}") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RosterError(f"malformed roster YAML {p}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RosterError(
            f"roster {p} must be a YAML mapping, got {type(data).__name__}"
        )
    return Roster.from_dict(data)


def validate_roster(roster: Roster) -> List[str]:
    """Return a list of validation issues (empty ⇒ valid). FR-4: unique ids, required fields, no
    empty briefs.

    Structural only — never judges whether a brief is *good*, just that it is *usable*.
    """
    issues: List[str] = []

    if not roster.personas:
        issues.append("roster declares no personas (need at least one)")

    seen: Dict[str, int] = {}
    for idx, persona in enumerate(roster.personas):
        where = persona.role_id or f"persona[{idx}]"

        if not persona.role_id:
            issues.append(f"{where}: missing role_id")
        elif not _ROLE_ID_RE.match(persona.role_id):
            issues.append(
                f"{persona.role_id!r}: role_id must be kebab-case "
                f"(lowercase alphanumerics separated by single hyphens)"
            )
        else:
            seen[persona.role_id] = seen.get(persona.role_id, 0) + 1

        if not persona.display_name:
            issues.append(f"{where}: missing display_name")

        if persona.is_empty:
            issues.append(
                f"{where}: empty brief — add at least one goal, constraint, or known_position"
            )

    for role_id, count in seen.items():
        if count > 1:
            issues.append(f"duplicate role_id {role_id!r} ({count} personas share it)")

    return issues


def assess_roster(path: Path | str) -> Dict[str, Any]:
    """Readiness summary for the Concierge ``assess`` path (FR-4).

    Returns one of:
      * ``{"status": "absent"}`` — no roster file.
      * ``{"status": "invalid", ...}`` — unreadable/malformed, **or** parsed-but-failed-validation
        (``issues`` lists the reasons).
      * ``{"status": "present", ...}`` — a valid roster (persona count, role_ids, provenance).

    The caller composes the *authored-vs-consumable* distinction (R2-S5) using
    ``stakeholder_panel.PANEL_CONSUMABLE`` — this function reports authoring readiness only.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        return {"status": "absent"}
    try:
        roster = load_roster(p)
    except RosterError as exc:
        return {"status": "invalid", "error": str(exc)}

    issues = validate_roster(roster)
    if issues:
        return {
            "status": "invalid",
            "issues": issues,
            "persona_count": len(roster.personas),
        }

    return {
        "status": "present",
        "provenance_default": roster.provenance_default,
        "persona_count": len(roster.personas),
        "role_ids": [p.role_id for p in roster.personas],
    }
