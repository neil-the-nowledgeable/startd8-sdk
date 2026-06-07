"""Whole-backend assembly — one call → every owned artifact (Python contract-codegen).

Aggregates the per-layer renderers into the full app spine as ``(relative_path, text)`` pairs, in a
deterministic order: package marker → Pydantic models → SQLModel tables → FastAPI routers/db/main →
HTMX web.py + templates → derived export/ai_schemas/completeness. Used by ``startd8 generate
backend`` (Step 7) and the pilot (Step 8).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from .crud_generator import (
    CANONICAL_LAYOUT,
    render_db,
    render_main,
    render_routers,
)
from .derived import _load_completeness_manifest, render_derived, render_requirements
from .htmx_generator import render_ui
from .pydantic_renderer import render_pydantic_models
from .sqlmodel_renderer import render_sqlmodel_tables
from .test_emitter import (
    COMPLETENESS_TESTS_PATH,
    CONTRACT_TESTS_PATH,
    render_completeness_tests,
    render_contract_tests,
)


def render_backend(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    manifest_text: Optional[str] = None,
    human_inputs_text: Optional[str] = None,
    ai_agent_spec: Optional[str] = None,
    pages_text: Optional[str] = None,
    pages_app_dir: Optional[Path] = None,
    authoring: bool = False,
    completeness_text: Optional[str] = None,
    views_text: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """Every backend artifact as ``(relative_path, text)`` pairs, in canonical write order.

    Includes an **empty ``app/__init__.py``** package marker (not owned/drift-tracked — it carries
    no header). All other files are owned, ``$0.00``-skip-recognized, and build-gateable.

    When *manifest_text* (``ai_passes.yaml``) is provided, the owned **AI layer** (FR-MA-1..6) is
    assembled too: service wrapper, edge schemas, per-pass harnesses, AI router, and ``app/server.py``
    — driven by the manifest + *human_inputs_text* (``human_inputs.yaml``, the C-4 field policy).

    *views_text* (``views.yaml``) feeds only its top-level ``forms:`` section here — per-entity
    post-create behavior (FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md FR-4); the ``views:`` section
    belongs to ``generate views`` (view_codegen).
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
    # app/web.py + templates (+ nav, + per-entity post-create behavior from views.yaml `forms:`)
    out.extend(render_ui(schema_text, source_file, pages_text, views_text))
    out.extend(
        render_derived(schema_text, source_file, completeness_text=completeness_text)
    )  # export / ai_schemas / completeness (completeness weighted when a manifest is given)
    out.append((
        "requirements.txt",
        render_requirements(schema_text, source_file, authoring=authoring, ai=bool(manifest_text)),
    ))
    # Rung-4 semantic tests over the contract (round-trip / field-presence / enum-domain). Owned,
    # $0, drift-checked; they ARE the gate the Python build runs (pytest).
    out.append((CONTRACT_TESTS_PATH, render_contract_tests(schema_text, source_file)))
    out.append((
        COMPLETENESS_TESTS_PATH,
        render_completeness_tests(
            schema_text, source_file, manifest=_load_completeness_manifest(completeness_text)
        ),
    ))  # FR-9: the completeness formula as an executable, drift-checked invariant
    if pages_text:
        from .pages_generator import render_pages

        out.extend(render_pages(schema_text, pages_text, source_file, app_dir=pages_app_dir))
        if authoring:
            from .pages_authoring import render_authoring

            out.extend(render_authoring(schema_text, source_file))
    if manifest_text:
        from .ai_layer import render_ai_layer

        out.extend(render_ai_layer(
            schema_text, manifest_text, human_inputs_text, source_file,
            ai_agent_spec=ai_agent_spec,
        ))
    return tuple(out)
