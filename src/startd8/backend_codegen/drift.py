"""Drift / staleness checking for the Python contract-codegen path.

The Python sibling of ``frontend_codegen.drift``. The two-stage check is the same operational
idea (R2-S6) — distinguish **stale** (schema changed, file not regenerated; caught cheaply by the
embedded ``schema-sha256``) from **tampered** (schema unchanged, bytes differ from a fresh
render; caught by a full re-render comparison). ``tampered`` states only that the bytes differ —
a hand-edit and a different generation invocation (other flags/manifests than this check) are
both plausible causes, and the check cannot tell which (strtd8 F-2, 2026-06-06). The module is
*mirrored, not reused* from the TS side: a ``.py`` file carries a ``#`` GENERATED
header (not the TS ``//``), and the re-render goes through :func:`render_pydantic_models`. Both are
hardwired in ``frontend_codegen.drift``, so the regexes and renderer differ here.

Exit-code contract: ``0`` in-sync, ``1`` drift (stale/tampered/missing), ``2`` error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..frontend_codegen.schema_renderer import schema_sha256

IN_SYNC = 0
DRIFT = 1
ERROR = 2

_HEADER_SHA_RE = re.compile(r"#\s*schema-sha256:\s*([0-9a-f]{64})")
_HEADER_SRC_RE = re.compile(r"#\s*GENERATED from\s+(\S+)")
_HEADER_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_HEADER_ENTITY_RE = re.compile(r"#\s*startd8-entity:\s*(\S+)")
# settings.py self-describes its baked deployment mode (FR-CFG-7a) so the schema-only skip-hook
# re-renders it from the file's OWN header — no app.yaml read (the ai-agent-spec precedent).
_HEADER_MODE_RE = re.compile(r"#\s*startd8-mode:\s*(\S+)")
# Tenant-scoped artifacts (routers.py / web.py, Tier B) self-describe the owner FK the same way, so
# the schema-only skip-hook re-renders the scoped file without app.yaml (FR-TEN-2/3).
_HEADER_TENANT_RE = re.compile(r"#\s*startd8-tenant:\s*(\S+)")
# AI-layer artifacts (FR-MA-5) derive from two extra inputs and carry two extra hashes.
_HEADER_PASSES_SHA_RE = re.compile(r"#\s*passes-sha256:\s*([0-9a-f]{64})")
_HEADER_HUMAN_SHA_RE = re.compile(r"#\s*human-inputs-sha256:\s*([0-9a-f]{64})")
_HEADER_AI_AGENT_RE = re.compile(r"#\s*ai-agent-spec:\s*(\S+)")
# Content-page artifacts derive from one extra input (pages.yaml) and carry one extra hash.
_HEADER_PAGES_SHA_RE = re.compile(r"#\s*pages-sha256:\s*([0-9a-f]{64})")
# Form-behavior artifacts derive from one extra input (views.yaml `forms:`) and carry one extra hash.
_HEADER_FORMS_SHA_RE = re.compile(r"#\s*forms-sha256:\s*([0-9a-f]{64})")
# The import owned-kind (FR-IMP-1) derives from one extra input (imports.yaml) → one extra hash.
_HEADER_IMPORTS_SHA_RE = re.compile(r"#\s*imports-sha256:\s*([0-9a-f]{64})")
# Role 2: openapi contract may derive from schema + api.yaml overlay.
_HEADER_API_SHA_RE = re.compile(r"#\s*api-sha256:\s*([0-9a-f]{64})")
_HEADER_CONTEXTS_SHA_RE = re.compile(r"#\s*contexts-sha256:\s*([0-9a-f]{64})")
_HEADER_CONTRACT_SHA_RE = re.compile(r"#\s*contract-sha256:\s*([0-9a-f]{64})")
_GENERATED_MARKER = "# GENERATED from"

# Artifact kinds whose drift derives from three inputs (schema + ai_passes + human_inputs). Kept in
# sync with ``ai_layer.AI_KINDS`` (literal here to avoid an import cycle at module load).
_AI_KINDS: frozenset = frozenset(
    {
        "ai-service",
        "ai-edge-schemas",
        "ai-pass",
        "ai-router",
        "ai-ui-router",        # FR-AIT: app/ai/ui.py (kept in sync with ai_layer.AI_KINDS)
        "ai-server",
        "ai-tests-edge",
        "ai-tests-keyless",
        "ai-tests-cost",
        "ai-tests-pass",
    }
)

# Artifact kinds whose drift derives from two inputs (schema + pages.yaml). Kept in sync with
# ``pages_generator.PAGES_KINDS`` (literal here to avoid an import cycle at module load).
_PAGES_KINDS: frozenset = frozenset({"pages-base", "pages-router", "pages-content"})

# Artifact kinds whose drift derives from two inputs (schema + views.yaml). web.py only carries
# ``fastapi-web-forms`` when generated WITH a forms manifest (else plain ``fastapi-web``) — the
# htmx-base/pages-base precedent: a distinct kind per dep-set. The ``flow-*`` kinds (FR-ED-15) are
# views.yaml-derived too: ``fastapi-flow``/``flow-shell`` re-render a single flow BY NAME (the
# ``startd8-entity`` slot), ``flow-aggregator`` re-renders the whole ``app/flows/__init__.py``.
# Previously ``fastapi-flow`` was registered nowhere → freshly-generated flow apps failed ``--check``.
_FORMS_KINDS: frozenset = frozenset(
    {
        "fastapi-web-forms", "htmx-created",
        "fastapi-flow", "flow-shell", "flow-aggregator",          # flows (FR-ED-15)
        "fastapi-editor", "editor-form", "editor-aggregator",     # bulk child-field editors (FR-ED-10)
    }
)

# settings.py derives from the schema + a SELF-EMBEDDED mode (FR-CFG-7a). Unlike the manifest-backed
# kinds above, its extra input (the mode) lives in the file's own header, so it needs no external
# input at drift time — the schema-only skip-hook can verify it.
_SETTINGS_KINDS: frozenset = frozenset({"python-settings"})

# The import owned-kinds (FR-IMP-1 importer + FR-IMP-6 surface) derive from two inputs (schema +
# imports.yaml). Kept in sync with ``import_codegen``/``import_surface`` (literal here to avoid a
# module-load import cycle).
_IMPORTS_KINDS: frozenset = frozenset({"python-import", "python-import-surface"})
_CONTEXT_CLIENT_KINDS: frozenset = frozenset({"python-context-client"})
_CONTEXT_SMOKE_KINDS: frozenset = frozenset({"python-tests-cross-context"})
_CONTEXT_INTEGRATION_KINDS: frozenset = frozenset({"python-context-integration"})


def _renderers(
    completeness_text: Optional[str] = None,
    forms_text: Optional[str] = None,
    display_text: Optional[str] = None,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    contexts_text: Optional[str] = None,
    project_root: Optional[str] = None,
    form_prose_text: Optional[str] = None,
) -> Dict[str, Callable[[str, str, Optional[str]], str]]:
    """Map artifact-kind → a ``(schema_text, source_file, entity) -> text`` renderer.

    Imported lazily so this module has no load-order dependency on the renderers. Each backend
    artifact tags its header with ``# startd8-artifact: <kind>`` (and, for per-entity templates,
    ``# startd8-entity: <Name>``) so a single provider/drift path re-renders it with the *right*
    renderer — every backend artifact carries the GENERATED marker, so the kind+entity tags are
    what disambiguate them. ``entity`` is ``None`` for app-wide artifacts.
    """
    from .auth_renderer import render_auth_seam as _render_auth_seam
    from .crud_generator import render_db, render_main, render_routers
    from .health_renderer import render_health
    from .openapi_contract_renderer import render_openapi_contract
    from .openapi_client_renderer import render_http_client
    from .derived import (
        render_ai_schemas,
        _load_completeness_manifest,
        render_completeness,
        render_export,
        render_requirements,
    )
    _cmpl = _load_completeness_manifest(completeness_text)  # weighted regen must match generate
    from .htmx_generator import (
        render_base_template,
        render_confirm_template,
        render_detail_template,
        render_field_error_template,
        render_form_template,
        render_list_template,
        render_row_template,
        render_web,
    )
    from .pages_authoring import (
        render_pages_admin,
        render_pages_admin_template,
        render_pages_io,
    )
    from .pydantic_renderer import render_pydantic_models
    from .sqlmodel_renderer import render_sqlmodel_tables
    from .test_emitter import (
        render_completeness_tests,
        render_contract_tests,
        render_health_tests,
        render_openapi_contract_tests,
        render_route_smoke_tests,
        render_cross_context_smoke_tests,
    )
    from .context_otel_renderer import render_context_otel
    # P0-2/FR-DM: list/row/detail re-render must use the SAME filter (views.yaml) + display
    # (display.yaml) inputs the generate path used, or a filtered/display-configured template
    # false-flags drift. Parsed lazily per entity from the threaded manifests.
    from .display_manifest import parse_display
    from .filters_manifest import parse_filters
    from ..languages.prisma_parser import parse_prisma_schema as _pps

    def _filt(s, e):
        return parse_filters(forms_text, known_entities=frozenset(_pps(s).models)).get(e) if forms_text else None

    def _disp(s, e):
        if not display_text:
            return None
        return parse_display(display_text, _pps(s))[0].get(e)

    from .form_prose import parse_form_prose as _parse_form_prose

    def _fp(s, e):
        # form.html re-render must use the SAME form_prose.yaml input as generate, or a help/intro-
        # configured form false-flags drift (FR-FH-3). Field-existence validation already ran at
        # generate; re-render only needs this entity's FormProse, so we parse without the known sets.
        if not form_prose_text or not e:
            return None
        return _parse_form_prose(form_prose_text).get(e)

    from .context_client_renderer import render_context_client
    from .context_integration_renderer import render_context_clients_module
    from .context_manifest import parse_contexts

    def _context_client_renderer(s: str, sf: str, e: Optional[str]) -> str:
        if not contexts_text or not e:
            return ""
        ctx_by_id = {c.id: c for c in parse_contexts(contexts_text)}
        ctx = ctx_by_id.get(e)
        if ctx is None:
            return ""
        return render_context_client(
            s,
            contexts_text,
            ctx,
            sf,
            api_text=api_text,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
            project_root=project_root,
        )

    return {
        "pydantic-models": lambda s, sf, e: render_pydantic_models(
            s, source_file=sf
        ).text,
        "sqlmodel-tables": lambda s, sf, e: render_sqlmodel_tables(
            s, source_file=sf
        ).text,
        "fastapi-routers": lambda s, sf, e: render_routers(s, sf),
        "fastapi-db": lambda s, sf, e: render_db(s, sf),
        "fastapi-main": lambda s, sf, e: render_main(s, sf),
        "fastapi-health": lambda s, sf, e: render_health(s, sf),
        "python-openapi-contract": lambda s, sf, e: render_openapi_contract(
            s,
            sf,
            api_text=api_text,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
        ),
        "python-openapi-client": lambda s, sf, e: render_http_client(
            s,
            sf,
            api_text=api_text,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
        ),
        "python-context-otel": lambda s, sf, e: render_context_otel(sf, s),
        "fastapi-web": lambda s, sf, e: render_web(s, sf),
        "htmx-base": lambda s, sf, e: render_base_template(s, sf),
        "htmx-field-error": lambda s, sf, e: render_field_error_template(s, sf),
        "htmx-list": lambda s, sf, e: render_list_template(s, sf, e, _filt(s, e), _disp(s, e)),
        "htmx-row": lambda s, sf, e: render_row_template(s, sf, e, _disp(s, e)),
        "htmx-confirm": lambda s, sf, e: render_confirm_template(s, sf, e),
        "htmx-detail": lambda s, sf, e: render_detail_template(s, sf, e, _disp(s, e)),
        "htmx-form": lambda s, sf, e: render_form_template(s, sf, e, _fp(s, e)),
        "python-export": lambda s, sf, e: render_export(s, sf),
        "python-ai-schemas": lambda s, sf, e: render_ai_schemas(s, sf),
        "python-completeness": lambda s, sf, e: render_completeness(s, sf, manifest=_cmpl),
        "python-auth-seam": lambda s, sf, e: _render_auth_seam(s, sf),  # deployed-only (FR-IDN-2/M2)
        "python-requirements": lambda s, sf, e: render_requirements(s, sf),
        "python-requirements-authoring": lambda s, sf, e: render_requirements(s, sf, authoring=True),
        "python-requirements-ai": lambda s, sf, e: render_requirements(s, sf, ai=True),
        "python-requirements-authoring-ai": lambda s, sf, e: render_requirements(
            s, sf, authoring=True, ai=True
        ),
        "pages-io": lambda s, sf, e: render_pages_io(s, sf),
        "pages-admin": lambda s, sf, e: render_pages_admin(s, sf),
        "pages-admin-tmpl": lambda s, sf, e: render_pages_admin_template(s, sf),
        "python-tests-contract": lambda s, sf, e: render_contract_tests(s, sf),
        "python-tests-health": lambda s, sf, e: render_health_tests(s, sf),
        "python-tests-openapi-contract": lambda s, sf, e: render_openapi_contract_tests(
            s,
            sf,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
            api_text=api_text,
        ),
        "python-tests-completeness": lambda s, sf, e: render_completeness_tests(s, sf, manifest=_cmpl),
        "python-tests-routes": lambda s, sf, e: render_route_smoke_tests(s, sf),
        "python-tests-cross-context": lambda s, sf, e: (
            render_cross_context_smoke_tests(s, contexts_text or "", sf)
            if contexts_text
            else ""
        ),
        "python-context-integration": lambda s, sf, e: (
            render_context_clients_module(
                s, contexts_text or "", sf, project_root=project_root
            )
            if contexts_text
            else ""
        ),
        "python-context-client": _context_client_renderer,
    }


def embedded_artifact_kind(ondisk_text: str) -> Optional[str]:
    """The ``startd8-artifact`` kind recorded in a generated file's header, or ``None``."""
    m = _HEADER_KIND_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_entity(ondisk_text: str) -> Optional[str]:
    """The ``startd8-entity`` name recorded in a per-entity template header, or ``None``."""
    m = _HEADER_ENTITY_RE.search(ondisk_text or "")
    return m.group(1) if m else None


