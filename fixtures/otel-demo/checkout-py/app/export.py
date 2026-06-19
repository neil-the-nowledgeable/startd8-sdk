# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-export
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

import json
from typing import Any, Dict, List

ENTITY_ORDER: List[str] = ["PlaceOrderSession"]
FIELDS: Dict[str, List[str]] = {
    'PlaceOrderSession': ["id", "userId", "email", "createdAt"],
}


def to_json(payload: Dict[str, List[Dict[str, Any]]]) -> str:
    """Lossless, stable JSON (sorted keys) — the round-trip-faithful export format."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def to_markdown(payload: Dict[str, List[Dict[str, Any]]]) -> str:
    """Deterministic Markdown: a section per entity (schema order), field lines in order."""
    lines: List[str] = []
    for entity in ENTITY_ORDER:
        lines.append(f'# {entity}')
        for row in payload.get(entity, []):
            for field in FIELDS[entity]:
                lines.append(f'- {field}: {row.get(field, "")}')
            lines.append('')
    return '\n'.join(lines)
