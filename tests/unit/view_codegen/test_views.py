"""Composite-view generator (class-3 determinism) — REQ-VIEW.

Proves the three v1 archetypes emit byte-stable, strict-validated, drift-checked owned views, and —
the D1 point — that the emitted view tests RUN GREEN against generated tables: dashboard aggregates
count, board groups by the owned order, and the workspace resolves a polymorphic match AND flags a
dangling one (RUN-029/032 invariants).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.view_codegen import (
    compute_binding_names,
    is_owned_view_file,
    parse_views,
    render_views,
    views_in_sync,
)
from startd8.view_codegen import manifest as _manifest
from startd8.view_codegen import renderers as _renderers

pytestmark = pytest.mark.unit

# Entities the views span. Content fields optional so the generic test-seeds construct rows trivially.
SCHEMA = """
model JobDescription {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  createdAt DateTime @default(now())
  rawText   String?
  requiredCapabilities String?
  targetOutcomes       String?
}

model TailoredMatch {
  id           String  @id @default(cuid())
  ownerId      String  @default("local")
  source       String  @default("user")
  confirmed    Boolean @default(true)
  jobDescriptionId String?
  capabilityId String?
  subjectType  String?
  subjectId    String?
}

model TailoredAsset {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  jobDescriptionId String?
  kind      String?
}

model Opportunity {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  stage     String?
  stageId   String?
  metrics       String?
  economicBuyer String?
}

model PipelineStage {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  name      String?
  position  Int     @default(0)
}

model Capability {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  name      String?
}

model Contact {
  id            String  @id @default(cuid())
  ownerId       String  @default("local")
  source        String  @default("user")
  confirmed     Boolean @default(true)
  opportunityId String?
}

model Activity {
  id            String  @id @default(cuid())
  ownerId       String  @default("local")
  source        String  @default("user")
  confirmed     Boolean @default(true)
  opportunityId String?
}

model Artifact {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  kind      String?
  dataJson  String?
}
""".strip()

VIEWS = """
views:
  - name: jobs_dashboard
    kind: dashboard
    route: /jobs
    root: JobDescription
    aggregates:
      - { name: matches, of: TailoredMatch, fk: jobDescriptionId }
      - { name: assets, of: TailoredAsset, fk: jobDescriptionId }
    signal: "matches >= 1"
  - name: pipeline_board
    kind: board
    route: /pipeline
    root: Opportunity
    group_by: stage
    order: [identified, offer]
  - name: job_workspace
    kind: workspace
    route: /job/{id}
    root: JobDescription
    polymorphic:
      of: TailoredMatch
      fk: jobDescriptionId
      type_field: subjectType
      id_field: subjectId
      type_map: { capability: Capability }
    gap:
      needs_from: [requiredCapabilities, targetOutcomes]
  - name: opportunity_detail
    kind: detail-compose
    route: /opportunity/{id}
    root: Opportunity
    relations:
      - { name: contacts, from: Contact, fk: opportunityId }
      - { name: activities, from: Activity, fk: opportunityId }
    panels:
      - { name: qualification, fields: [metrics, economicBuyer], show_when: any_set }
  - name: job_export
    kind: export-package
    route: /job/{id}/export
    root: JobDescription
    relations:
      - { name: matches, from: TailoredMatch, fk: jobDescriptionId }
      - { name: assets, from: TailoredAsset, fk: jobDescriptionId }
  - name: value_map
    kind: detail-compose
    scope: model
    root: Capability
    relations:
      - { name: matches, from: TailoredMatch, fk: capabilityId }
  - name: completeness_panel
    kind: computed-panel
    compute: completeness
    route: /completeness
  - name: artifact_reader
    kind: rendered-content
    root: Artifact
    content_field: dataJson
    prose_key: body
    route: /artifacts
  - name: stage_board
    kind: board
    route: /stages
    root: Opportunity
    group_by: stageId
    columns_from: PipelineStage
    order_by: position
  - name: model_import
    kind: import-flow
    route: /import
  - name: model_export
    kind: export-package
    scope: model
