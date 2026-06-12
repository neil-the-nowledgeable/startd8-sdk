"""FR-DRC-5 — cross-provider `$0` skip-hook recognition lock.

The shipped `test_skip_hook_manifest_recognition.py` exercises `owned_file_in_sync` (the backend
helper) directly. That left a gap: it could not catch a *provider* that fails to RESOLVE + THREAD a
manifest its owned files derive from — which is exactly how the **view** provider shipped (it threaded
`view_prose.yaml` but not `display.yaml`, FR-DRC-4). This module pins recognition at the **provider**
boundary (`Provider.is_in_sync` + a real `ProviderContext`), so a display-/prose-/forms-configured owned
file is recognized as `$0` — and fails loudly if a provider drops a manifest it must thread.
"""

from __future__ import annotations

from pathlib import Path

from startd8.contractors.deterministic_providers import ProviderContext

# --- fixtures: a display-configured composite view (exercises FR-DM-6 label bindings) ---------------
_SCHEMA = """
model Capability {
  id      String @id @default(cuid())
  ownerId String @default("local")
  name    String
}
model CapabilityOutcome {
  id           String @id @default(cuid())
  ownerId      String @default("local")
  capabilityId String
  outcomeId    String
}
""".strip()

_VIEWS = """
views:
  - name: value_map
    kind: detail-compose
    scope: model
    root: Capability
    relations:
      - { name: outcomes, from: CapabilityOutcome, fk: capabilityId }
""".strip()

# display.yaml changes the rendered view (root_label_field + relation label_field ⇒ `{{ x.label }}`
# instead of `{{ x.id }}`), so a display-configured file re-rendered WITHOUT display diverges → the
# provider must thread display.yaml to recognize it.
_DISPLAY = """
views:
  value_map:
    root_label_field: name
    relations:
      - { name: outcomes, via_fk: capabilityId, label_field: name }
""".strip()


def _write_project(tmp_path: Path, *, schema, views, display=None, view_prose=None) -> Path:
    prisma = tmp_path / "prisma"
    prisma.mkdir(parents=True, exist_ok=True)
    (prisma / "schema.prisma").write_text(schema, encoding="utf-8")
    (prisma / "views.yaml").write_text(views, encoding="utf-8")
    if display is not None:
        (prisma / "display.yaml").write_text(display, encoding="utf-8")
    if view_prose is not None:
        (prisma / "view_prose.yaml").write_text(view_prose, encoding="utf-8")
    return tmp_path


def _ctx(root: Path) -> ProviderContext:
    return ProviderContext(project_root=root, source_anchors=())


# --------------------------------------------------------------------------- #
# View provider — FR-DRC-4: display.yaml must be threaded
# --------------------------------------------------------------------------- #

def test_view_provider_recognizes_display_configured_files(tmp_path):
    """The lock: with display.yaml present, every owned display-configured view file is `$0`-in-sync.
    Fails if the provider stops threading display.yaml (the FR-DRC-4 regression)."""
    from startd8.view_codegen import render_views
    from startd8.view_codegen.provider import CompositeViewProvider

    root = _write_project(tmp_path, schema=_SCHEMA, views=_VIEWS, display=_DISPLAY)
    provider = CompositeViewProvider()
    owned = 0
    for rel, content in render_views(_SCHEMA, _VIEWS, _DISPLAY):
        if not provider.owns(Path(rel), content):
            continue
        owned += 1
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        assert provider.is_in_sync(target, content, _ctx(root)) is True, rel
    assert owned, "expected at least one owned display-configured view file"


def test_view_provider_safe_failure_when_display_absent(tmp_path):
    """A display-configured file with no display.yaml resolvable → NOT recognized (re-render diverges)
    → falls through to the LLM. Proves display threading is load-bearing (not a no-op)."""
    from startd8.view_codegen import render_views
    from startd8.view_codegen.provider import CompositeViewProvider

    root = _write_project(tmp_path, schema=_SCHEMA, views=_VIEWS)  # NO display.yaml
    provider = CompositeViewProvider()
    # The model-compose template is the one display rewrites (`{{ x.label }}` vs `{{ x.id }}`).
    tmpl_rel = "app/templates/views/value_map.html"
    content = dict(render_views(_SCHEMA, _VIEWS, _DISPLAY))[tmpl_rel]
    assert provider.owns(Path(tmpl_rel), content)
    target = root / tmpl_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    assert provider.is_in_sync(target, content, _ctx(root)) is False


def test_view_provider_recognizes_view_prose_configured_files(tmp_path):
    """Regression guard for the existing view_prose threading (alongside the new display threading)."""
    from startd8.view_codegen import render_views
    from startd8.view_codegen.provider import CompositeViewProvider

    prose = 'value_map:\n  title: "Your value map"\n'
    root = _write_project(tmp_path, schema=_SCHEMA, views=_VIEWS, view_prose=prose)
    provider = CompositeViewProvider()
    tmpl_rel = "app/templates/views/value_map.html"
    content = dict(render_views(_SCHEMA, _VIEWS, None, prose))[tmpl_rel]
    target = root / tmpl_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    assert provider.is_in_sync(target, content, _ctx(root)) is True


# --------------------------------------------------------------------------- #
# Backend provider — FR-ED-16: forms-configured files recognized at the provider boundary
# --------------------------------------------------------------------------- #

def test_backend_provider_recognizes_forms_configured_file(tmp_path):
    """The backend skip-hook (provider-level) recognizes a `views.yaml forms:`-derived file as `$0`."""
    from startd8.backend_codegen.htmx_generator import render_web
    from startd8.backend_codegen.provider import PydanticSQLModelProvider

    schema = "model Task {\n  id String @id\n  title String\n  status String\n}\n"
    views = "forms:\n  Task:\n    on_create: detail\n"
    root = _write_project(tmp_path, schema=schema, views=views)
    web = render_web(schema, "prisma/schema.prisma", views)
    provider = PydanticSQLModelProvider()
    assert provider.owns(Path("app/web.py"), web)
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "web.py").write_text(web, encoding="utf-8")
    assert provider.is_in_sync(root / "app" / "web.py", web, _ctx(root)) is True
