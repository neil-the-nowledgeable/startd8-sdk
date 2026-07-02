# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The ``role-rubric`` built-in adapter (FR-5).

Ingests the *role-rubric format family* — `key`/`label`/`lens`/`rubric`/`coverage`/`out_of_scope`
(as used by e.g. a benchmark's ``reviewer_roles.yaml``) — into a native :class:`Roster`. This is the
pilot converter promoted into the SDK, but it builds ``PersonaBrief``/``Roster`` objects directly and
returns a **validated** roster (no hand-written YAML). Loaded lazily by the registry (R2-F4): importing
``stakeholder_panel`` never imports this module — only ``get_adapter("role-rubric")`` does.

**Pinned mapping (R1-F5)** — asserted field-by-field by tests, and kept byte-equivalent to the pilot
converter so the N3 retirement parity check holds:

    key           -> role_id        (kebab-cased)
    label         -> display_name
    lens          -> goals          ("Review through the lens of: <lens>.")
    rubric[].name -> answers_for     (routing keys)
    "name: desc"  -> known_positions (statements)
    coverage      -> constraints     (round-level / applies_to_services / mandatory / standby)
    out_of_scope  -> out_of_scope
"""

from __future__ import annotations

from typing import Any, List

import yaml

from startd8.stakeholder_panel.adapters.base import AdaptResult, AdapterError
from startd8.stakeholder_panel.models import PersonaBrief, Roster, _str_list
from startd8.stakeholder_panel.roster import validate_roster

__all__ = ["RoleRubricAdapter"]


def _kebab(key: str) -> str:
    return str(key).strip().lower().replace("_", "-")


def _constraints(coverage: Any) -> List[str]:
    """Turn the coverage policy into human-readable persona constraints (matches the pilot converter).

    Tolerant of a malformed ``coverage`` (a non-dict, or a scalar/list where a list of services was
    expected) — a bad source must never crash with a raw ``AttributeError``/``TypeError``; it just
    yields no constraint from that key.
    """
    if not isinstance(coverage, dict):
        return []
    out: List[str] = []
    if coverage.get("scope") == "round_level":
        out.append("You sign off at the round level, not per individual service.")
    services = _str_list(coverage.get("applies_to_services"))
    if services:
        out.append(f"You review only these services: {', '.join(services)}.")
    if coverage.get("mandatory"):
        out.append("You are assigned to every reviewable service.")
    if coverage.get("auto_assign") is False and not services:
        out.append(
            "You are a standby reviewer — engaged only when an operator assigns you."
        )
    return out


def _lens_text(lens: Any) -> str:
    """A single lens phrase; a list is joined so a list never leaks a Python repr into a goal."""
    if isinstance(lens, (list, tuple)):
        return ", ".join(str(x).strip() for x in lens if str(x).strip())
    return str(lens).strip()


class RoleRubricAdapter:
    """Adapter for the ``key/label/lens/rubric/coverage`` role-rubric format family."""

    name = "role-rubric"

    def adapt(self, text: str) -> AdaptResult:
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise AdapterError(f"malformed role-rubric YAML: {exc}") from exc
        if not isinstance(doc, dict):
            raise AdapterError("role-rubric source must be a YAML mapping")

        roles = doc.get("roles")
        if not isinstance(roles, list) or not roles:
            raise AdapterError("role-rubric source has no non-empty 'roles' list")

        personas: List[PersonaBrief] = []
        for idx, role in enumerate(roles):
            if not isinstance(role, dict):
                raise AdapterError(f"role[{idx}] is not a mapping")
            key, label = role.get("key"), role.get("label")
            if not key or not label:
                raise AdapterError(
                    f"role[{idx}] is missing a required 'key' or 'label'"
                )
            rubric = role.get("rubric")
            if not isinstance(rubric, list):
                raise AdapterError(f"role {key!r}: 'rubric' must be a list")
            dims = [d for d in rubric if isinstance(d, dict)]
            lens = _lens_text(role.get("lens"))
            personas.append(
                PersonaBrief(
                    role_id=_kebab(key),
                    display_name=str(label),
                    goals=([f"Review through the lens of: {lens}."] if lens else []),
                    # Filter dims missing a name (parity with answers_for), and default a missing
                    # description to "" so a bad dim never emits a literal "None: None".
                    known_positions=[
                        f"{d['name']}: {d.get('description', '')}"
                        for d in dims
                        if d.get("name")
                    ],
                    constraints=_constraints(role.get("coverage")),
                    out_of_scope=_str_list(role.get("out_of_scope")),
                    answers_for=[d.get("name") for d in dims if d.get("name")],
                )
            )

        roster = Roster(personas=personas, provenance_default="authored")
        # Defense-in-depth (R2-S1): a well-formed source must produce a *usable* roster. Content
        # problems (dup role_id from dup keys, empty brief) are a source defect → AdapterError. (N2's
        # ingest round-trip-gates again via parse_roster + validate_roster.)
        issues = validate_roster(roster)
        if issues:
            raise AdapterError(
                "role-rubric source produced an invalid roster: " + "; ".join(issues)
            )
        return AdaptResult(roster=roster, warnings=[])