""".strip()


def test_strict_validation_rejects_unknown_entity():
    bad = VIEWS.replace("root: Opportunity", "root: Nonexistent")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=frozenset({
            "JobDescription", "TailoredMatch", "TailoredAsset", "Capability",
            "Opportunity", "Contact", "Activity", "Artifact", "PipelineStage",
        }))


_KNOWN = frozenset({
    "JobDescription", "TailoredMatch", "TailoredAsset", "Capability",
    "Opportunity", "Contact", "Activity", "Artifact", "PipelineStage",
})
# Entity -> scalar field names (for AR-6 content_field + FR-EB board field loud-fail tests).
_KNOWN_FIELDS = {
    "Artifact": frozenset({"id", "ownerId", "source", "confirmed", "kind", "dataJson"}),
    "Opportunity": frozenset({
        "id", "ownerId", "source", "confirmed", "stage", "stageId", "metrics", "economicBuyer",
    }),
    "PipelineStage": frozenset({"id", "ownerId", "source", "confirmed", "name", "position"}),
}


def test_strict_validation_rejects_unknown_relation_panel_gap_keys():
    # unknown relation key
    bad = VIEWS.replace("{ name: contacts, from: Contact, fk: opportunityId }",
                        "{ name: contacts, from: Contact, fk: opportunityId, bogus: x }")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=_KNOWN)
    # unknown panel key
    bad = VIEWS.replace("show_when: any_set }", "show_when: any_set, bogus: x }")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=_KNOWN)
    # unknown gap key
    bad = VIEWS.replace("needs_from: [requiredCapabilities, targetOutcomes]",
                        "needs_from: [requiredCapabilities]\n      bogus: x")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=_KNOWN)
    # unknown show_when grammar
    bad = VIEWS.replace("show_when: any_set", "show_when: all_set")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=_KNOWN)
    # relation to unknown entity is gated
    bad = VIEWS.replace("from: Contact", "from: Ghost")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=_KNOWN)


def test_model_scope_strict_validation():
    # unknown scope value is loud (no LLM fallback)
    bad = VIEWS.replace("scope: model", "scope: app")
    with pytest.raises(ValueError, match="unknown scope"):
        parse_views(bad, known_entities=_KNOWN)
    # scope is export-package/detail-compose-only (AR-3 + AR-1)
    bad = VIEWS.replace("kind: board\n    route: /pipeline", "kind: board\n    scope: model\n    route: /pipeline")
    with pytest.raises(ValueError, match="only valid on kinds"):
        parse_views(bad, known_entities=_KNOWN)
    # root is forbidden on a model-scoped export (the whole model has no root row)
    bad = VIEWS.replace("scope: model", "scope: model\n    root: JobDescription")
    with pytest.raises(ValueError, match="not allowed with `scope: model`"):
        parse_views(bad, known_entities=_KNOWN)
    # relations are forbidden too
    bad = VIEWS.replace(
        "scope: model",
        "scope: model\n    relations:\n      - { name: m, from: TailoredMatch, fk: jobDescriptionId }",
    )
    with pytest.raises(ValueError, match="not allowed with `scope: model`"):
        parse_views(bad, known_entities=_KNOWN)


# --------------------------------------------------------------------------- #
# Client-logged friction regressions (docs/design/client-friction-fixes/)
# --------------------------------------------------------------------------- #

def test_f2_static_board_without_order_raises_named_valueerror_not_indexerror():
    """portal-rebuild F2: a static `board` whose group_by is an enum, with no `Order:`, used to crash
    with a bare `IndexError: tuple index out of range`. It must now raise a clear ValueError that
    names the offending view (flag-don't-crash)."""
    bad = VIEWS.replace(
        "    group_by: stage\n    order: [identified, offer]",
        "    group_by: stage",
    )
    with pytest.raises(ValueError, match=r"board 'pipeline_board' requires an `Order:`"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)


def test_h3_non_polymorphic_workspace_raises_named_valueerror_not_assertionerror():
    """household-o11y H3: a `workspace` view on a non-polymorphic root tripped a bare AssertionError
    (`assert p is not None`) with no view name. It must raise a ValueError naming the view."""
    from startd8.view_codegen.renderers import _render_workspace

    y = (
        "views:\n"
        "  - name: member_workspace\n"
        "    kind: workspace\n"
        "    route: /member/{id}\n"
        "    root: Opportunity\n"
    )
    specs = parse_views(y, known_entities=_KNOWN)
    ws = specs[0]
    assert ws.polymorphic is None
    with pytest.raises(ValueError, match=r"workspace 'member_workspace': requires a polymorphic"):
        _render_workspace(ws)
    # #77 DX: the error must redirect the author to the generic archetype.
    with pytest.raises(ValueError, match=r"detail-compose"):
        _render_workspace(ws)


def test_model_scope_route_derivation_and_override():
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN)}
    me = specs["model_export"]
    assert me.scope == "model" and me.route == "/export" and me.root == ""
    # per-row export is untouched
    assert specs["job_export"].scope == "row"
    # explicit Route: override (authoring contract §2.3) is honored
    overridden = VIEWS.replace("scope: model", "scope: model\n    route: /backup")
    specs = {v.name: v for v in parse_views(overridden, known_entities=_KNOWN)}
    assert specs["model_export"].route == "/backup"
    rendered = dict(render_views(SCHEMA, overridden))
    assert '@views_router.get(\'/backup/markdown\')' in rendered["app/views/routes.py"]
    assert '@views_router.get(\'/backup/json\')' in rendered["app/views/routes.py"]


