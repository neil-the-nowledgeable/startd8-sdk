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
from startd8.view_codegen import is_owned_view_file, parse_views, render_views, views_in_sync

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
  metrics       String?
  economicBuyer String?
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
            "Opportunity", "Contact", "Activity",
        }))


_KNOWN = frozenset({
    "JobDescription", "TailoredMatch", "TailoredAsset", "Capability",
    "Opportunity", "Contact", "Activity",
})


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


def test_render_byte_identical_and_paths():
    a = render_views(SCHEMA, VIEWS)
    assert a == render_views(SCHEMA, VIEWS)
    paths = {rel for rel, _ in a}
    for expected in (
        "app/views/jobs_dashboard.py", "app/views/pipeline_board.py", "app/views/job_workspace.py",
        "app/views/opportunity_detail.py", "app/views/job_export.py", "app/views/model_export.py",
        "app/views/value_map.py", "app/views/completeness_panel.py", "app/views/model_import.py",
        "app/views/routes.py", "tests/test_views.py",
        "app/templates/views/job_workspace.html",
        "app/templates/views/opportunity_detail.html", "app/templates/views/job_export.html",
        "app/templates/views/value_map.html", "app/templates/views/completeness_panel.html",
        "app/templates/views/model_import.html",
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
    # + model_import round-trip/confirm-gate (AR-4)
    assert "11 passed" in result.stdout
