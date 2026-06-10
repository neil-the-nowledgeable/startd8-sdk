"""``flows:`` — the multi-step step-state flow declaration (P0-1 primitive), a views.yaml section.

Coexists with ``views:`` / ``forms:`` / ``filters:`` in views.yaml. Each flow declares a draft entity,
the column holding the current step, an ordered step list, and an optional ``on_finish`` registered
owned-fn. Strict: unknown entity → loud at parse; ``step_field`` column existence is validated at
render (where the schema is available).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import yaml

_KEYS = {"name", "draft_entity", "step_field", "steps", "on_finish"}


@dataclass(frozen=True)
class FlowSpec:
    name: str
    draft_entity: str
    step_field: str
    steps: Tuple[str, ...]
    on_finish: str = ""        # optional owned-fn name (tolerant registry hook)


def parse_flows(
    views_text: Optional[str], *, known_entities: frozenset = frozenset()
) -> Tuple[FlowSpec, ...]:
    """Parse the ``flows:`` section of views.yaml → FlowSpecs. Tolerant of absence."""
    data = yaml.safe_load(views_text or "") or {}
    if not isinstance(data, dict) or "flows" not in data:
        return ()
    raw = data["flows"] or []
    if not isinstance(raw, list):
        raise ValueError("views.yaml: `flows` must be a list")
    out = []
    seen = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"views.yaml: flow #{i} must be a mapping")
        unknown = set(entry) - _KEYS
        if unknown:
            raise ValueError(f"views.yaml: flow #{i} has unknown keys {sorted(unknown)}")
        for req in ("name", "draft_entity", "step_field", "steps"):
            if not entry.get(req):
                raise ValueError(f"views.yaml: flow #{i} missing required `{req}`")
        name = str(entry["name"])
        if name in seen:
            raise ValueError(f"views.yaml: duplicate flow name {name!r}")
        seen.add(name)
        entity = str(entry["draft_entity"])
        if known_entities and entity not in known_entities:
            raise ValueError(f"views.yaml: flow {name!r} references unknown entity {entity!r}")
        steps = entry["steps"]
        if not isinstance(steps, list) or not steps or not all(isinstance(s, str) for s in steps):
            raise ValueError(f"views.yaml: flow {name!r} `steps` must be a non-empty list of strings")
        if len(set(steps)) != len(steps):
            raise ValueError(f"views.yaml: flow {name!r} has duplicate step keys")
        out.append(FlowSpec(
            name=name, draft_entity=entity, step_field=str(entry["step_field"]),
            steps=tuple(steps), on_finish=str(entry.get("on_finish") or ""),
        ))
    return tuple(out)
