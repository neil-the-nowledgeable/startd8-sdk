# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Supported kickoff-input domains for the proactive recommendation pass (Teian, FR-KIR-2/3/4).

This is the **M0, $0/no-LLM** foundation of *Stakeholder Input Recommendations*: a registry of the
three kickoff **value** domains a persona may draft starter values for, plus deterministic field
enumeration and bounded persona↔domain resolution.

Three domains are supported (FR-KIR-2): ``business-targets``, ``conventions``, ``build-preferences`` —
the value inputs that (a) have a strict :mod:`startd8.kickoff_inputs` round-trip parser and (b) sit on
the ``estimate`` provenance tier. ``observability`` is deliberately **excluded** (NR-KIR-7): it has no
strict parser and its values are ``config-default`` (industry dataset), not an LLM ``estimate``.

Field enumeration yields the **logical fields** of a domain YAML (FR-KIR-4). A ``business-targets``
metric row is a single **composite** field (``{target, why}``) — enumerated once, not split into two
scalar leaves — so the drafting pass makes one query per metric (M2/approve later splices the two
scalars back through :mod:`kickoff_experience.capture`). ``conventions``/``build-preferences`` are
scalar maps. A field is **unfilled** when its value is absent, empty, or a ``<placeholder>`` — those
are the fields a persona drafts (FR-KIR-1/OQ-KIR-6); a real value is left alone.

Persona↔domain routing is **bounded** (FR-KIR-3, R3-F1): the domain's default owning role if present
on the roster, else a *high-confidence* ``answers_for`` hit that explicitly names the domain, else the
domain is **skipped** — never assigned to a non-owning persona by a loose match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import yaml

from startd8.kickoff_inputs import (
    parse_build_preferences,
    parse_business_targets,
    parse_conventions,
)
from startd8.stakeholder_panel.models import PersonaBrief

__all__ = [
    "SUPPORTED_DOMAINS",
    "DomainSpec",
    "FieldSlot",
    "DOMAINS",
    "get_domain",
    "is_placeholder",
    "enumerate_fields",
    "unfilled_fields",
    "resolve_owner",
]

# Meta keys that are never draftable fields.
_META_KEYS = frozenset({"domain", "provenance_default"})

# A ``<...>`` template placeholder anywhere in a scalar marks it unfilled (OQ-KIR-6).
_PLACEHOLDER_RE = re.compile(r"<[^>]*>")

# The composite sub-keys of a business-targets metric row (FR-KIR-4).
_METRIC_SUBKEYS = ("target", "why")
_METRIC_GROUPS = ("product_funnel", "traction", "unit_economics")


def is_placeholder(value: Any) -> bool:
    """True iff *value* is an **unfilled** slot: absent, empty, or a ``<placeholder>`` (OQ-KIR-6).

    A real scalar (a number, a bool, a non-placeholder string) is *filled* and must be left alone —
    Teian never overwrites an authored/real value, only drafts blanks.
    """
    if value is None:
        return True
    if isinstance(value, str):
        s = value.strip()
        return s == "" or bool(_PLACEHOLDER_RE.search(s))
    return False


@dataclass(frozen=True)
class FieldSlot:
    """One draftable field of a domain YAML (FR-KIR-4).

    ``value_path`` is the dotted key (e.g. ``product_funnel.signup_rate``). ``composite_keys`` is empty
    for a scalar field and ``("target", "why")`` for a business-targets metric row — in which case
    ``current`` is the row mapping and approval splices each sub-key separately (R4-S1).
    """

    value_path: str
    current: Any
    is_unfilled: bool
    composite_keys: tuple = ()

    @property
    def is_composite(self) -> bool:
        return bool(self.composite_keys)

    def scalar_paths(self) -> List[str]:
        """The concrete scalar dotted keys this field writes to (one for scalar, N for composite)."""
        if not self.composite_keys:
            return [self.value_path]
        return [f"{self.value_path}.{k}" for k in self.composite_keys]


# --------------------------------------------------------------------------- #
# Per-domain enumerators. Each takes the leniently-parsed YAML mapping and yields FieldSlots.
# --------------------------------------------------------------------------- #


def _scalar_map_slots(data: Dict[str, Any], group: str) -> List[FieldSlot]:
    """Enumerate an open ``group: {k: scalar}`` map as one scalar FieldSlot per key."""
    block = data.get(group)
    if not isinstance(block, dict):
        return []
    slots: List[FieldSlot] = []
    for key, value in block.items():
        slots.append(
            FieldSlot(
                value_path=f"{group}.{key}",
                current=value,
                is_unfilled=is_placeholder(value),
            )
        )
    return slots


def _enumerate_business_targets(data: Dict[str, Any]) -> List[FieldSlot]:
    """Metric rows are composite ``{target, why}`` (one slot per row, R4-F1); scalars stay scalar."""
    slots: List[FieldSlot] = []
    for group in _METRIC_GROUPS:
        block = data.get(group)
        if not isinstance(block, dict):
            continue
        for metric, row in block.items():
            row_map = row if isinstance(row, dict) else {}
            slots.append(
                FieldSlot(
                    value_path=f"{group}.{metric}",
                    current=row_map,
                    # Unfilled when the primary sub-field (target) is a placeholder/absent.
                    is_unfilled=is_placeholder(row_map.get("target")),
                    composite_keys=_METRIC_SUBKEYS,
                )
            )
    monetization = data.get("monetization")
    if isinstance(monetization, dict):
        for key, value in monetization.items():
            if isinstance(value, dict):  # {target, status} composite
                slots.append(
                    FieldSlot(
                        value_path=f"monetization.{key}",
                        current=value,
                        is_unfilled=is_placeholder(value.get("target")),
                        composite_keys=("target", "status"),
                    )
                )
            else:  # mode_now (scalar)
                slots.append(
                    FieldSlot(
                        value_path=f"monetization.{key}",
                        current=value,
                        is_unfilled=is_placeholder(value),
                    )
                )
    slots.extend(_scalar_map_slots(data, "per_role_top_goals"))
    return slots


