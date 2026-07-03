# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Requirement domains + owned owner-resolution (FR-RP-1/FR-RP-2).

The structural analogue of ``stakeholder_panel.input_domains.DomainSpec`` — a section/FR-class →
owning-role map — but **owned**, not reused. The CRP review falsified the "reuse ``recommend_inputs``"
shortcut **twice**:

* ``input_domains.resolve_owner`` calls ``get_domain()`` and returns ``None`` for any name outside the
  3 **value** domains (``input_domains.py:308-325``) → every requirements area would be skipped.
* ``recommend._default_domains`` enumerates by on-disk YAML presence (``recommend.py:162-168``) →
  requirements domains (an in-code registry, no YAML) would enumerate to **zero**.

So this module owns both :func:`requirement_domains` (enumeration) and :func:`resolve_requirement_owner`
(resolution). Only ``routing.route`` (which keys on a symbol string) is reused, indirectly, via the
bounded ``answers_for`` fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from startd8.stakeholder_panel.models import PersonaBrief

__all__ = [
    "RequirementDomain",
    "DEFAULT_DOMAINS",
    "requirement_domains",
    "get_domain",
    "resolve_requirement_owner",
]


@dataclass(frozen=True)
class RequirementDomain:
    """One requirement area a persona may draft FRs for (FR-RP-1)."""

    area: str  # the routing symbol (matched against a persona's answers_for)
    owning_role: str  # the default role_id that owns this area if present on the roster
    label: str
    grounds_on: Tuple[str, ...] = ("brief", "schema")  # FR-RP-4 grounding hooks
    aliases: Tuple[str, ...] = ()  # extra answers_for tokens that confer ownership


# The default requirements roster areas. `data` is the entity-touching FR class (schema-grounded); the
# rest are perspective areas a stakeholder persona owns.
DEFAULT_DOMAINS: Tuple[RequirementDomain, ...] = (
    RequirementDomain(
        "problem",
        "product-owner",
        "problem statement & goals",
        aliases=("goals", "product"),
    ),
    RequirementDomain(
        "data",
        "architect",
        "entity-touching / data requirements",
        aliases=("schema", "entities"),
    ),
    RequirementDomain(
        "ux", "designer", "user-experience requirements", aliases=("design", "frontend")
    ),
    RequirementDomain(
        "ops",
        "ops",
        "operational / reliability requirements",
        aliases=("operations", "reliability", "observability"),
    ),
    RequirementDomain(
        "security",
        "security",
        "security & authz requirements",
        aliases=("auth", "authz"),
    ),
    RequirementDomain(
        "compliance",
        "compliance",
        "compliance & data-governance requirements",
        aliases=("legal", "privacy"),
    ),
)


def requirement_domains(
    names: Optional[Sequence[str]] = None,
) -> List[RequirementDomain]:
    """The in-code requirement-domain registry (FR-RP-1) — do NOT call ``recommend._default_domains``.

    ``names`` optionally restricts to a subset (unknown names are skipped, deterministic order).
    """
    if names is None:
        return list(DEFAULT_DOMAINS)
    wanted = list(names)
    by_area = {d.area: d for d in DEFAULT_DOMAINS}
    return [by_area[n] for n in wanted if n in by_area]


def get_domain(area: str) -> Optional[RequirementDomain]:
    for d in DEFAULT_DOMAINS:
        if d.area == area:
            return d
    return None


def _answers_for_names_area(brief: PersonaBrief, domain: RequirementDomain) -> bool:
    """High-confidence signal: an ``answers_for`` entry explicitly names this area or an alias."""
    candidates = {domain.area, *domain.aliases}
    for raw in brief.answers_for:
        norm = raw.strip().rstrip("*").rstrip(".").lower()
        if norm in candidates:
            return True
    return False


def resolve_requirement_owner(
    domain: RequirementDomain, briefs: Sequence[PersonaBrief]
) -> Optional[str]:
    """Return the ``role_id`` that owns *domain*, or ``None`` to **skip** the area (FR-RP-2, bounded).

    Resolution order (mirrors the panel's bounded discipline, but owned — R1-F1):
      1. the domain's **default owning role** if present on the roster;
      2. else a persona whose ``answers_for`` **explicitly names the area/alias** (high-confidence);
      3. else ``None`` — the area is skipped, never drafted by a non-owning persona (no loose match).
    """
    by_id = {b.role_id: b for b in briefs}
    if domain.owning_role in by_id:
        return domain.owning_role
    for brief in briefs:  # roster order = deterministic tie-break
        if _answers_for_names_area(brief, domain):
            return brief.role_id
    return None
