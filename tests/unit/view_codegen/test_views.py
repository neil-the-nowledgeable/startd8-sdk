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
    # scope is export-package-only
    bad = VIEWS.replace("kind: board\n    route: /pipeline", "kind: board\n    scope: model\n    route: /pipeline")
    with pytest.raises(ValueError, match="only valid on kind 'export-package'"):
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
        "app/views/routes.py", "tests/test_views.py",
        "app/templates/views/job_workspace.html",
        "app/templates/views/opportunity_detail.html", "app/templates/views/job_export.html",
    ):
        assert expected in paths
    # AR-3: a model-scoped export serves raw Markdown/JSON — no template is emitted for it
    assert "app/templates/views/model_export.html" not in paths


def test_rendered_python_is_ast_valid():
    import ast

    for rel, content in render_views(SCHEMA, VIEWS):
        if rel.endswith(".py"):
            ast.parse(content, filename=rel)


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
    assert "6 passed" in result.stdout
