"""Inc 7 — owned skeleton planning (FR-6/FR-7, owned-only v1).

The schema-types file is always owned; the directory skeleton comes from the file manifest
(RUN-013 prevention); barrels/CSS are gated on conventions, and their *absence* is recorded
as an explicit anti-invention note (RUN-012).
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import (
    ProjectConventions,
    plan_frontend_skeleton,
    render_barrel,
    render_css_module_stub,
)

pytestmark = pytest.mark.unit

SCHEMA = "model M {\n  id String @id\n  name String\n}"

_NO_BARRELS = ProjectConventions(
    alias="@/",
    alias_target="./",
    uses_barrels=False,
    uses_css_modules=False,
    has_types_dir=False,
)
_USES_BOTH = ProjectConventions(
    alias="@/",
    alias_target="./",
    uses_barrels=True,
    uses_css_modules=True,
    has_types_dir=True,
)


# --------------------------------------------------------------------------- #
# Standalone deterministic emitters
# --------------------------------------------------------------------------- #


def test_render_barrel_is_deterministic_and_ordered():
    assert render_barrel(["a", "b"]) == 'export * from "./a";\nexport * from "./b";\n'
    assert render_barrel(["a", "b"]) == render_barrel(["a", "b"])


def test_render_css_module_stub():
    assert render_css_module_stub() == ".root {\n}\n"


# --------------------------------------------------------------------------- #
# Plan: schema-types owned artifact + gated decisions
# --------------------------------------------------------------------------- #


def test_schema_types_is_the_owned_artifact():
    plan = plan_frontend_skeleton("/x", SCHEMA, conventions=_NO_BARRELS)
    schema_artifacts = [a for a in plan.artifacts if a.kind == "schema"]
    assert len(schema_artifacts) == 1
    art = schema_artifacts[0]
    assert art.ownership == "owned"
    assert art.path == "lib/value-model.ts"
    assert "export const MSchema = z.object({" in art.content


def test_absent_barrels_and_css_recorded_as_anti_invention_notes():
    plan = plan_frontend_skeleton("/x", SCHEMA, conventions=_NO_BARRELS)
    joined = " ".join(plan.notes)
    assert "does not use barrels" in joined
    assert "does not use CSS modules" in joined
    # nothing generated for them
    assert not any(a.kind in ("barrel", "css") for a in plan.artifacts)


def test_project_using_barrels_and_css_gets_no_absence_notes():
    plan = plan_frontend_skeleton("/x", SCHEMA, conventions=_USES_BOTH)
    assert plan.notes == ()


def test_directory_skeleton_from_file_manifest():
    plan = plan_frontend_skeleton(
        "/x",
        SCHEMA,
        conventions=_NO_BARRELS,
        target_modules=["lib/export/markdown.ts", "lib/export/json.ts", "app/page.tsx"],
    )
    dirs = sorted(a.path for a in plan.directories())
    assert dirs == ["app", "lib", "lib/export"]
    assert all(a.ownership == "owned" and a.content is None for a in plan.directories())


def test_plan_surfaces_unrenderable_fields():
    schema = "model M {\n  id String @id\n  geom Unsupported\n}"
    plan = plan_frontend_skeleton("/x", schema, conventions=_NO_BARRELS)
    assert any(u.field == "geom" for u in plan.unrenderable)
