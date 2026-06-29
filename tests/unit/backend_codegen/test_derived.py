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


def test_completeness_no_manifest_unchanged():
    """OQ-4: absent manifest → the flat presence-rule output (no weighted code emitted)."""
    src = render_completeness(SCHEMA)
    assert "Presence rule (OQ-4 v1)" in src
    assert "_CONFIG" not in src and "_EXCLUDED" not in src


def test_completeness_weighted_manifest_exclude_and_threshold():
    manifest = {"exclude": ["ProofPoint"], "entities": {"Profile": {"min_rows": 2, "weight": 3}}}
    ns = _exec(render_completeness(SCHEMA, manifest=manifest))
    # ProofPoint excluded → out of denominator; Profile needs >=2 rows
    r = ns["compute_completeness"]({"Profile": 1, "ProofPoint": 0})
    assert r.score == 0.0 and r.nudges == ["Add at least 2 Profile."]
    full = ns["compute_completeness"]({"Profile": 2})
    assert full.score == 1.0 and full.nudges == []


def test_completeness_weighted_fraction_and_nudge_qty():
    manifest = {"entities": {"Profile": {"weight": 3}, "ProofPoint": {"min_rows": 2, "weight": 1}}}
    ns = _exec(render_completeness(SCHEMA, manifest=manifest))
    r = ns["compute_completeness"]({"Profile": 1, "ProofPoint": 1})
    assert r.score == 0.75  # weight 3 met / total 4
    assert r.nudges == ["Add at least 2 ProofPoint."]


def test_completeness_custom_nudge_text_is_used():
    """D7: an author-supplied `nudge` replaces the generated message for the unmet signal; an
    entity without a nudge falls back to the generated "Add at least N <Entity>." text."""
    manifest = {"entities": {
        "Profile": {"min_rows": 2, "nudge": "Tell us who you are first."},
        "ProofPoint": {"min_rows": 1},  # no custom nudge → generated message
    }}
    src = render_completeness(SCHEMA, manifest=manifest)
    assert "_NUDGES" in src  # the map is emitted only when a custom nudge is present
    ns = _exec(src)
    r = ns["compute_completeness"]({"Profile": 0, "ProofPoint": 0})
    assert r.nudges == ["Tell us who you are first.", "Add at least one ProofPoint."]
    # met signals never nudge
    assert ns["compute_completeness"]({"Profile": 2, "ProofPoint": 1}).nudges == []


def test_completeness_without_nudge_is_byte_identical_to_prior():
    """D7 byte-identical-when-absent: a weighted manifest with no `nudge` key emits no `_NUDGES`
    map and the prior append line — the output must not drift for manifests that don't use it."""
    manifest = {"entities": {"Profile": {"min_rows": 2, "weight": 3}}}
    src = render_completeness(SCHEMA, manifest=manifest)
    assert "_NUDGES" not in src
    assert "nudges.append(f'Add at least {qty} {e}.')" in src


def test_completeness_signals_are_opt_in_new_entity_is_inert():
    """F-13 regression: a signal is OPT-IN — an entity that is neither configured nor excluded
    is INERT (out of the denominator), so adding a model to the contract cannot silently change
    the score. Under the old opt-out rule (included = ENTITIES - exclude) the unconfigured
    ProofPoint would have become a default-required signal, dropping a complete model to 0.5 with
    a spurious nudge — exactly the leak that turned StartDate's `main` red."""
    # Only Profile is declared a signal; ProofPoint is neither configured nor excluded.
    manifest = {"entities": {"Profile": {"min_rows": 1}}}
    ns = _exec(render_completeness(SCHEMA, manifest=manifest))
    # Profile satisfied, ProofPoint inert → complete, no spurious ProofPoint nudge.
    r = ns["compute_completeness"]({"Profile": 1})
    assert r.score == 1.0 and r.nudges == []
    # An unconfigured entity having rows neither helps nor hurts the score.
    assert ns["compute_completeness"]({"Profile": 1, "ProofPoint": 99}).score == 1.0
    # The single configured signal still drives the score when unmet.
    unmet = ns["compute_completeness"]({})
    assert unmet.score == 0.0 and unmet.nudges == ["Add at least one Profile."]


def test_completeness_exclude_is_advisory_override_of_a_configured_signal():
    """F-13: with opt-in, `exclude` is no longer needed to keep non-signals out, but it still
    works as an override — it can drop an explicitly-configured entity from the denominator."""
    manifest = {"exclude": ["ProofPoint"], "entities": {"Profile": {"min_rows": 1},
                                                          "ProofPoint": {"min_rows": 1}}}
    ns = _exec(render_completeness(SCHEMA, manifest=manifest))
    # ProofPoint is configured but also excluded → excluded wins, out of denominator.
    r = ns["compute_completeness"]({"Profile": 1})
    assert r.score == 1.0 and r.nudges == []


_CMPL_YAML = "exclude: [ProofPoint]\nentities:\n  Profile: {min_rows: 2, weight: 3}\n"


def test_completeness_generate_and_drift_consistent_with_manifest():
    """Step-4 wiring: generate weighted + drift-check with the SAME manifest → in_sync."""
    from startd8.backend_codegen import render_backend, check_drift
    arts = dict(render_backend(SCHEMA, completeness_text=_CMPL_YAML))
    completeness = arts["app/completeness.py"]
    assert "_CONFIG" in completeness  # weighted output
    # same manifest → both paths regen identical bytes → in_sync (the consistency guarantee)
    assert check_drift(SCHEMA, completeness, completeness_text=_CMPL_YAML).status == "in_sync"
    # WITHOUT the manifest, drift regens flat → mismatch (threading is load-bearing)
    assert check_drift(SCHEMA, completeness, completeness_text=None).status != "in_sync"


def test_completeness_no_manifest_generate_and_drift_unchanged():
    """Projects without completeness.yaml: flat output + clean drift (zero behavior change)."""
    from startd8.backend_codegen import render_backend, check_drift
    completeness = dict(render_backend(SCHEMA))["app/completeness.py"]
    assert "_CONFIG" not in completeness
    assert check_drift(SCHEMA, completeness).status == "in_sync"