def test_model_compose_grammar_route_derivation_and_loud_failures():
    """AR-1: `scope: model` on detail-compose — whole-model compose (the FR-8 Value Map)."""
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN)}
    vm = specs["value_map"]
    # route derives /<kebab(view name)> with NO {id} (authoring contract §2.3); root required
    assert vm.scope == "model" and vm.route == "/value-map" and vm.root == "Capability"
    # row-scope detail-compose is untouched
    assert specs["opportunity_detail"].scope == "row"
    assert specs["opportunity_detail"].route == "/opportunity/{id}"
    # explicit route override honored
    overridden = VIEWS.replace(
        "scope: model\n    root: Capability", "scope: model\n    route: /map\n    root: Capability"
    )
    specs = {v.name: v for v in parse_views(overridden, known_entities=_KNOWN)}
    assert specs["value_map"].route == "/map"
    # root stays REQUIRED (we iterate all roots of that entity)
    bad = VIEWS.replace("scope: model\n    root: Capability\n", "scope: model\n")
    with pytest.raises(ValueError, match="missing required `root`"):
        parse_views(bad, known_entities=_KNOWN)
    # a model-scoped compose iterates ALL roots — an {id} route is a contradiction, loud
    bad = VIEWS.replace(
        "scope: model\n    root: Capability",
        "scope: model\n    route: /value-map/{id}\n    root: Capability",
    )
    with pytest.raises(ValueError, match="must not take path params"):
        parse_views(bad, known_entities=_KNOWN)


def test_model_compose_module_router_and_template():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/value_map.py"]
    assert is_owned_view_file(mod)  # two-hash header carried
    assert "def value_map_data(session: Session) -> list[dict[str, Any]]:" in mod
    assert '"linked"' in mod  # FR-8: unlinked roots flagged, never dropped
    routes = rendered["app/views/routes.py"]
    # bare route — no {id}, no `id:` param; TemplateResponse stays request-first (dd15e7ca)
    assert "@views_router.get('/value-map', response_class=HTMLResponse)" in routes
    assert "def value_map(request: Request, session: Session = Depends(get_session)):" in routes
    assert "include_router" not in routes  # mounts via the owned user_routers seam only
    tmpl = rendered["app/templates/views/value_map.html"]
    assert "{% if not rows %}" in tmpl  # meaningful empty state on an empty DB
    assert "not yet linked" in tmpl    # the FR-8 unlinked nudge


def test_computed_panel_grammar_and_loud_failures():
    """AR-2: `computed-panel` — a generated compute binding -> score+nudges panel (FR-9)."""
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN)}
    cp = specs["completeness_panel"]
    assert cp.kind == "computed-panel" and cp.compute == "completeness"
    assert cp.route == "/completeness" and cp.root == ""
    # route derives /<kebab(view name)> when omitted
    derived = VIEWS.replace("compute: completeness\n    route: /completeness", "compute: completeness")
    specs = {v.name: v for v in parse_views(derived, known_entities=_KNOWN)}
    assert specs["completeness_panel"].route == "/completeness-panel"
    # missing compute is loud
    bad = VIEWS.replace("compute: completeness\n    route: /completeness", "route: /completeness")
    with pytest.raises(ValueError, match="missing required `compute`"):
        parse_views(bad, known_entities=_KNOWN)
    # unknown compute binding is loud (closed vocabulary, no LLM fallback)
    bad = VIEWS.replace("compute: completeness", "compute: vibes")
    with pytest.raises(ValueError, match="unknown compute binding"):
        parse_views(bad, known_entities=_KNOWN)
    # entity-shaped keys are wrong-kind on a computed-panel
    bad = VIEWS.replace("compute: completeness", "compute: completeness\n    root: Capability")
    with pytest.raises(ValueError, match="not valid on kind"):
        parse_views(bad, known_entities=_KNOWN)
    # compute is computed-panel-only
    bad = VIEWS.replace("kind: board\n    route: /pipeline", "kind: board\n    compute: completeness\n    route: /pipeline")
    with pytest.raises(ValueError, match="only valid on kind 'computed-panel'"):
        parse_views(bad, known_entities=_KNOWN)