@dataclass(frozen=True)
class DriftResult:
    """Outcome of a drift check. ``exit_code`` follows the contract above."""

    status: str  # "in_sync" | "stale" | "tampered" | "missing"
    exit_code: int
    detail: str


def embedded_schema_sha(ondisk_text: str) -> Optional[str]:
    """The ``schema-sha256`` recorded in a generated file's header, or ``None``."""
    m = _HEADER_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_source_file(ondisk_text: str) -> Optional[str]:
    """The ``GENERATED from <source_file>`` label recorded in a generated header, or ``None``."""
    m = _HEADER_SRC_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_passes_sha(ondisk_text: str) -> Optional[str]:
    """The ``passes-sha256`` recorded in an AI-layer file's header, or ``None``."""
    m = _HEADER_PASSES_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_human_sha(ondisk_text: str) -> Optional[str]:
    """The ``human-inputs-sha256`` recorded in an AI-layer file's header, or ``None``."""
    m = _HEADER_HUMAN_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_pages_sha(ondisk_text: str) -> Optional[str]:
    """The ``pages-sha256`` recorded in a content-page file's header, or ``None``."""
    m = _HEADER_PAGES_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_forms_sha(ondisk_text: str) -> Optional[str]:
    """The ``forms-sha256`` recorded in a forms-configured file's header, or ``None``."""
    m = _HEADER_FORMS_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_imports_sha(ondisk_text: str) -> Optional[str]:
    """The ``imports-sha256`` recorded in the import owned-kind's header, or ``None`` (FR-IMP-1)."""
    m = _HEADER_IMPORTS_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_api_sha(ondisk_text: str) -> Optional[str]:
    """The ``api-sha256`` recorded in an API-overlay contract header, or ``None`` (Role 2)."""
    m = _HEADER_API_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_contexts_sha(ondisk_text: str) -> Optional[str]:
    """The ``contexts-sha256`` recorded in a context-client header, or ``None`` (Role 3)."""
    m = _HEADER_CONTEXTS_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_contract_sha(ondisk_text: str) -> Optional[str]:
    """The ``contract-sha256`` recorded in a context-client header, or ``None`` (Role 3)."""
    m = _HEADER_CONTRACT_SHA_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_ai_agent_spec(ondisk_text: str) -> Optional[str]:
    """The ``ai-agent-spec`` baked into a generated service.py header, or ``None``.

    Self-describing so drift re-renders the file with the same spec it was
    generated with (a custom provider must not read as drift). Only the
    ``ai-service`` artifact carries this line.
    """
    m = _HEADER_AI_AGENT_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def ai_layer_stale_reason(
    ondisk_text: str,
    *,
    schema_sha: str,
    passes_sha: str,
    human_sha: str,
) -> Optional[str]:
    """For an AI-layer file, return why it is **stale**, or ``None`` if all three inputs match.

    An AI-layer artifact derives from three inputs (schema + ai_passes + human_inputs), so it is
    stale if **any one** of the embedded hashes differs from the current input hash (FR-MA-5). A
    missing embedded hash counts as stale (header was stripped or predates the AI-layer format).
    This is the pure three-hash core; :func:`check_drift` (wired in M-C) calls it for ``_AI_KINDS``.
    """
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("ai_passes", embedded_passes_sha(ondisk_text), passes_sha),
        ("human_inputs", embedded_human_sha(ondisk_text), human_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def embedded_mode(ondisk_text: str) -> Optional[str]:
    """The ``startd8-mode`` baked into a generated ``settings.py`` header, or ``None`` (FR-CFG-7a).

    Self-describing so drift re-renders the file with the same mode it was generated with — the
    schema-only skip-hook needs no ``app.yaml`` (mirrors :func:`embedded_ai_agent_spec`).
    """
    m = _HEADER_MODE_RE.search(ondisk_text or "")
    return m.group(1) if m else None


def embedded_tenant_field(ondisk_text: str) -> Optional[str]:
    """The ``startd8-tenant`` owner-FK baked into a scoped routers/web header, or ``None`` (FR-TEN-2).

    Self-describing so the schema-only skip-hook re-renders the scoped file with the same owner field
    it was generated with — no ``app.yaml`` (mirrors :func:`embedded_mode`).
    """
    m = _HEADER_TENANT_RE.search(ondisk_text or "")
    return m.group(1) if m else None


# Artifact kinds whose bytes may be tenant-scoped (Tier B). They self-describe the owner FK in their
# header; absent → today's unscoped output. Re-rendered with the embedded tenant, schema-only.
# (``fastapi-web-forms`` is NOT here — it routes through _check_forms_drift, which threads the tenant.)
_TENANT_AWARE_KINDS: frozenset = frozenset({"fastapi-routers", "fastapi-web"})


def _check_tenant_aware_drift(schema_text, ondisk_text, source_file, kind) -> DriftResult:
    """Drift for a possibly tenant-scoped file (routers.py / web.py): stale if the schema changed; else
    byte re-render using the **self-embedded owner FK** from the file's own header — no ``app.yaml``."""
    current_sha = schema_sha256(schema_text)
    embedded = embedded_schema_sha(ondisk_text)
    if embedded is None:
        return DriftResult("tampered", DRIFT, "no schema-sha256 header — file was not generated")
    if embedded != current_sha:
        return DriftResult(
            "stale", DRIFT,
            f"schema changed (header {embedded[:12]}… != current {current_sha[:12]}…) — regenerate",
        )
    tenant = embedded_tenant_field(ondisk_text)  # None → unscoped (today's output)
    from .crud_generator import render_routers
    from .htmx_generator import render_web

    builders = {
        "fastapi-routers": lambda: render_routers(schema_text, source_file, tenant_owner_field=tenant),
        "fastapi-web": lambda: render_web(schema_text, source_file, None, tenant_owner_field=tenant),
    }
    rendered = builders[kind]()
    if rendered != ondisk_text:
        return DriftResult(
            "tampered", DRIFT,
            "owned tenant-aware file differs from a fresh render of the unchanged schema + "
            "self-described tenant — hand-edited or generated by a different invocation",
        )
    return DriftResult("in_sync", IN_SYNC, "owned tenant-aware file matches schema + self-described tenant")


def _check_settings_drift(schema_text, ondisk_text, source_file, kind) -> DriftResult:
    """Drift for ``app/settings.py``: stale if the schema changed; else byte re-render using the
    **self-embedded mode** from the file's own header — no ``app.yaml`` read (FR-CFG-7a)."""
    current_sha = schema_sha256(schema_text)
    embedded = embedded_schema_sha(ondisk_text)
    if embedded is None:
        return DriftResult(
            "tampered", DRIFT, "no schema-sha256 header — settings.py was not generated or stripped"
        )
    if embedded != current_sha:
        return DriftResult(
            "stale",
            DRIFT,
            f"schema changed (header {embedded[:12]}… != current {current_sha[:12]}…) — regenerate",
        )
    mode = embedded_mode(ondisk_text)
    if mode is None:
        return DriftResult(
            "tampered", DRIFT, "missing startd8-mode header — cannot re-derive the baked mode"
        )
    from .settings_renderer import render_settings

    try:
        rendered = render_settings(schema_text, source_file, mode=mode)
    except ValueError as exc:  # an unknown/tampered mode value in the header
        return DriftResult("tampered", DRIFT, f"invalid startd8-mode header ({mode!r}): {exc}")
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned settings.py differs from a fresh render of the unchanged schema + self-described "
            "mode — hand-edited (e.g. the mode line was altered) or generated by a different invocation",
        )
    return DriftResult("in_sync", IN_SYNC, "owned settings.py matches schema + self-described mode")


