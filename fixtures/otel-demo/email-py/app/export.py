# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-export
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

import json
from typing import Any, Dict, List

ENTITY_ORDER: List[str] = ["OrderConfirmation"]
FIELDS: Dict[str, List[str]] = {
    'OrderConfirmation': ["id", "orderId", "email", "createdAt"],
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
