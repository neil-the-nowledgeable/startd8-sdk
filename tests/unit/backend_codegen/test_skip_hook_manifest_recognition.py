"""FR-ED-16 — the prime-contractor `$0` skip-hook must recognize manifest-derived owned files.

Regression for a verified pre-existing bug: ``owned_file_in_sync`` passed ONLY the schema to
``check_drift``, so every manifest-derived owned kind (``forms:``/``pages:``/AI-layer/``flows:``)
routed to its check with the manifest unset → ``ERROR`` → ``False`` → silently fell through to the
LLM despite being a clean ``$0`` file. The fix threads every manifest through; these tests pin the
recognition (and the safe-failure when a manifest is *not* supplied).
"""

from __future__ import annotations

from startd8.backend_codegen.drift import owned_file_in_sync
from startd8.backend_codegen.htmx_generator import render_web
from startd8.backend_codegen.pages_generator import render_pages
from startd8.backend_codegen.pydantic_renderer import render_pydantic_models

_SCHEMA = "model Task {\n  id String @id\n  title String\n  status String\n}\n"
_SRC = "prisma/schema.prisma"


def test_forms_configured_file_recognized_when_views_threaded():
    views = "forms:\n  Task:\n    on_create: detail\n"
    web = render_web(_SCHEMA, _SRC, views)
    # The bug: False without the manifest. The fix: True when views.yaml is threaded.
    assert owned_file_in_sync(_SCHEMA, web, views_text=views) is True


def test_forms_file_without_manifest_stays_false_safe_failure():
    """No false-positive skip: a forms file whose manifest the caller cannot resolve is NOT skipped."""
    views = "forms:\n  Task:\n    on_create: detail\n"
    web = render_web(_SCHEMA, _SRC, views)
    assert owned_file_in_sync(_SCHEMA, web) is False


def test_pages_artifacts_recognized_when_pages_threaded():
    pages = 'pages:\n  - slug: /home\n    title: Home\n    content: "Hi"\n'
    arts = [(rel, txt) for rel, txt in render_pages(_SCHEMA, pages, _SRC) if "startd8-artifact" in txt]
    assert arts, "expected at least one header-bearing pages artifact"
    for rel, txt in arts:
        assert owned_file_in_sync(_SCHEMA, txt, pages_text=pages) is True, rel


def test_schema_only_spine_still_recognized_without_any_manifest():
    """Regression guard: threading the new params must not break the schema-only kinds."""
    models = render_pydantic_models(_SCHEMA, source_file=_SRC).text
    assert owned_file_in_sync(_SCHEMA, models) is True


def test_threaded_manifests_are_optional_and_independent():
    """Passing an unrelated manifest must not flip a schema-only file (params are kind-scoped)."""
    models = render_pydantic_models(_SCHEMA, source_file=_SRC).text
    assert owned_file_in_sync(
        _SCHEMA, models, views_text="forms:\n  Task:\n    on_create: detail\n"
    ) is True