def _enumerate_conventions(data: Dict[str, Any]) -> List[FieldSlot]:
    slots: List[FieldSlot] = []
    language = data.get("language")
    slots.append(
        FieldSlot(
            value_path="language",
            current=language,
            is_unfilled=is_placeholder(language),
        )
    )
    for group in ("stack", "module_paths", "naming", "data_model"):
        slots.extend(_scalar_map_slots(data, group))
    if "field_authorship" in data:
        fa = data.get("field_authorship")
        slots.append(
            FieldSlot(
                value_path="field_authorship",
                current=fa,
                is_unfilled=is_placeholder(fa),
            )
        )
    return slots


def _enumerate_build_preferences(data: Dict[str, Any]) -> List[FieldSlot]:
    slots: List[FieldSlot] = []
    for group in ("budgets", "model_routing", "generation", "unattended"):
        slots.extend(_scalar_map_slots(data, group))
    if "concierge_agent" in data:
        ca = data.get("concierge_agent")
        slots.append(
            FieldSlot(
                value_path="concierge_agent",
                current=ca,
                is_unfilled=is_placeholder(ca),
            )
        )
    return slots


@dataclass(frozen=True)
class DomainSpec:
    """A supported kickoff-input value domain (FR-KIR-2)."""

    name: str
    filename: str
    owning_role: str
    parse: Callable[[Optional[str]], Any]
    enumerate: Callable[[Dict[str, Any]], List[FieldSlot]]
    label: str = ""

    def rel_path(self) -> str:
        return f"docs/kickoff/inputs/{self.filename}"


DOMAINS: Dict[str, DomainSpec] = {
    "business-targets": DomainSpec(
        name="business-targets",
        filename="business-targets.yaml",
        owning_role="product-owner",
        parse=parse_business_targets,
        enumerate=_enumerate_business_targets,
        label="business targets (KPIs / traction / unit economics)",
    ),
    "conventions": DomainSpec(
        name="conventions",
        filename="conventions.yaml",
        owning_role="architect",
        parse=parse_conventions,
        enumerate=_enumerate_conventions,
        label="conventions (stack / layout / naming)",
    ),
    "build-preferences": DomainSpec(
        name="build-preferences",
        filename="build-preferences.yaml",
        owning_role="pm",
        parse=parse_build_preferences,
        enumerate=_enumerate_build_preferences,
        label="build preferences (budgets / model routing / profile)",
    ),
}

SUPPORTED_DOMAINS: tuple = tuple(DOMAINS.keys())


def get_domain(name: str) -> Optional[DomainSpec]:
    """The :class:`DomainSpec` for *name*, or ``None`` if it is not a supported value domain."""
    return DOMAINS.get(name)


def enumerate_fields(spec: DomainSpec, yaml_text: Optional[str]) -> List[FieldSlot]:
    """All logical fields of a domain YAML (filled + unfilled).

    Parses **leniently** (``yaml.safe_load``, not the strict parser) so a placeholder-laden template
    still enumerates — the strict parser is the *write-time* round-trip gate (FR-KIR-11), not the
    read-time enumerator. A malformed/non-mapping document yields no fields.
    """
    try:
        data = yaml.safe_load(yaml_text or "") or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    return [s for s in spec.enumerate(data) if _is_draftable(s)]


def _is_draftable(slot: FieldSlot) -> bool:
    top = slot.value_path.split(".", 1)[0]
    return top not in _META_KEYS


def unfilled_fields(spec: DomainSpec, yaml_text: Optional[str]) -> List[FieldSlot]:
    """The subset of :func:`enumerate_fields` that is unfilled — the drafting candidates (FR-KIR-1)."""
    return [s for s in enumerate_fields(spec, yaml_text) if s.is_unfilled]


# --------------------------------------------------------------------------- #
# Bounded persona↔domain resolution (FR-KIR-3, R3-F1)
# --------------------------------------------------------------------------- #


def _answers_for_names_domain(brief: PersonaBrief, domain_name: str) -> bool:
    """High-confidence signal: an ``answers_for`` entry explicitly names this domain.

    Accepts the domain name itself (``business-targets``), its underscore form, or its head token
    (``business``). This is the *only* fallback that confers ownership — a loose field-path route()
    match does NOT (R3-F1), because a bad persona fit produces a useless starter.
    """
    candidates = {
        domain_name,
        domain_name.replace("-", "_"),
        domain_name.split("-", 1)[0],
    }
    for raw in brief.answers_for:
        norm = raw.strip().rstrip("*").rstrip(".").lower()
        if norm in candidates:
            return True
    return False


def resolve_owner(domain_name: str, briefs: List[PersonaBrief]) -> Optional[str]:
    """Return the ``role_id`` that owns *domain_name*, or ``None`` to **skip** the domain (FR-KIR-3).

    Resolution order (bounded, R3-F1):
      1. the domain's **default owning role** if present on the roster;
      2. else a persona whose ``answers_for`` **explicitly names the domain** (high-confidence);
      3. else ``None`` — the domain is skipped, never drafted by a non-owning persona.
    """
    spec = get_domain(domain_name)
    if spec is None:
        return None
    by_id = {b.role_id: b for b in briefs}
    if spec.owning_role in by_id:
        return spec.owning_role
    for brief in briefs:  # roster order = deterministic tie-break
        if _answers_for_names_domain(brief, domain_name):
            return brief.role_id
    return None
