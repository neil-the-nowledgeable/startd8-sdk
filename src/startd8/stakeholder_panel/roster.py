# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Load and validate the stakeholder roster from ``docs/kickoff/inputs/stakeholders.yaml`` (FR-1/FR-4).

Deterministic and ``$0`` — pure YAML parsing plus structural checks. :func:`assess_roster` is the
readiness-facing summary the Concierge ``assess`` path consumes; it reports a roster as
``absent`` / ``invalid`` / ``present`` (FR-4) and never grades content quality (parity with the other
kickoff input domains, which report honestly rather than scoring).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import yaml

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import (
    PROTOCOL_VERSION,
    ROLE_ID_PATTERN,
    PersonaBrief,
    Roster,
)

__all__ = [
    "RosterError",
    "DOMAIN",
    "TOPLEVEL_KEYS",
    "PERSONA_KEYS",
    "parse_roster",
    "load_roster",
    "validate_roster",
    "assess_roster",
]

logger = get_logger(__name__)

_ROLE_ID_RE = re.compile(ROLE_ID_PATTERN)

# The domain discriminator (a strict parser rejects a roster that is not one, FR-2).
DOMAIN = "stakeholders"

# Allow-sets for the typo guard, DERIVED from the dataclasses (R1-F7) so adding a field never desyncs
# the guard. Top-level = the ``Roster`` envelope fields + the ``domain`` discriminator; per-persona =
# the ``PersonaBrief`` fields. ``ROSTER_SCHEMA.md`` documents these and a test asserts the doc stays
# in sync (R2-F2).
TOPLEVEL_KEYS = frozenset({"domain"} | {f.name for f in dataclasses.fields(Roster)})
PERSONA_KEYS = frozenset(f.name for f in dataclasses.fields(PersonaBrief))


class RosterError(ValueError):
    """The roster is structurally/schema-invalid — a *parse* failure (FR-2).

    Raised for I/O, malformed YAML, a non-mapping root, a wrong/absent ``domain`` discriminator, an
    unknown top-level/per-persona key (typo guard), or a newer major ``protocol_version``. Distinct
    from *content* issues (a well-formed roster with duplicate ids / empty briefs), which
    :func:`validate_roster` returns as a soft list rather than raising.
    """


def _version_tuple(value: Any) -> Tuple[int, int]:
    """Best-effort (major, minor) from a version string; unparseable parts default low."""
    parts = str(value or "").split(".")

    def _int(token: str, default: int) -> int:
        try:
            return int(token)
        except (TypeError, ValueError):
            return default

    major = _int(parts[0], 0) if parts and parts[0] else 0
    minor = _int(parts[1], 0) if len(parts) > 1 else 0
    return major, minor


def _check_unknown(
    keys: Iterable[str], allowed: Iterable[str], where: str, *, lenient: bool
) -> None:
    """Typo guard: reject unknown keys (or warn, under a forward-compatible minor version)."""
    allowed_set = set(allowed)
    unknown = [k for k in keys if k not in allowed_set]
    if not unknown:
        return
    msg = (
        f"unknown {where} key(s) {', '.join(map(repr, unknown))} "
        f"(allowed: {', '.join(sorted(allowed_set))})"
    )
    if lenient:
        logger.warning("roster forward-compat: %s", msg)
    else:
        raise RosterError(msg)


def parse_roster(text: str) -> Roster:
    """Strictly parse roster *text* into a :class:`Roster` (FR-2) — the one canonical authority.

    Strict on **document structure** (mapping root, ``domain`` discriminator, no unknown keys) and
    forward-compat on ``protocol_version`` (a newer *major* is rejected; a newer *minor* relaxes the
    unknown-key guard to a warning so an additive future key does not hard-fail an older SDK). Field
    element types are still *coerced* by :meth:`Roster.from_dict`; *content* issues are left to
    :func:`validate_roster`. An empty document is an empty roster (validation reports "no personas").
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RosterError(f"malformed roster YAML: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RosterError(f"roster must be a YAML mapping, got {type(data).__name__}")
    if not data:
        return Roster.from_dict(
            data
        )  # empty roster; validate_roster reports "no personas"

    domain = data.get("domain")
    if domain != DOMAIN:
        raise RosterError(f"roster 'domain' must be {DOMAIN!r}, got {domain!r}")

    # Forward-compat on protocol_version (R1-F2): reject a newer major; a newer minor is additive.
    v_major, v_minor = _version_tuple(data.get("protocol_version", PROTOCOL_VERSION))
    o_major, o_minor = _version_tuple(PROTOCOL_VERSION)
    if v_major > o_major:
        raise RosterError(
            f"roster protocol_version {data.get('protocol_version')!r} is newer than this SDK's "
            f"{PROTOCOL_VERSION!r} — upgrade the SDK"
        )
    lenient = v_major == o_major and v_minor > o_minor

    _check_unknown(data.keys(), TOPLEVEL_KEYS, "top-level", lenient=lenient)
    for idx, persona in enumerate(data.get("personas") or []):
        if isinstance(persona, dict):
            _check_unknown(
                persona.keys(), PERSONA_KEYS, f"persona[{idx}]", lenient=lenient
            )

    return Roster.from_dict(data)


def load_roster(path: Path | str) -> Roster:
    """Read *path* and :func:`parse_roster` it. Raises :class:`RosterError` on I/O or parse failure."""
    p = Path(path).expanduser()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RosterError(f"cannot read roster {p}: {exc}") from exc
    try:
        return parse_roster(raw)
    except RosterError as exc:
        # Re-raise with the path for a caller-friendly message.
        raise RosterError(f"{p}: {exc}") from exc


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