def test_computed_panel_reuses_generated_compute_and_routes():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/completeness_panel.py"]
    assert is_owned_view_file(mod)
    # the scoring rule lives in the generated app/completeness.py — imported, never duplicated
    assert "from app.completeness import ENTITIES, compute_completeness" in mod
    assert "score = " not in mod  # no re-implemented scoring math
    routes = rendered["app/views/routes.py"]
    assert "@views_router.get('/completeness', response_class=HTMLResponse)" in routes
    assert "def completeness_panel(request: Request, session: Session = Depends(get_session)):" in routes
    tmpl = rendered["app/templates/views/completeness_panel.html"]
    assert "data.score" in tmpl and "data.nudges" in tmpl  # the score+nudges panel


def test_compute_binding_registry_is_single_source_of_truth():
    """AR-2 extension point: the manifest's parse-validation vocabulary is DERIVED from the renderer
    registry (renderers._COMPUTE_RENDERERS) — one place, no drift between "what parses" and "what
    renders"."""
    # the public accessor, the renderer registry, and the manifest's allow-list are all the same set
    assert compute_binding_names() == frozenset(_renderers._COMPUTE_RENDERERS)
    assert _manifest._compute_bindings() == frozenset(_renderers._COMPUTE_RENDERERS)
    # v1 ships exactly `completeness`
    assert compute_binding_names() == frozenset({"completeness"})


def test_compute_binding_registry_is_open_and_extensible():
    """Registering ONE entry (name + renderer fn) opens BOTH parse-validation and render dispatch —
    the whole extension surface. Uses a throwaway in-test binding, restored afterward."""
    saved = dict(_renderers._COMPUTE_RENDERERS)

    def _render_throwaway(v):  # a minimal valid data module — emits a no-op compute view
        return "\n".join([
            "from __future__ import annotations", "",
            "from typing import Any", "",
            "from sqlmodel import Session", "", "",
            f"def {v.module}_data(session: Session) -> dict[str, Any]:",
            '    return {"score": 0.0, "nudges": []}', "",
            f"__all__ = [{(v.module + '_data')!r}]", "",
        ])

    try:
        _renderers._COMPUTE_RENDERERS["throwaway"] = _render_throwaway
        # 1) the manifest validator now ACCEPTS the new binding (derived, not hardcoded)
        assert "throwaway" in _manifest._compute_bindings()
        yaml_text = (
            "views:\n"
            "  - name: tw_panel\n"
            "    kind: computed-panel\n"
            "    compute: throwaway\n"
            "    route: /tw\n"
        )
        specs = {v.name: v for v in parse_views(yaml_text, known_entities=_KNOWN)}
        assert specs["tw_panel"].compute == "throwaway"
        # 2) the render dispatch picks the SAME registry entry up automatically
        from startd8.view_codegen.renderers import _render_computed_panel
        out = _render_computed_panel(specs["tw_panel"])
        assert "tw_panel_data" in out and 'score": 0.0' in out
    finally:
        _renderers._COMPUTE_RENDERERS.clear()
        _renderers._COMPUTE_RENDERERS.update(saved)
    # restored: vocabulary is closed again to v1
    assert compute_binding_names() == frozenset({"completeness"})


def test_unknown_compute_binding_message_lists_registered_set():
    """An unknown binding fails loud AND names the registered set (the closed-vocabulary contract)."""
    bad = VIEWS.replace("compute: completeness", "compute: vibes")
    with pytest.raises(ValueError, match=r"unknown compute binding 'vibes' \(allowed: \['completeness'\]\)"):
        parse_views(bad, known_entities=_KNOWN)


def test_import_flow_grammar_and_loud_failures():
    """AR-4: `import-flow` — upload -> validate -> confirmed restore (FR-10 round-trip)."""
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN)}
    mi = specs["model_import"]
    assert mi.kind == "import-flow" and mi.route == "/import" and mi.root == ""
    # route defaults to /import (the conventional base, like AR-3's /export)
    derived = VIEWS.replace("kind: import-flow\n    route: /import", "kind: import-flow")
    specs = {v.name: v for v in parse_views(derived, known_entities=_KNOWN)}
    assert specs["model_import"].route == "/import"
    # entity keys are wrong-kind on an import-flow (the export contract drives it)
    bad = VIEWS.replace("kind: import-flow", "kind: import-flow\n    root: Capability")
    with pytest.raises(ValueError, match="not valid on kind"):
        parse_views(bad, known_entities=_KNOWN)
    bad = VIEWS.replace(
        "kind: import-flow",
        "kind: import-flow\n    relations:\n      - { name: m, from: TailoredMatch, fk: capabilityId }",
    )
    with pytest.raises(ValueError, match="not valid on kind"):
        parse_views(bad, known_entities=_KNOWN)


