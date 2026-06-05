"""Full worst-wins composition matrix (R6-F3/R6-S4 validation criterion).

Every reachable (schema status × secondary-manifest status) pair for the three multi-manifest
sections resolves to exactly one documented section status:

- Forms = schema + human_inputs (both always participate; absent human_inputs ⇒ `defaults`)
- Composite Views = schema + views (both always participate; absent views ⇒ `not_defined`)
- Services = schema + ai_passes (ai participates only in its degradation states
  `invalid`/`placeholder`; mere absence scopes to the AI items per the FR-W4 table)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.wireframe import Status, build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.plan import _PRECEDENCE, worst

# Manifest texts producing each reachable status, per manifest -------------------------------

SCHEMA = {
    Status.PLANNED: "model Profile {\n  id String @id\n  name String\n}\n",
    Status.PLACEHOLDER: "// scaffolded stub — no models yet\n",
    # Nested-unclosed first block drops the inner declaration (verified parser behavior).
    Status.INVALID: "model Profile {\n  id String @id\nmodel B {\n  x String\n}\n",
    Status.NOT_DEFINED: None,  # absent
}

HUMAN_INPUTS = {
    Status.PLANNED: "fields:\n  - target: Profile.name\n    authored_by: human\n",
    Status.PLACEHOLDER: "fields:\n  - target: REPLACE_WITH_Entity.field\n    authored_by: human\n",
    Status.INVALID: "fields:\n  - no_target_key: 1\n",
    Status.DEFAULTS: None,  # absent ⇒ defaults
}

AI_PASSES = {
    Status.PLANNED: (
        "passes:\n  - name: p1\n    output_entities: [Profile]\n"
        "    route_path: /ai/p1\n    prompt: do the thing\n"
    ),
    Status.PLACEHOLDER: (
        "passes:\n  - name: p1\n    output_entities: [Profile]\n"
        "    route_path: /ai/p1\n    prompt: REPLACE_WITH_PROMPT\n"
    ),
    Status.INVALID: "passes: []\n",
    Status.NOT_DEFINED: None,  # absent ⇒ AI items not_defined, section unaffected
}

VIEWS = {
    Status.PLANNED: (
        "views:\n  - name: v1\n    kind: dashboard\n    route: /views/v1\n    root: Profile\n"
    ),
    Status.PLACEHOLDER: (
        "views:\n  - name: v1\n    kind: dashboard\n    route: /REPLACE_WITH_ROUTE\n"
        "    root: Profile\n"
    ),
    Status.INVALID: "views:\n  - {name: v1, kind: nonsense, route: /v1, root: Profile}\n",
    Status.NOT_DEFINED: None,
}


def _project(tmp_path: Path, schema_status: str, key: str, text) -> Path:
    root = tmp_path / "p"
    (root / "prisma").mkdir(parents=True)
    schema_text = SCHEMA[schema_status]
    if schema_text is not None:
        (root / "prisma" / "schema.prisma").write_text(schema_text, encoding="utf-8")
    if text is not None:
        (root / "prisma" / f"{key}.yaml").write_text(text, encoding="utf-8")
    return root


def _section_status(root: Path, section: str) -> str:
    plan = build_wireframe_plan(load_assembly_inputs(project_root=root))
    return plan.section(section).status


@pytest.mark.parametrize("schema_status", sorted(SCHEMA, key=_PRECEDENCE.get))
@pytest.mark.parametrize("human_status", sorted(HUMAN_INPUTS, key=_PRECEDENCE.get))
def test_forms_matrix(tmp_path: Path, schema_status: str, human_status: str) -> None:
    root = _project(tmp_path, schema_status, "human_inputs", HUMAN_INPUTS[human_status])
    assert _section_status(root, "forms") == worst(schema_status, human_status)


@pytest.mark.parametrize("schema_status", sorted(SCHEMA, key=_PRECEDENCE.get))
@pytest.mark.parametrize("views_status", sorted(VIEWS, key=_PRECEDENCE.get))
def test_views_matrix(tmp_path: Path, schema_status: str, views_status: str) -> None:
    root = _project(tmp_path, schema_status, "views", VIEWS[views_status])
    assert _section_status(root, "views") == worst(schema_status, views_status)


@pytest.mark.parametrize("schema_status", sorted(SCHEMA, key=_PRECEDENCE.get))
@pytest.mark.parametrize("ai_status", sorted(AI_PASSES, key=_PRECEDENCE.get))
def test_services_matrix(tmp_path: Path, schema_status: str, ai_status: str) -> None:
    root = _project(tmp_path, schema_status, "ai_passes", AI_PASSES[ai_status])
    # ai_passes participates only in its degradation states; absence (and planned) scope to
    # items, leaving the section at the schema's status (FR-W4 table + R6-F3 as merged).
    expected = (
        worst(schema_status, ai_status)
        if ai_status in (Status.INVALID, Status.PLACEHOLDER)
        else schema_status
    )
    assert _section_status(root, "services") == expected