def is_owned_generated_file(ondisk_text: str) -> bool:
    """True if *ondisk_text* is a file this generator produced (carries the GENERATED header).

    Necessary but **not** sufficient to skip in the pipeline — a stale/hand-edited file also
    carries the header. Pair with :func:`owned_file_in_sync` before treating it as provided.
    """
    text = ondisk_text or ""
    return _GENERATED_MARKER in text and embedded_schema_sha(text) is not None


def owned_file_in_sync(
    schema_text: str,
    ondisk_text: str,
    *,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    human_inputs_text: Optional[str] = None,
    completeness_text: Optional[str] = None,
    display_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    api_text: Optional[str] = None,
    contexts_text: Optional[str] = None,
    project_root: Optional[str] = None,
    form_prose_text: Optional[str] = None,
) -> bool:
    """True iff *ondisk_text* is an owned generated file that is **currently in-sync**.

    The safe predicate for the pipeline skip-hook: header presence alone is rejected; the file
    must re-render byte-identically from the current source(s). The embedded source-label is
    recovered so the re-render's header line matches (avoiding a false "tampered"). Any doubt →
    ``False`` (the caller falls through to the LLM — a safe failure).

    **Manifest-derived kinds (FR-ED-16):** an owned file's drift may depend on more than the schema —
    ``forms:``/``flows:``/``editors:`` on ``views.yaml`` (*views_text*), content pages on ``pages.yaml``
    (*pages_text*), the AI layer on ``ai_passes.yaml`` + ``human_inputs.yaml`` (*manifest_text* /
    *human_inputs_text*), weighted completeness on ``completeness.yaml`` (*completeness_text*), and the
    display structure on ``display.yaml`` (*display_text*). These were previously **not** threaded here,
    so EVERY manifest-derived kind (forms/pages/AI/flows) routed to its check with the manifest unset →
    ``ERROR`` → ``False`` → silently fell through to the LLM despite being a clean ``$0`` file. Callers
    that can resolve these manifests (e.g. the deterministic-file provider) MUST pass them so the file is
    recognized as ``$0``-owned. Each is optional; a schema-only kind ignores all of them.
    """
    if not is_owned_generated_file(ondisk_text):
        return False
    source_file = embedded_source_file(ondisk_text) or "prisma/schema.prisma"
    return (
        check_drift(
            schema_text,
            ondisk_text,
            source_file=source_file,
            manifest_text=manifest_text,
            human_inputs_text=human_inputs_text,
            pages_text=pages_text,
            completeness_text=completeness_text,
            forms_text=views_text,  # check_drift names the views.yaml input `forms_text`
            display_text=display_text,
            imports_text=imports_text,
            api_text=api_text,
            contexts_text=contexts_text,
            project_root=project_root,
            form_prose_text=form_prose_text,
        ).status
        == "in_sync"
    )


