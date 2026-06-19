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
from .health_renderer import render_health
from .openapi_contract_renderer import render_openapi_contract
from .openapi_client_renderer import render_http_client
from .editor_generator import render_editors
from .flow_generator import render_flows
from .htmx_generator import render_ui
from .pydantic_renderer import render_pydantic_models
from .sqlmodel_renderer import render_sqlmodel_tables
from .test_emitter import (
    COMPLETENESS_TESTS_PATH,
    CONTRACT_TESTS_PATH,
    HEALTH_TESTS_PATH,
    OPENAPI_CONTRACT_TESTS_PATH,
    ROUTE_SMOKE_TESTS_PATH,
    render_completeness_tests,
    render_contract_tests,
    render_health_tests,
    render_openapi_contract_tests,
    render_route_smoke_tests,
    render_cross_context_smoke_tests,
    CROSS_CONTEXT_SMOKE_TESTS_PATH,
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
    display_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    api_text: Optional[str] = None,
    overlay_warnings: Optional[List[str]] = None,
    contexts_text: Optional[str] = None,
    project_root: Optional[str] = None,
    deployment_mode: str = "installed",
    tenant_owner_field: Optional[str] = None,
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
        (
            CANONICAL_LAYOUT["fastapi-routers"],
            render_routers(schema_text, source_file, tenant_owner_field=tenant_owner_field),
        ),
        (CANONICAL_LAYOUT["fastapi-db"], render_db(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-main"], render_main(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-health"], render_health(schema_text, source_file)),
        (
            CANONICAL_LAYOUT["python-openapi-contract"],
            render_openapi_contract(
                schema_text,
                source_file,
                api_text=api_text,
                overlay_warnings=overlay_warnings,
                manifest_text=manifest_text,
                pages_text=pages_text,
                views_text=views_text,
                imports_text=imports_text,
            ),
        ),
        ("clients/__init__.py", ""),
        (
            CANONICAL_LAYOUT["python-openapi-client"],
            render_http_client(
                schema_text,
                source_file,
                api_text=api_text,
                manifest_text=manifest_text,
                pages_text=pages_text,
                views_text=views_text,
                imports_text=imports_text,
            ),
        ),
    ]
    # app/web.py + templates (+ nav, + per-entity post-create behavior from views.yaml `forms:`)
    out.extend(render_ui(
        schema_text, source_file, pages_text, views_text, display_text,
        tenant_owner_field=tenant_owner_field,
    ))
    # P0-1: step-state flow routers + shells from views.yaml `flows:` (empty when none declared)
    out.extend(render_flows(schema_text, views_text or ""))
    # FR-ED: bulk child-field editors from views.yaml `editors:` (empty when none declared)
    out.extend(render_editors(schema_text, views_text or ""))
    out.extend(
        render_derived(schema_text, source_file, completeness_text=completeness_text)
    )  # export / ai_schemas / completeness (completeness weighted when a manifest is given)
    # FR-IMP-1: app/importer.py (from_json upsert), opt-in — emitted ONLY when imports.yaml is
    # present (R2-S2 conditional emission, the `if manifest_text:` precedent). It imports
    # ENTITY_ORDER/FIELDS from app/export.py, so it must follow render_derived. Absent manifest ⇒
    # no importer, byte-identical to today.
    if imports_text:
        from .import_codegen import render_import

        out.append((CANONICAL_LAYOUT["python-import"], render_import(schema_text, imports_text, source_file)))
        # FR-IMP-6: the paste/upload surface — emitted only when an import declares `surface: true`.
        from .import_surface import render_import_surface, surface_enabled

        if surface_enabled(imports_text):
            out.append((
                CANONICAL_LAYOUT["python-import-surface"],
                render_import_surface(schema_text, imports_text, source_file),
            ))
    out.append((
        "requirements.txt",
        render_requirements(schema_text, source_file, authoring=authoring, ai=bool(manifest_text)),
    ))
    # Rung-4 semantic tests over the contract (round-trip / field-presence / enum-domain). Owned,
    # $0, drift-checked; they ARE the gate the Python build runs (pytest).
    out.append((CONTRACT_TESTS_PATH, render_contract_tests(schema_text, source_file)))
    out.append((HEALTH_TESTS_PATH, render_health_tests(schema_text, source_file)))
    out.append((
        OPENAPI_CONTRACT_TESTS_PATH,
        render_openapi_contract_tests(
            schema_text,
            source_file,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=views_text,
            imports_text=imports_text,
            api_text=api_text,
        ),
    ))
    out.append((
        COMPLETENESS_TESTS_PATH,
        render_completeness_tests(
            schema_text, source_file, manifest=_load_completeness_manifest(completeness_text)
        ),
    ))  # FR-9: the completeness formula as an executable, drift-checked invariant
    # Rung-5 floor (strtd8 §8 F-8): generated HTTP smoke — every mounted GET
    # route (incl. user_routers/views) × every seeds/test-user-* fixture.
    out.append((
        ROUTE_SMOKE_TESTS_PATH, render_route_smoke_tests(schema_text, source_file),
    ))
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
    if contexts_text:
        from .context_client_renderer import render_context_clients

        out.extend(
            render_context_clients(
                schema_text,
                contexts_text,
                source_file,
                api_text=api_text,
                manifest_text=manifest_text,
                pages_text=pages_text,
                views_text=views_text,
                imports_text=imports_text,
                project_root=project_root,
            )
        )
        out.append((
            CROSS_CONTEXT_SMOKE_TESTS_PATH,
            render_cross_context_smoke_tests(schema_text, contexts_text, source_file),
        ))
    # FR-CFG-7 / D11: app/settings.py is emitted ONLY in deployed mode. Installed mode is the
    # settings-absent default and stays byte-identical to today (R4). settings.py — present here,
    # absent in installed — is the single file that differs between the two modes.
    if deployment_mode == "deployed":
        from .auth_renderer import render_auth_seam
        from .settings_renderer import render_settings

        out.append((
            CANONICAL_LAYOUT["python-settings"],
            render_settings(schema_text, source_file, mode=deployment_mode),
        ))
        # FR-IDN-2/M2: deployed mode also emits the reference auth seam (app/auth.py). A dependency
        # module the operator wires via user_routers.py — main.py stays unchanged.
        out.append((
            CANONICAL_LAYOUT["python-auth-seam"],
            render_auth_seam(schema_text, source_file),
        ))
    return tuple(out)
