"""Whole-backend assembly — one call → every owned artifact (Python contract-codegen).

Aggregates the per-layer renderers into the full app spine as ``(relative_path, text)`` pairs, in a
deterministic order: package marker → Pydantic models → SQLModel tables → FastAPI routers/db/main →
HTMX web.py + templates → derived export/ai_schemas/completeness. Used by ``startd8 generate
backend`` (Step 7) and the pilot (Step 8).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .crud_generator import (
    CANONICAL_LAYOUT,
    render_db,
    render_main,
    render_routers,
)
from .derived import render_derived, render_requirements
from .htmx_generator import render_ui
from .pydantic_renderer import render_pydantic_models
from .sqlmodel_renderer import render_sqlmodel_tables


def render_backend(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    manifest_text: Optional[str] = None,
    human_inputs_text: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """Every backend artifact as ``(relative_path, text)`` pairs, in canonical write order.

    Includes an **empty ``app/__init__.py``** package marker (not owned/drift-tracked — it carries
    no header). All other files are owned, ``$0.00``-skip-recognized, and build-gateable.

    When *manifest_text* (``ai_passes.yaml``) is provided, the owned **AI layer** (FR-MA-1..6) is
    assembled too: service wrapper, edge schemas, per-pass harnesses, AI router, and ``app/server.py``
    — driven by the manifest + *human_inputs_text* (``human_inputs.yaml``, the C-4 field policy).
    """
    out: List[Tuple[str, str]] = [
        ("app/__init__.py", ""),
        (
            CANONICAL_LAYOUT["pydantic-models"],
            render_pydantic_models(schema_text, source_file=source_file).text,
        ),
        (
            CANONICAL_LAYOUT["sqlmodel-tables"],
            render_sqlmodel_tables(schema_text, source_file=source_file).text,
        ),
        (CANONICAL_LAYOUT["fastapi-routers"], render_routers(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-db"], render_db(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-main"], render_main(schema_text, source_file)),
    ]
    out.extend(render_ui(schema_text, source_file))  # app/web.py + templates
    out.extend(
        render_derived(schema_text, source_file)
    )  # export / ai_schemas / completeness
    out.append(("requirements.txt", render_requirements(schema_text, source_file)))
    if manifest_text:
        from .ai_layer import render_ai_layer

        out.extend(render_ai_layer(schema_text, manifest_text, human_inputs_text, source_file))
    return tuple(out)