def _ai_renderers():
    """Map AI artifact-kind → ``(schema, manifest, human, source_file, entity) -> text`` renderer."""
    from .ai_layer import (
        render_ai_pass,
        render_ai_pass_tests,
        render_keyless_boot_tests,
        render_cost_logging_tests,
        render_ai_routes,
        render_ai_ui_routes,
        render_ai_service,
        render_edge_schemas,
        render_edge_tests,
        render_server,
    )

    # Each renderer takes (schema, manifest, human, source_file, entity, ai_agent_spec).
    # Only ai-service consumes ai_agent_spec — it bakes DEFAULT_AGENT_SPEC, so the
    # re-render must use the same spec the on-disk file declares (else a custom
    # provider false-reads as drift).
    return {
        "ai-service": lambda s, m, h, sf, e, spec: render_ai_service(s, m, h, sf, ai_agent_spec=spec),
        "ai-edge-schemas": lambda s, m, h, sf, e, spec: render_edge_schemas(s, m, h, sf),
        "ai-pass": lambda s, m, h, sf, e, spec: render_ai_pass(s, m, h, sf, e),
        "ai-router": lambda s, m, h, sf, e, spec: render_ai_routes(s, m, h, sf),
        "ai-ui-router": lambda s, m, h, sf, e, spec: render_ai_ui_routes(s, m, h, sf),
        "ai-server": lambda s, m, h, sf, e, spec: render_server(s, m, h, sf),
        "ai-tests-edge": lambda s, m, h, sf, e, spec: render_edge_tests(s, m, h, sf),
        "ai-tests-pass": lambda s, m, h, sf, e, spec: render_ai_pass_tests(s, m, h, sf),
        "ai-tests-keyless": lambda s, m, h, sf, e, spec: render_keyless_boot_tests(s, m, h, sf),
        "ai-tests-cost": lambda s, m, h, sf, e, spec: render_cost_logging_tests(s, m, h, sf),
    }


