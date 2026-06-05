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
}

model Capability {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  name      String?
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
""".strip()


def test_strict_validation_rejects_unknown_entity():
    bad = VIEWS.replace("root: Opportunity", "root: Nonexistent")
    with pytest.raises(ValueError):
        parse_views(bad, known_entities=frozenset({"JobDescription", "TailoredMatch", "TailoredAsset", "Capability"}))


def test_render_byte_identical_and_paths():
    a = render_views(SCHEMA, VIEWS)
    assert a == render_views(SCHEMA, VIEWS)
    paths = {rel for rel, _ in a}
    for expected in (
        "app/views/jobs_dashboard.py", "app/views/pipeline_board.py", "app/views/job_workspace.py",
        "app/views/routes.py", "tests/test_views.py",
        "app/templates/views/job_workspace.html",
    ):
        assert expected in paths


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
    assert "3 passed" in result.stdout
