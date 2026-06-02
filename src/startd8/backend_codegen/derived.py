"""Deterministic derived-artifact emitters (Python contract-codegen, Step 6 / FR-6, FR-7, FR-8).

Three small *pure* emitters, all projected from the ``.prisma`` contract so they fit the shared
drift/$0.00-skip model uniformly (no LLM):

- **FR-7 export** → ``app/export.py``: ``to_json`` (lossless, sorted) + ``to_markdown`` (a
  deterministic layout — one ``# <Entity>`` section per entity in schema order, ``- field: value``
  lines in field order). JSON is the round-trip-faithful format; Markdown is presentation.
- **FR-8 AI tool/IO schemas** → ``app/ai_schemas.py``: re-projects the Step 1 Pydantic models as the
  AI passes' structured-output contract — ``AI_SCHEMAS`` (entity → model class) + ``json_schema()``.
- **FR-6 completeness** → ``app/completeness.py``: ``compute_completeness(present)`` → score +
  priority-ordered nudges.

**OQ-4 (resolved, v1):** completeness signals are *not* derivable from the schema alone (the
``.prisma`` doesn't say "≥3 confirmed ProofPoints"). v1 ships a schema-derived **presence** rule
(each entity with ≥1 row contributes; nudge per absent entity). Domain-weighted thresholds come from
a declared **manifest** — the documented refinement, deferred.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema


def _header(source_file: str, sha: str, kind: str) -> str:
    return (
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {sha}"
    )


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _py_list(items: List[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def render_export(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/export.py`` — ``to_json`` (lossless) + ``to_markdown`` (deterministic layout)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    fields = {n: [f.name for f in schema.scalar_fields(n)] for n in names}

    entities_lit = _py_list(names)
    fields_lit = (
        "{\n" + "".join(f"    {n!r}: {_py_list(fields[n])},\n" for n in names) + "}"
    )

    header = _header(source_file, sha, "python-export")
    body = (
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any, Dict, List\n\n"
        f"ENTITY_ORDER: List[str] = {entities_lit}\n"
        f"FIELDS: Dict[str, List[str]] = {fields_lit}\n\n\n"
        "def to_json(payload: Dict[str, List[Dict[str, Any]]]) -> str:\n"
        '    """Lossless, stable JSON (sorted keys) — the round-trip-faithful export format."""\n'
        "    return json.dumps(payload, indent=2, sort_keys=True, default=str)\n\n\n"
        "def to_markdown(payload: Dict[str, List[Dict[str, Any]]]) -> str:\n"
        '    """Deterministic Markdown: a section per entity (schema order), field lines in order."""\n'
        "    lines: List[str] = []\n"
        "    for entity in ENTITY_ORDER:\n"
        "        lines.append(f'# {entity}')\n"
        "        for row in payload.get(entity, []):\n"
        "            for field in FIELDS[entity]:\n"
        "                lines.append(f'- {field}: {row.get(field, \"\")}')\n"
        "            lines.append('')\n"
        "    return '\\n'.join(lines)\n"
    )
    return header + "\n\n" + body


def render_ai_schemas(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``app/ai_schemas.py`` — the AI passes' structured-output contract (FR-8)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    header = _header(source_file, sha, "python-ai-schemas")
    imports = (
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, Type\n\n"
    )
    if names:
        imports += (
            "from pydantic import BaseModel\n\n"
            "from .models import " + ", ".join(f"{n}Schema" for n in names) + "\n"
        )
    else:
        imports += "from pydantic import BaseModel\n"

    registry = (
        "AI_SCHEMAS: Dict[str, Type[BaseModel]] = {\n"
        + "".join(f"    {n!r}: {n}Schema,\n" for n in names)
        + "}"
    )
    helper = (
        "def json_schema(entity: str) -> Dict[str, Any]:\n"
        '    """The JSON Schema an AI pass targets for structured output of *entity*."""\n'
        "    return AI_SCHEMAS[entity].model_json_schema()\n"
    )
    return header + "\n\n" + imports + "\n\n" + registry + "\n\n\n" + helper


def render_completeness(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``app/completeness.py`` — presence-based score + nudges (FR-6; OQ-4 v1 default)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    entities_lit = _py_list(names)

    header = _header(source_file, sha, "python-completeness")
    body = (
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Dict, List\n\n"
        f"ENTITIES: List[str] = {entities_lit}\n\n\n"
        "@dataclass\n"
        "class CompletenessResult:\n"
        "    score: float  # 0.0 .. 1.0\n"
        "    nudges: List[str]  # priority-ordered, schema order\n\n\n"
        "def compute_completeness(present: Dict[str, int]) -> CompletenessResult:\n"
        '    """Presence rule (OQ-4 v1): score = fraction of entities with >=1 row; one nudge per\n'
        "    absent entity. Domain-weighted thresholds (e.g. >=3 ProofPoints) are a manifest\n"
        '    refinement, deferred."""\n'
        "    if not ENTITIES:\n"
        "        return CompletenessResult(score=1.0, nudges=[])\n"
        "    have = [e for e in ENTITIES if present.get(e, 0) > 0]\n"
        "    score = round(len(have) / len(ENTITIES), 4)\n"
        "    nudges = [f'Add at least one {e}.' for e in ENTITIES if present.get(e, 0) == 0]\n"
        "    return CompletenessResult(score=score, nudges=nudges)\n"
    )
    return header + "\n\n" + body


def render_derived(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> Tuple[Tuple[str, str], ...]:
    """All derived artifacts as ``(relative_path, text)`` pairs: export, ai_schemas, completeness."""
    return (
        ("app/export.py", render_export(schema_text, source_file)),
        ("app/ai_schemas.py", render_ai_schemas(schema_text, source_file)),
        ("app/completeness.py", render_completeness(schema_text, source_file)),
    )


# Artifact-kind → path, for CANONICAL_LAYOUT extension.
DERIVED_LAYOUT: Dict[str, str] = {
    "python-export": "app/export.py",
    "python-ai-schemas": "app/ai_schemas.py",
    "python-completeness": "app/completeness.py",
}