def test_import_flow_module_router_and_template():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/model_import.py"]
    assert is_owned_view_file(mod)
    # driven by the generated export contract — imported, never duplicated
    assert "from app.export import ENTITY_ORDER, FIELDS" in mod
    # datetime coercion map is baked FROM THE CONTRACT, not hardcoded provenance names
    assert "_DATETIME_FIELDS" in mod and "'JobDescription': ('createdAt',)" in mod
    assert "_PK" in mod and "datetime.fromisoformat" in mod
    routes = rendered["app/views/routes.py"]
    assert "@views_router.get('/import', response_class=HTMLResponse)" in routes
    assert "@views_router.post('/import/validate')" in routes
    assert "@views_router.post('/import/restore')" in routes
    # the destructive step is explicit — an unconfirmed restore is refused with 400
    assert "if confirm != 'restore':" in routes
    assert "status_code=400" in routes
    # multipart machinery present only because an import-flow exists
    assert "from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile" in routes
    assert "import json" in routes
    tmpl = rendered["app/templates/views/model_import.html"]
    assert 'enctype="multipart/form-data"' in tmpl
    assert 'action="/import/validate"' in tmpl and 'action="/import/restore"' in tmpl
    assert 'name="confirm"' in tmpl  # the explicit confirmation tick


def test_router_without_import_flow_keeps_minimal_imports():
    no_import = "\n".join(
        line for line in VIEWS.splitlines()
        if "model_import" not in line and "import-flow" not in line and "route: /import" not in line
    )
    rendered = dict(render_views(SCHEMA, no_import))
    routes = rendered["app/views/routes.py"]
    assert "from fastapi import APIRouter, Depends, Request\n" in routes
    assert "import json" not in routes
    assert "UploadFile" not in routes


def test_model_export_reuses_export_layer_and_routes():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/model_export.py"]
    # serialization is the generated app/export.py layer — imported, never duplicated
    assert "from app.export import ENTITY_ORDER, FIELDS, to_json, to_markdown" in mod
    assert "json.dumps" not in mod
    assert is_owned_view_file(mod)  # two-hash header carried
    routes = rendered["app/views/routes.py"]
    assert "@views_router.get('/export/markdown')" in routes
    assert "@views_router.get('/export/json')" in routes
    assert "media_type='text/markdown; charset=utf-8'" in routes
    assert "media_type='application/json'" in routes
    assert "from fastapi.responses import HTMLResponse, Response" in routes
    # the views mount through the owned user_routers seam (D2) — the router never self-mounts
    assert "include_router" not in routes


def test_router_without_model_export_keeps_minimal_imports():
    no_model = "\n".join(VIEWS.splitlines()[:-3])  # drop the model_export block
    rendered = dict(render_views(SCHEMA, no_model))
    routes = rendered["app/views/routes.py"]
    assert "from fastapi.responses import HTMLResponse\n" in routes
    assert "return Response(" not in routes


def test_rendered_content_grammar_and_loud_failures():
    """AR-6 (FR-16): `rendered-content` — a prose-from-a-JSON-field presenter bound to one entity."""
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)}
    ar = specs["artifact_reader"]
    assert ar.kind == "rendered-content" and ar.root == "Artifact"
    assert ar.content_field == "dataJson" and ar.prose_key == "body" and ar.route == "/artifacts"
    # prose_key defaults to "body" when omitted
    derived = VIEWS.replace("    content_field: dataJson\n    prose_key: body\n", "    content_field: dataJson\n")
    specs2 = {v.name: v for v in parse_views(derived, known_entities=_KNOWN)}
    assert specs2["artifact_reader"].prose_key == "body"
    # route derives /<kebab(view name)> when omitted
    derived = VIEWS.replace("    content_field: dataJson\n    prose_key: body\n    route: /artifacts",
                            "    content_field: dataJson")
    specs3 = {v.name: v for v in parse_views(derived, known_entities=_KNOWN)}
    assert specs3["artifact_reader"].route == "/artifact-reader"
    # missing content_field is loud
    bad = VIEWS.replace("    content_field: dataJson\n", "")
    with pytest.raises(ValueError, match="missing required `content_field`"):
        parse_views(bad, known_entities=_KNOWN)
    # content_field/prose_key are rendered-content-only (wrong-kind elsewhere)
    bad = VIEWS.replace("kind: board\n    route: /pipeline",
                        "kind: board\n    content_field: stage\n    route: /pipeline")
    with pytest.raises(ValueError, match="only valid on kind 'rendered-content'"):
        parse_views(bad, known_entities=_KNOWN)
    # aggregate/relation/panel keys are wrong-kind on a rendered-content view
    bad = VIEWS.replace("    content_field: dataJson\n    prose_key: body\n    route: /artifacts",
                        "    content_field: dataJson\n    route: /artifacts\n    group_by: kind")
    with pytest.raises(ValueError, match="not valid on kind"):
        parse_views(bad, known_entities=_KNOWN)
    # a path-param route is a contradiction (the view lists/reads by query id)
    bad = VIEWS.replace("    route: /artifacts", "    route: /artifacts/{id}")
    with pytest.raises(ValueError, match="must not take path params"):
        parse_views(bad, known_entities=_KNOWN)


