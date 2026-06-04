"""Convention-aware repair — Phase A (advisory detection).

Asserts: the authority is derived from the generators' `CANONICAL_LAYOUT`; a *generated* backend file is
convention-clean (parity); each RUN-028 anti-flavor is detected with the right `convention_kind` and
`safe_fixable`; and `app.models`-vs-`app.tables` module-source detection respects the `*Schema` exception.
Phase A is detect-only — these tests exercise detection, not fixing or verdict.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen.crud_generator import render_routers
from startd8.backend_codegen.htmx_generator import render_web
from startd8.repair.convention import (
    build_python_convention_authority,
    detect_conventions,
)
from startd8.repair.models import ConventionDiagnostic

pytestmark = pytest.mark.unit

SCHEMA = """\
model Profile {
  id   String @id
  name String
}
"""

# The RUN-028 anti-flavors, verbatim-shaped (Flask + app.models table import + SQLAlchemy + render_template).
RUN028_LIKE = """\
from flask import request, render_template, Response
from app.models import Profile, resolve_matches

@app.route("/jobs")
def jobs(session):
    item = session.query(Profile).get(id)
    rows = session.query(Profile).all()
    return render_template("jobs.html", rows=rows)
"""


def test_authority_derived_from_canonical_layout():
    auth = build_python_convention_authority()
    assert auth.tables_module == "app.tables"
    assert auth.schemas_module == "app.models"


def test_generated_backend_is_convention_clean():
    # Parity (FR-CAR-2): the generator's own output must trip ZERO convention detectors.
    for generated in (render_routers(SCHEMA), render_web(SCHEMA)):
        assert detect_conventions(generated) == []


def test_run028_anti_flavors_all_detected():
    diags = detect_conventions(RUN028_LIKE, file="app/jobs.py")
    assert all(isinstance(d, ConventionDiagnostic) and d.category == "convention" for d in diags)
    kinds = {d.convention_kind for d in diags}
    assert {"framework", "orm_idiom", "module_source", "template_idiom"} <= kinds
    # every diagnostic is anchored to a line and carries the canonical expectation
    assert all(d.line > 0 and d.expected for d in diags)


def test_safe_fixable_flags():
    diags = detect_conventions(RUN028_LIKE)
    by_symbol = {d.symbol: d for d in diags}
    # the .query().get() rewrite is deterministic → safe-fixable; a wholesale Flask import is not
    assert by_symbol["session.query(...).get(...)"].safe_fixable is True
    assert by_symbol["flask"].safe_fixable is False
    # module-source repoint is deterministic (Phase B does the shadow check)
    assert any(d.convention_kind == "module_source" and d.safe_fixable for d in diags)


def test_module_source_respects_schema_exception():
    # importing a *table* from app.models is wrong...
    bad = "from app.models import Profile\n"
    d = detect_conventions(bad)
    assert [x.convention_kind for x in d] == ["module_source"]
    # ...but importing a Pydantic *Schema from app.models is correct (no diagnostic)
    ok = "from app.models import ProfileSchema, MetricSchema\n"
    assert detect_conventions(ok) == []
    # ...and importing the table from app.tables is correct
    assert detect_conventions("from app.tables import Profile\n") == []


def test_comments_are_ignored():
    assert detect_conventions("# from flask import x — a note, not code\n") == []


def test_orm_query_without_get_is_flagged_unsafe():
    d = detect_conventions("rows = session.query(Profile).all()\n")
    assert len(d) == 1
    assert d[0].convention_kind == "orm_idiom"
    assert d[0].safe_fixable is False  # plain .query() has no single-symbol rewrite


# --------------------------------------------------------------------------- #
# Phase B.1 — the verdict hard-gate (FR-CAR-7)
# --------------------------------------------------------------------------- #

def test_verdict_hard_gate_fails_lint_clean_wrong_file():
    from startd8.forward_manifest_validator import (
        DiskComplianceResult,
        compute_disk_quality_score,
    )

    # A structurally-perfect file (ast_valid, no stubs, full contract/import) scores 1.0 — the
    # convention gate is additive and does NOT touch convention-clean scores (regression guard, R1-F8).
    clean = DiskComplianceResult(file_path="x.py")
    assert compute_disk_quality_score(clean) == 1.0

    # The SAME structurally-perfect file, but with an error-severity convention violation, scores 0.0 —
    # the symptom-fix trap is closed: a lint-clean Flask view cannot pass.
    wrong = DiskComplianceResult(
        file_path="x.py",
        convention_violations=[
            ConventionDiagnostic(
                category="convention", file="x.py", message="flask",
                convention_kind="framework", symbol="flask", severity="error",
            )
        ],
    )
    assert compute_disk_quality_score(wrong) == 0.0


def test_verdict_gate_end_to_end_on_flask_file(tmp_path):
    # Integration: a valid-Python Flask file on disk → convention_violations populated → score 0.0,
    # even though it is ast_valid (the exact RUN-028 lint-clean-but-wrong shape).
    from startd8.forward_manifest_validator import (
        compute_disk_quality_score,
        validate_disk_compliance,
    )

    f = tmp_path / "app" / "jobs.py"
    f.parent.mkdir(parents=True)
    f.write_text(RUN028_LIKE, encoding="utf-8")
    res = validate_disk_compliance("app/jobs.py", str(tmp_path))
    assert res.ast_valid is True  # Flask is valid Python — structurally clean
    assert res.convention_violations  # ...but convention-dirty
    assert compute_disk_quality_score(res) == 0.0
