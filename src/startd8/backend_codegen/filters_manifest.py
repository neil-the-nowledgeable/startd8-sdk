"""``filters:`` — the per-entity list-filter declaration (P0-2), a disjoint views.yaml section.

Coexists with ``views:`` (composite views) and ``forms:`` (post-create behavior) in the same
``views.yaml``; this reads only ``filters:``. Each entity declares facet fields (exact / JSON-array
membership) and free-text search fields. Strict: unknown entity → loud. Field validation against the
contract happens at backend render (where the schema is available).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import yaml


@dataclass(frozen=True)
class EntityFilter:
    facets: Tuple[str, ...] = ()      # narrowing controls (scalar == / list membership)
    search: Tuple[str, ...] = ()      # free-text (case-insensitive substring, OR'd)


_KEYS = {"facets", "search"}


def parse_filters(
    views_text: Optional[str], *, known_entities: frozenset = frozenset()
) -> Dict[str, EntityFilter]:
    """Parse the ``filters:`` section of views.yaml → {entity: EntityFilter}. Tolerant of absence."""
    data = yaml.safe_load(views_text or "") or {}
    if not isinstance(data, dict) or "filters" not in data:
        return {}
    raw = data["filters"] or {}
    if not isinstance(raw, dict):
        raise ValueError("views.yaml: `filters` must be a mapping of entity -> {facets, search}")
    out: Dict[str, EntityFilter] = {}
    for entity, spec in raw.items():
        if known_entities and entity not in known_entities:
            raise ValueError(f"views.yaml: filters references unknown entity {entity!r}")
        if not isinstance(spec, dict):
            raise ValueError(f"views.yaml: filters[{entity}] must be a mapping")
        unknown = set(spec) - _KEYS
        if unknown:
            raise ValueError(f"views.yaml: filters[{entity}] has unknown keys {sorted(unknown)}")
        facets = tuple(spec.get("facets", ()) or ())
        search = tuple(spec.get("search", ()) or ())
        if not all(isinstance(f, str) for f in (*facets, *search)):
            raise ValueError(f"views.yaml: filters[{entity}] facets/search must be field-name strings")
        if facets or search:
            out[entity] = EntityFilter(facets=facets, search=search)
    return out