def test_rendered_content_unknown_field_is_loud():
    """content_field must be a REAL field on root — loud-fail when known_fields is supplied (AR-6)."""
    bad = VIEWS.replace("content_field: dataJson", "content_field: noSuchColumn")
    with pytest.raises(ValueError, match="unknown field 'noSuchColumn' on 'Artifact'"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # render_views derives known_fields from the schema, so the same drift fails loud end-to-end
    with pytest.raises(ValueError, match="unknown field"):
        render_views(SCHEMA, bad)


def test_rendered_content_module_router_and_template():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/artifact_reader.py"]
    assert is_owned_view_file(mod)
    # the prose extraction is the SHARED app/views/_prose.py renderer — imported, never duplicated
    assert "from app.views._prose import prose_body, prose_html, prose_preview" in mod
    assert "def artifact_reader_list(session: Session)" in mod
    assert "def artifact_reader_data(session: Session, root_id: str)" in mod
    assert "'dataJson'" in mod and "'body'" in mod  # binds content_field + prose_key
    # the single prose-from-JSON helper module
    prose = rendered["app/views/_prose.py"]
    assert is_owned_view_file(prose)
    assert "def prose_body(" in prose and "def prose_html(" in prose and "def prose_preview(" in prose
    routes = rendered["app/views/routes.py"]
    assert "@views_router.get('/artifacts', response_class=HTMLResponse)" in routes
    assert "from app.views.artifact_reader import artifact_reader_data, artifact_reader_list" in routes
    assert "include_router" not in routes  # mounts via the owned user_routers seam only
    tmpl = rendered["app/templates/views/artifact_reader.html"]
    # detail: prose html + a copy control (plain-text body); list: kind + preview; no raw JSON
    assert "data.html | safe" in tmpl and "navigator.clipboard.writeText" in tmpl
    assert "data-copy=\"{{ data.body }}\"" in tmpl
    assert "r.kind" in tmpl and "r.preview" in tmpl
    assert "dataJson" not in tmpl  # the template never surfaces the raw JSON column name


def test_rendered_content_prose_helper_extracts_body_only():
    """The emitted prose helper turns a {body, traces} JSON column into prose — never the blob/ids."""
    import ast

    prose = dict(render_views(SCHEMA, VIEWS))["app/views/_prose.py"]
    ns: dict = {}
    exec(compile(ast.parse(prose), "<_prose>", "exec"), ns)  # noqa: S102 (generated, trusted)
    payload = '{"body": "Win first. Proof next.", "traces": ["cap-1", "out-2"]}'
    assert ns["prose_body"](payload) == "Win first. Proof next."
    html = ns["prose_html"](payload)
    assert "Win first" in html and "<p>" in html
    assert "cap-1" not in html and "traces" not in html and "{" not in html  # no JSON, no ids
    assert ns["prose_preview"](payload).startswith("Win first")
    # tolerant: a dict column, a plain string, and empty/None all behave (never raise)
    assert ns["prose_body"]({"body": "X"}) == "X"
    assert ns["prose_body"]("not json at all") == "not json at all"
    assert ns["prose_body"](None) == "" and ns["prose_html"]("") == ""


def test_fr10_model_export_renders_artifact_prose_verbatim():
    """FR-10 (capability A): the model-scoped Markdown export pulls Artifact.dataJson.body and
    renders it VERBATIM as prose, reusing the SAME prose renderer — not a per-entity JSON dump."""
    rendered = dict(render_views(SCHEMA, VIEWS))
    export_mod = rendered["app/views/model_export.py"]
    # the export reuses the shared prose renderer, keyed off the rendered-content declaration
    assert "from app.views._prose import prose_body" in export_mod
    assert "from app.tables import Artifact" in export_mod
    assert "prose_body(getattr(_row, 'dataJson', None), 'body')" in export_mod
    assert "VERBATIM" in export_mod
    # F-10b: the prose entity is dropped from the generic dump ENTIRELY (rendered once as
    # named prose), not kept as a redacted/blank row — no duplicate, no `_redact` machinery.
    assert "_prose_entities = {'Artifact'}" in export_mod
    assert "_e not in _prose_entities" in export_mod
    assert "_redact" not in export_mod  # the old redact-the-field-but-keep-the-row path is gone
    # an export with NO rendered-content view keeps the prose machinery out (byte-parity guard)
    _artifact_lines = {
        "  - name: artifact_reader", "    kind: rendered-content", "    root: Artifact",
        "    content_field: dataJson", "    prose_key: body", "    route: /artifacts",
    }
    no_artifact = "\n".join(
        line for line in VIEWS.splitlines() if line not in _artifact_lines
    )
    plain = dict(render_views(SCHEMA, no_artifact))["app/views/model_export.py"]
    assert "prose_body" not in plain and "return to_markdown(payload)" in plain
    assert "app/views/_prose.py" not in dict(render_views(SCHEMA, no_artifact))


def test_entity_backed_board_grammar_and_loud_failures():
    """FR-EB: a board variant grouping by a related entity's runtime rows ordered by `position`."""
    specs = {v.name: v for v in parse_views(VIEWS, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)}
    eb = specs["stage_board"]
    assert eb.kind == "board" and eb.root == "Opportunity"
    assert eb.columns_from == "PipelineStage" and eb.group_by == "stageId" and eb.order_by == "position"
    assert eb.order == ()  # no static order list
    # the static-order board is still parsed as the static variant
    assert specs["pipeline_board"].columns_from == "" and specs["pipeline_board"].order == ("identified", "offer")
    # mixing static `order:` with `columns_from:` is loud
    bad = VIEWS.replace(
        "    group_by: stageId\n    columns_from: PipelineStage\n    order_by: position",
        "    group_by: stageId\n    columns_from: PipelineStage\n    order_by: position\n    order: [a, b]",
    )
    with pytest.raises(ValueError, match="cannot mix `order:`"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # columns_from naming a non-entity is loud
    bad = VIEWS.replace("columns_from: PipelineStage", "columns_from: Ghost")
    with pytest.raises(ValueError, match="unknown entity 'Ghost'"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # order_by not a field on the column entity is loud
    bad = VIEWS.replace("order_by: position", "order_by: notAField")
    with pytest.raises(ValueError, match="unknown field 'notAField' on 'PipelineStage'"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # group_by not a root field is loud
    bad = VIEWS.replace("group_by: stageId\n    columns_from", "group_by: bogusRef\n    columns_from")
    with pytest.raises(ValueError, match="unknown field 'bogusRef' on 'Opportunity'"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # missing order_by is loud
    bad = VIEWS.replace("    columns_from: PipelineStage\n    order_by: position",
                        "    columns_from: PipelineStage")
    with pytest.raises(ValueError, match="missing required `order_by`"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)
    # columns_from/order_by are board-only
    bad = VIEWS.replace("compute: completeness\n    route: /completeness",
                        "compute: completeness\n    columns_from: PipelineStage\n    route: /completeness")
    with pytest.raises(ValueError, match="only valid on kind 'board'"):
        parse_views(bad, known_entities=_KNOWN, known_fields=_KNOWN_FIELDS)


def test_entity_backed_board_module_and_static_board_byte_identical():
    rendered = dict(render_views(SCHEMA, VIEWS))
    eb = rendered["app/views/stage_board.py"]
    assert is_owned_view_file(eb)
    # columns are queried from the entity at request time, ordered by order_by — NO static list
    assert "select(PipelineStage).order_by(PipelineStage.position)" in eb
    assert "_ORDER" not in eb  # no baked static order list
    assert "from app.tables import Opportunity, PipelineStage" in eb
    assert "Unassigned" in eb  # the no-row-lost tail
    assert "getattr(root, 'stageId')" in eb  # group by the root's ref
    # the static board (pipeline_board) is unchanged — still the baked-_ORDER variant, byte-identical
    sb = rendered["app/views/pipeline_board.py"]
    assert "_ORDER = [\"identified\", \"offer\"]" in sb
    assert "columns_from" not in sb and "PipelineStage" not in sb and "Unassigned" not in sb
    # entity-backed board uses the SAME router/template path (board), so it passes `rows`
    routes = rendered["app/views/routes.py"]
    assert "@views_router.get('/stages', response_class=HTMLResponse)" in routes
    tmpl = rendered["app/templates/views/stage_board.html"]
    assert "{% for stage, rows in rows %}" in tmpl  # same board template shape


def test_static_board_render_unaffected_by_entity_board_feature():
    """Regression guard: a manifest with ONLY the static board renders the static board exactly as
    before (the entity-backed branch is gated on `columns_from`, never touches the static path)."""
    static_only = (
        "views:\n"
        "  - name: pipeline_board\n"
        "    kind: board\n"
        "    route: /pipeline\n"
        "    root: Opportunity\n"
        "    group_by: stage\n"
        "    order: [identified, offer]\n"
    )
    mod = dict(render_views(SCHEMA, static_only))["app/views/pipeline_board.py"]
    # the static board body is the baked-_ORDER grouping — no entity-backed machinery leaked in
    assert "_ORDER = [\"identified\", \"offer\"]" in mod
    assert "order_by" not in mod and "columns_from" not in mod and "Unassigned" not in mod
    assert "_key.value if isinstance(_key, Enum)" in mod  # the enum-.value hardening is preserved
    # idempotent
    assert render_views(SCHEMA, static_only) == render_views(SCHEMA, static_only)


def test_render_byte_identical_and_paths():
    a = render_views(SCHEMA, VIEWS)
    assert a == render_views(SCHEMA, VIEWS)
    paths = {rel for rel, _ in a}
    for expected in (
        "app/views/jobs_dashboard.py", "app/views/pipeline_board.py", "app/views/job_workspace.py",
        "app/views/opportunity_detail.py", "app/views/job_export.py", "app/views/model_export.py",
        "app/views/value_map.py", "app/views/completeness_panel.py", "app/views/model_import.py",
        "app/views/artifact_reader.py", "app/views/_prose.py", "app/views/stage_board.py",
        "app/views/routes.py", "tests/test_views.py",
        "app/templates/views/job_workspace.html",
        "app/templates/views/opportunity_detail.html", "app/templates/views/job_export.html",
        "app/templates/views/value_map.html", "app/templates/views/completeness_panel.html",
        "app/templates/views/model_import.html", "app/templates/views/artifact_reader.html",
        "app/templates/views/stage_board.html",
    ):
        assert expected in paths
    # AR-3: a model-scoped export serves raw Markdown/JSON — no template is emitted for it
    assert "app/templates/views/model_export.html" not in paths


def test_rendered_python_is_ast_valid():
    import ast

    for rel, content in render_views(SCHEMA, VIEWS):
        if rel.endswith(".py"):
            ast.parse(content, filename=rel)


def test_board_groups_by_enum_value_not_member():
    """Board grouping keys on the field's string form, so a non-str Enum member can't fall
    outside the _ORDER strings (the §0 silent-empty-columns risk). Verified by executing the
    generated _data against rows whose group field is a PLAIN (non-str) Enum."""
    from enum import Enum

    mod = dict(render_views(SCHEMA, VIEWS))["app/views/pipeline_board.py"]
    assert "isinstance(_key, Enum)" in mod and "_key.value" in mod  # the hardening is present

    # Execute the generated grouping logic against a plain-Enum group field.
    class Stage(Enum):
        identified = "identified"
        offer = "offer"

    # Run only the grouping body against plain-Enum-bearing rows.
    rows = [type("R", (), {"stage": Stage.identified})(), type("R", (), {"stage": Stage.offer})()]
    cols: dict = {}
    for root in rows:
        _key = getattr(root, "stage")
        _key = _key.value if isinstance(_key, Enum) else _key
        cols.setdefault(_key, []).append(root)
    ordered = [(s, cols.pop(s, [])) for s in ["identified", "offer"]]
    assert [(s, len(v)) for s, v in ordered] == [("identified", 1), ("offer", 1)]  # matched, not empty


def test_drift_in_sync_and_tamper():
    rendered = dict(render_views(SCHEMA, VIEWS))
    mod = rendered["app/views/job_workspace.py"]
    assert is_owned_view_file(mod)
    assert views_in_sync(SCHEMA, VIEWS, "app/views/job_workspace.py", mod) is True
    assert views_in_sync(SCHEMA, VIEWS, "app/views/job_workspace.py", mod.replace("resolved", "x", 1)) is False


def test_emitted_view_tests_run_green(tmp_path):
    """The D1 gate: data functions resolve/aggregate/group correctly against generated tables."""
    pytest.importorskip("sqlmodel")
    files = list(render_backend(SCHEMA)) + list(render_views(SCHEMA, VIEWS))
    for rel, content in files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_views.py", "-q"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"emitted view tests failed:\n{result.stdout}\n{result.stderr}"
    # 6 data tests + value_map data/route (AR-1) + completeness_panel data (AR-2)
    # + artifact_reader prose-not-json (AR-6) + stage_board entity-backed (FR-EB)
    # + model_import round-trip/confirm-gate (AR-4)
    assert "13 passed" in result.stdout