def _check_ai_drift(
    schema_text, manifest_text, human_inputs_text, ondisk_text, source_file, kind
) -> DriftResult:
    """Drift for an AI-layer file: stale if any of schema/ai_passes/human_inputs changed (FR-MA-5)."""
    if manifest_text is None:
        return DriftResult(
            "error", ERROR, "AI-layer drift check requires the ai_passes manifest"
        )
    reason = ai_layer_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        passes_sha=schema_sha256(manifest_text),
        human_sha=schema_sha256(human_inputs_text or ""),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    renderer = _ai_renderers().get(kind)
    if renderer is None:
        return DriftResult("tampered", DRIFT, f"unknown AI artifact kind ({kind!r})")
    rendered = renderer(
        schema_text, manifest_text, human_inputs_text, source_file,
        embedded_entity(ondisk_text), embedded_ai_agent_spec(ondisk_text),
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned AI file differs from a fresh render of the unchanged inputs — "
            "hand-edited, or generated by a different invocation (different flags or "
            "manifests than this check)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned AI file matches schema + manifest + human-inputs")


def pages_stale_reason(
    ondisk_text: str, *, schema_sha: str, pages_sha: str
) -> Optional[str]:
    """For a content-page file, return why it is **stale**, or ``None`` if both inputs match.

    A content-page artifact derives from two inputs (schema + pages.yaml), so it is stale if **either**
    embedded hash differs from the current input hash. A missing embedded hash counts as stale. The
    page prose is deliberately not an input, so editing a ``.md`` never reaches here.
    """
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("pages", embedded_pages_sha(ondisk_text), pages_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def _pages_renderers():
    """Map content-page kind → a ``(schema, pages, source_file, entity) -> text`` renderer."""
    from .htmx_generator import render_base_template
    from .pages_generator import render_page_shell, render_pages_router

    return {
        "pages-base": lambda s, p, sf, e: render_base_template(s, sf, p),
        "pages-router": lambda s, p, sf, e: render_pages_router(s, p, sf),
        "pages-content": lambda s, p, sf, e: render_page_shell(s, p, sf, e),
    }


def _check_pages_drift(
    schema_text, pages_text, ondisk_text, source_file, kind
) -> DriftResult:
    """Drift for a content-page file: stale if schema or pages.yaml changed; else byte re-render."""
    if pages_text is None:
        return DriftResult(
            "error", ERROR, "content-page drift check requires the pages manifest"
        )
    reason = pages_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        pages_sha=schema_sha256(pages_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    renderer = _pages_renderers().get(kind)
    if renderer is None:
        return DriftResult("tampered", DRIFT, f"unknown content-page kind ({kind!r})")
    rendered = renderer(schema_text, pages_text, source_file, embedded_entity(ondisk_text))
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned content-page file differs from a fresh render of the unchanged inputs — "
            "hand-edited, or generated by a different invocation (different flags or "
            "manifests than this check)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned content-page file matches schema + pages")


def forms_stale_reason(
    ondisk_text: str, *, schema_sha: str, forms_sha: str
) -> Optional[str]:
    """For a forms-configured file, return why it is **stale**, or ``None`` if both inputs match.

    A forms-configured artifact derives from two inputs (schema + views.yaml), so it is stale if
    **either** embedded hash differs from the current input hash. A missing embedded hash counts
    as stale. The hash covers the whole ``views.yaml`` (pages precedent), so composite-view edits
    conservatively re-stamp these files.
    """
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("forms", embedded_forms_sha(ondisk_text), forms_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def _forms_renderers(tenant: Optional[str] = None):
    """Map forms-configured kind → a ``(schema, forms, source_file, entity) -> text`` renderer.

    *tenant* (the self-embedded owner FK) threads Tier-B scoping into the forms-configured web.py
    re-render (``fastapi-web-forms`` queries the DB and must be row-scoped, FR-TEN-2); every other
    kind is a template/aggregator and is unscoped (server-side enforcement lives in web.py)."""
    from .htmx_generator import render_created_template, render_web
    from .flow_generator import (
        render_flow_aggregator,
        render_named_flow_router,
        render_named_flow_shell,
    )
    from .editor_generator import (
        render_editor_aggregator,
        render_named_editor_form,
        render_named_editor_router,
    )

    return {
        "fastapi-web-forms": lambda s, f, sf, e: render_web(s, sf, f, tenant_owner_field=tenant),
        "htmx-created": lambda s, f, sf, e: render_created_template(s, sf, e, f),
        # flows (FR-ED-15): `e` is the flow NAME from the startd8-entity slot; aggregator ignores it.
        "fastapi-flow": lambda s, f, sf, e: render_named_flow_router(s, f, e),
        "flow-shell": lambda s, f, sf, e: render_named_flow_shell(s, f, e),
        "flow-aggregator": lambda s, f, sf, e: render_flow_aggregator(s, f),
        # editors (FR-ED-10): `e` is the editor NAME; aggregator ignores it.
        "fastapi-editor": lambda s, f, sf, e: render_named_editor_router(s, f, e),
        "editor-form": lambda s, f, sf, e: render_named_editor_form(s, f, e),
        "editor-aggregator": lambda s, f, sf, e: render_editor_aggregator(s, f),
    }


def _check_forms_drift(
    schema_text, forms_text, ondisk_text, source_file, kind
) -> DriftResult:
    """Drift for a forms-configured file: stale if schema or views.yaml changed; else byte re-render."""
    if forms_text is None:
        return DriftResult(
            "error", ERROR, "forms drift check requires the views manifest (`forms:` section)"
        )
    reason = forms_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        forms_sha=schema_sha256(forms_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    renderer = _forms_renderers(embedded_tenant_field(ondisk_text)).get(kind)
    if renderer is None:
        return DriftResult("tampered", DRIFT, f"unknown forms-configured kind ({kind!r})")
    rendered = renderer(schema_text, forms_text, source_file, embedded_entity(ondisk_text))
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned forms-configured file was hand-edited (differs from a fresh render of the unchanged inputs)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned forms-configured file matches schema + forms")


def imports_stale_reason(
    ondisk_text: str, *, schema_sha: str, imports_sha: str
) -> Optional[str]:
    """For ``app/importer.py``, return why it is **stale**, or ``None`` if both inputs match (FR-IMP-1)."""
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("imports", embedded_imports_sha(ondisk_text), imports_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def context_client_stale_reason(
    ondisk_text: str,
    *,
    schema_sha: str,
    contexts_sha: str,
    contract_sha: str,
) -> Optional[str]:
    """For a context consumer client, return why it is stale, or ``None`` if inputs match."""
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("contexts", embedded_contexts_sha(ondisk_text), contexts_sha),
        ("contract", embedded_contract_sha(ondisk_text), contract_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def context_smoke_stale_reason(
    ondisk_text: str,
    *,
    schema_sha: str,
    contexts_sha: str,
) -> Optional[str]:
    """For cross-context smoke tests, return why stale, or ``None`` if inputs match."""
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("contexts", embedded_contexts_sha(ondisk_text), contexts_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def api_overlay_stale_reason(
    ondisk_text: str,
    *,
    schema_sha: str,
    api_sha: str,
) -> Optional[str]:
    """For an API-overlay contract file, return why it is stale, or ``None`` if both inputs match."""
    checks = (
        ("schema", embedded_schema_sha(ondisk_text), schema_sha),
        ("api", embedded_api_sha(ondisk_text), api_sha),
    )
    for label, embedded, current in checks:
        if embedded is None:
            return f"missing {label}-sha256 header"
        if embedded != current:
            return (
                f"{label} changed (header {embedded[:12]}… != current {current[:12]}…) — regenerate"
            )
    return None


def _check_api_contract_drift(
    schema_text: str,
    api_text: Optional[str],
    ondisk_text: str,
    source_file: str,
    *,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
) -> DriftResult:
    """Drift for ``python-openapi-contract`` when an ``api.yaml`` overlay participates."""
    if api_text is None:
        return DriftResult(
            "error",
            ERROR,
            "API-overlay drift check requires the api.yaml overlay",
        )
    reason = api_overlay_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        api_sha=schema_sha256(api_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    from .openapi_contract_renderer import render_openapi_contract

    rendered = render_openapi_contract(
        schema_text,
        source_file,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned API contract differs from a fresh render of the unchanged inputs",
        )
    return DriftResult("in_sync", IN_SYNC, "owned API contract matches schema + api overlay")


def _check_imports_drift(
    schema_text, imports_text, ondisk_text, source_file, kind
) -> DriftResult:
    """Drift for the import owned-kinds (FR-IMP-1 importer + FR-IMP-6 surface): stale if schema or
    imports.yaml changed; else byte re-render. Dispatches by kind to the right renderer."""
    if imports_text is None:
        return DriftResult(
            "error", ERROR, "import drift check requires the imports manifest (imports.yaml)"
        )
    reason = imports_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        imports_sha=schema_sha256(imports_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    if kind == "python-import-surface":
        from .import_surface import render_import_surface

        rendered = render_import_surface(schema_text, imports_text, source_file)
    else:
        from .import_codegen import render_import

        rendered = render_import(schema_text, imports_text, source_file)
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned import file was hand-edited (differs from a fresh render of the unchanged inputs)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned import file matches schema + imports")


def _check_context_client_drift(
    schema_text: str,
    contexts_text: Optional[str],
    ondisk_text: str,
    source_file: str,
    *,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    api_text: Optional[str] = None,
    project_root: Optional[str] = None,
) -> DriftResult:
    """Drift for ``python-context-client`` — schema + contexts manifest + pinned contract."""
    if contexts_text is None:
        return DriftResult(
            "error", ERROR, "context-client drift check requires contexts.yaml"
        )
    from .context_client_renderer import render_context_client, _resolve_producer_spec
    from .context_manifest import contract_sha256, filter_spec_for_context, parse_contexts

    producer_id = embedded_entity(ondisk_text)
    if not producer_id:
        return DriftResult("tampered", DRIFT, "missing startd8-entity producer id")
    ctx_by_id = {c.id: c for c in parse_contexts(contexts_text)}
    ctx = ctx_by_id.get(producer_id)
    if ctx is None:
        return DriftResult(
            "tampered", DRIFT, f"unknown producer id {producer_id!r} in contexts manifest"
        )
    raw_spec = _resolve_producer_spec(
        schema_text,
        ctx,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
        project_root=project_root,
    )
    filtered = filter_spec_for_context(raw_spec, schema_text, ctx)
    contract_sha = contract_sha256(filtered)
    reason = context_client_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        contexts_sha=schema_sha256(contexts_text),
        contract_sha=contract_sha,
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    rendered = render_context_client(
        schema_text,
        contexts_text,
        ctx,
        source_file,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
        project_root=project_root,
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned context client differs from a fresh render of the unchanged inputs",
        )
    return DriftResult("in_sync", IN_SYNC, "owned context client matches schema + contexts")


def _check_context_smoke_drift(
    schema_text: str,
    contexts_text: Optional[str],
    ondisk_text: str,
    source_file: str,
) -> DriftResult:
    """Drift for ``python-tests-cross-context`` — schema + contexts manifest."""
    if contexts_text is None:
        return DriftResult(
            "error", ERROR, "cross-context smoke drift check requires contexts.yaml"
        )
    from .test_emitter import render_cross_context_smoke_tests

    reason = context_smoke_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        contexts_sha=schema_sha256(contexts_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    rendered = render_cross_context_smoke_tests(
        schema_text, contexts_text, source_file
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned cross-context smoke tests differ from a fresh render",
        )
    return DriftResult(
        "in_sync", IN_SYNC, "owned cross-context smoke tests match schema + contexts"
    )


def _check_context_integration_drift(
    schema_text: str,
    contexts_text: Optional[str],
    ondisk_text: str,
    source_file: str,
    *,
    project_root: Optional[str] = None,
) -> DriftResult:
    """Drift for ``python-context-integration`` — schema + contexts manifest."""
    if contexts_text is None:
        return DriftResult(
            "error", ERROR, "context integration drift check requires contexts.yaml"
        )
    from .context_integration_renderer import render_context_clients_module

    reason = context_smoke_stale_reason(
        ondisk_text,
        schema_sha=schema_sha256(schema_text),
        contexts_sha=schema_sha256(contexts_text),
    )
    if reason is not None:
        status = "tampered" if "missing" in reason else "stale"
        return DriftResult(status, DRIFT, reason)
    rendered = render_context_clients_module(
        schema_text,
        contexts_text,
        source_file,
        project_root=project_root,
    )
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned context integration registry differs from a fresh render",
        )
    return DriftResult(
        "in_sync", IN_SYNC, "owned context integration registry matches schema + contexts"
    )


def check_drift(
    schema_text: str,
    ondisk_text: Optional[str],
    *,
    source_file: str = "prisma/schema.prisma",
    manifest_text: Optional[str] = None,
    human_inputs_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    completeness_text: Optional[str] = None,
    forms_text: Optional[str] = None,
    display_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    api_text: Optional[str] = None,
    contexts_text: Optional[str] = None,
    project_root: Optional[str] = None,
    form_prose_text: Optional[str] = None,
) -> DriftResult:
    """Compare an on-disk owned file against its source contract(s). No writes.

    ``ondisk_text is None`` means the file is absent (drift — it should exist). Otherwise: a
    missing/old embedded hash means tampered/stale; matching hash with differing bytes means
    tampered (the bytes differ from a fresh render — hand-edit or a different generation
    invocation, the check cannot tell which); matching hash and bytes means in-sync. AI-layer
    kinds (``_AI_KINDS``) derive from three
    inputs and route to the three-hash check (needs *manifest_text*/*human_inputs_text*); content-page
    kinds (``_PAGES_KINDS``) derive from two inputs and route to the two-hash check (needs *pages_text*);
    forms-configured kinds (``_FORMS_KINDS``) likewise (needs *forms_text* — the full ``views.yaml``).
    """
    if ondisk_text is None:
        return DriftResult("missing", DRIFT, "owned file does not exist on disk")

    kind = embedded_artifact_kind(ondisk_text)
    if kind in _AI_KINDS:
        return _check_ai_drift(
            schema_text, manifest_text, human_inputs_text, ondisk_text, source_file, kind
        )
    if kind in _PAGES_KINDS:
        return _check_pages_drift(schema_text, pages_text, ondisk_text, source_file, kind)
    if kind in _FORMS_KINDS:
        return _check_forms_drift(schema_text, forms_text, ondisk_text, source_file, kind)
    if kind in _IMPORTS_KINDS:
        return _check_imports_drift(schema_text, imports_text, ondisk_text, source_file, kind)
    if kind in _CONTEXT_CLIENT_KINDS:
        return _check_context_client_drift(
            schema_text,
            contexts_text,
            ondisk_text,
            source_file,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
            api_text=api_text,
            project_root=project_root,
        )
    if kind in _CONTEXT_SMOKE_KINDS:
        return _check_context_smoke_drift(
            schema_text, contexts_text, ondisk_text, source_file
        )
    if kind in _CONTEXT_INTEGRATION_KINDS:
        return _check_context_integration_drift(
            schema_text,
            contexts_text,
            ondisk_text,
            source_file,
            project_root=project_root,
        )
    if kind == "python-openapi-contract" and (
        api_text is not None or embedded_api_sha(ondisk_text) is not None
    ):
        return _check_api_contract_drift(
            schema_text,
            api_text,
            ondisk_text,
            source_file,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=forms_text,
            imports_text=imports_text,
        )
    if kind in _SETTINGS_KINDS:
        # The skip-hook path: re-derive the baked mode from the file's own header (FR-CFG-7a) — this
        # is the ONLY mode-varying file, and it needs no app.yaml to verify.
        return _check_settings_drift(schema_text, ondisk_text, source_file, kind)
    if kind in _TENANT_AWARE_KINDS:
        # Tier B: re-derive the owner FK from the file's own header (FR-TEN-2); schema-only.
        return _check_tenant_aware_drift(schema_text, ondisk_text, source_file, kind)

    current_sha = schema_sha256(schema_text)
    embedded = embedded_schema_sha(ondisk_text)
    if embedded is None:
        return DriftResult(
            "tampered",
            DRIFT,
            "no schema-sha256 header — file was not generated or the header was stripped",
        )
    if embedded != current_sha:
        return DriftResult(
            "stale",
            DRIFT,
            f"schema changed (header {embedded[:12]}… != current {current_sha[:12]}…) "
            f"— regenerate",
        )

    kind = embedded_artifact_kind(ondisk_text)
    # completeness.py is schema + optional completeness.yaml → regen with the same manifest
    # the generate path used, or drift would false-flag a weighted file.
    renderer = _renderers(
        completeness_text=completeness_text,
        forms_text=forms_text,
        display_text=display_text,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        imports_text=imports_text,
        contexts_text=contexts_text,
        project_root=project_root,
        form_prose_text=form_prose_text,
    ).get(kind or "")
    if renderer is None:
        return DriftResult(
            "tampered",
            DRIFT,
            f"unknown or missing startd8-artifact kind ({kind!r}) — cannot verify",
        )
    rendered = renderer(schema_text, source_file, embedded_entity(ondisk_text))
    if rendered != ondisk_text:
        return DriftResult(
            "tampered",
            DRIFT,
            "owned file differs from a fresh render of the unchanged schema — "
            "hand-edited, or generated by a different invocation (different flags or "
            "manifests than this check)",
        )
    return DriftResult("in_sync", IN_SYNC, "owned file matches the schema")
