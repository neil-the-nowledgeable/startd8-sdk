"""Step 6 (FR-6/7/8): derived emitters — export, AI schemas, completeness.

export.py and completeness.py are pure stdlib, so the tests EXECUTE the generated code and call it
(strongest validation). ai_schemas.py imports pydantic + the generated models, so it's
syntax-validated. All three participate in the shared drift/$0.00 model.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import (
    owned_file_in_sync,
    render_ai_schemas,
    render_completeness,
    render_derived,
    render_export,
)
from startd8.backend_codegen.drift import embedded_artifact_kind

pytestmark = pytest.mark.unit

SCHEMA = """\
model Profile {
  id   String @id
  name String
}

model ProofPoint {
  id     String @id
  result String
}
"""


def _exec(src: str) -> dict:
    ns: dict = {}
    exec(compile(src, "<gen>", "exec"), ns)
    return ns


def test_export_runs_json_and_markdown():
    ns = _exec(render_export(SCHEMA))
    assert ns["ENTITY_ORDER"] == ["Profile", "ProofPoint"]
    payload = {
        "Profile": [{"id": "p1", "name": "Ada"}],
        "ProofPoint": [{"id": "x1", "result": "shipped"}],
    }
    # JSON is lossless + stable (sorted keys)
    js = ns["to_json"](payload)
    assert '"name": "Ada"' in js
    assert ns["to_json"](payload) == js  # deterministic
    # Markdown: section per entity in schema order, field lines in order
    md = ns["to_markdown"](payload)
    assert md.index("# Profile") < md.index("# ProofPoint")
    assert "- name: Ada" in md
    assert "- result: shipped" in md


def test_completeness_runs_and_scores():
    ns = _exec(render_completeness(SCHEMA))
    Result = ns["CompletenessResult"]
    r = ns["compute_completeness"]({"Profile": 1, "ProofPoint": 0})
    assert isinstance(r, Result)
    assert r.score == 0.5  # 1 of 2 entities present
    assert r.nudges == ["Add at least one ProofPoint."]
    # all present -> 1.0, no nudges
    full = ns["compute_completeness"]({"Profile": 3, "ProofPoint": 2})
    assert full.score == 1.0 and full.nudges == []
    # none present -> 0.0, nudges in schema order
    empty = ns["compute_completeness"]({})
    assert empty.score == 0.0
    assert empty.nudges == ["Add at least one Profile.", "Add at least one ProofPoint."]


def test_ai_schemas_structure_and_compiles():
    src = render_ai_schemas(SCHEMA)
    compile(src, "<ai>", "exec")
    assert "from .models import ProfileSchema, ProofPointSchema" in src
    assert "'Profile': ProfileSchema," in src
    assert "def json_schema(entity: str)" in src
    assert ".model_json_schema()" in src


def test_all_derived_artifacts_in_sync_and_tagged():
    arts = render_derived(SCHEMA)
    paths = {p for p, _ in arts}
    assert paths == {"app/export.py", "app/ai_schemas.py", "app/completeness.py"}
    for _path, content in arts:
        assert owned_file_in_sync(SCHEMA, content) is True
        assert embedded_artifact_kind(content).startswith("python-")


def test_requirements_manifest():
    from startd8.backend_codegen import render_requirements

    req = render_requirements(SCHEMA)
    assert req.startswith("# GENERATED from")  # pip ignores # comment lines
    for dep in (
        "fastapi",
        "sqlmodel",
        "jinja2",
        "python-multipart",
        "uvicorn[standard]",
    ):
        assert dep in req
    assert owned_file_in_sync(SCHEMA, req) is True
    assert embedded_artifact_kind(req) == "python-requirements"


def test_derived_tamper_detected():
    export = render_export(SCHEMA)
    assert (
        owned_file_in_sync(SCHEMA, export.replace("sort_keys=True", "sort_keys=False"))
        is False
    )
