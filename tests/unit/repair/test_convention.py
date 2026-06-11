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


def test_detector_ignores_mentions_in_docstrings_and_strings():
    # Reliability (code-review fix): a `session.query`/`flask`/`render_template` mention inside a
    # docstring, string literal, or inline comment must NOT false-fire — else the verdict gate would
    # falsely FAIL the file (cf. app/ai/extract.py's docstring that describes the SQLAlchemy style).
    code = (
        '"""Supports the SQLAlchemy session.query(model).all() style.\n'
        "Do not use flask or render_template here.\n"
        '"""\n'
        "x = 1  # session.query is fine inside a comment\n"
        's = "from flask import nope"  # and inside a string literal\n'
    )
    assert detect_conventions(code) == []


def test_detector_still_flags_real_code_beside_prose():
    code = (
        "# note: this uses session.query (just a comment)\n"
        "def f(session):\n"
        "    return session.query(Model).all()\n"
    )
    d = detect_conventions(code)
    assert len(d) == 1
    assert d[0].convention_kind == "orm_idiom" and d[0].line == 3  # real code only, correct line


def test_orm_query_without_get_is_flagged_unsafe():
    d = detect_conventions("rows = session.query(Profile).all()\n")
    assert len(d) == 1
    assert d[0].convention_kind == "orm_idiom"
    assert d[0].safe_fixable is False  # plain .query() has no single-symbol rewrite


def test_sqlalchemy_infra_imports_are_not_flagged_but_orm_imports_are():
    # The sqlalchemy import rule must NOT false-fire on infrastructure primitives a SQLModel app
    # legitimately needs (no sqlmodel equivalent) — event/inspect (db.py), cast/or_/String (filters).
    for ok in (
        "from sqlalchemy import event, inspect as _i\n",
        "from sqlalchemy import String as _S, cast as _c, or_ as _o\n",
        "from sqlalchemy import Column, JSON\n",
    ):
        assert [d for d in detect_conventions(ok) if d.symbol == "sqlalchemy"] == [], ok
    # ...but genuine raw-ORM usage still fires.
    for bad in (
        "import sqlalchemy\n",
        "from sqlalchemy.orm import Session\n",
        "from sqlalchemy import select, event\n",
    ):
        assert any(d.symbol == "sqlalchemy" for d in detect_conventions(bad)), bad


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


def test_convention_gating_flag_reverts_to_advisory(monkeypatch):
    """FR-CAR-11: STARTD8_CONVENTION_GATING=0 makes the convention gate advisory (no hard-zero).

    Default (precondition met — measured FP 0% over the governed in-architecture corpus) is gating-ON;
    the off-switch is the §4 ramp control for architectures where the detector's FP rate is unmeasured.
    """
    from startd8.forward_manifest_validator import (
        DiskComplianceResult,
        compute_disk_quality_score,
    )

    wrong = DiskComplianceResult(
        file_path="x.py",
        convention_violations=[
            ConventionDiagnostic(
                category="convention", file="x.py", message="flask",
                convention_kind="framework", symbol="flask", severity="error",
            )
        ],
    )
    # Default (flag unset) and explicit "1" → gating ON → hard-zero.
    monkeypatch.delenv("STARTD8_CONVENTION_GATING", raising=False)
    assert compute_disk_quality_score(wrong) == 0.0
    monkeypatch.setenv("STARTD8_CONVENTION_GATING", "1")
    assert compute_disk_quality_score(wrong) == 0.0
    # Flag = "0" → advisory: the violation is still recorded on the result, but does not hard-zero.
    monkeypatch.setenv("STARTD8_CONVENTION_GATING", "0")
    assert compute_disk_quality_score(wrong) > 0.0


# --------------------------------------------------------------------------- #
# Phase B.2 — safe-fixer + authority-governed-scope guard (FR-CAR-4)
# --------------------------------------------------------------------------- #

def _fix(code: str, rel_path: str):
    from pathlib import Path

    from startd8.repair.models import RepairContext
    from startd8.repair.steps.python_convention_fix import PythonConventionFixStep

    return PythonConventionFixStep()(code, RepairContext(), Path(rel_path))


def test_safe_fix_query_get_in_generator_owned_file():
    # A generator-owned spine file (in CANONICAL_LAYOUT) IS auto-fixed.
    res = _fix("obj = session.query(Profile).get(item_id)\n", "app/routers.py")
    assert res.modified is True
    assert "session.get(Profile, item_id)" in res.code
    assert "query(" not in res.code


def test_query_rewrite_stays_spine_only_on_hand_written_file():
    # R1-F6 (preserved under FR-CAR-12): the dual-pattern-risky query→session.get rewrite stays
    # scoped to the generator spine — a hand-written app/ai/* file's session.query().get() is
    # NEVER rewritten (byte-identical). (The *unambiguous* module-source repoint has a wider
    # scope — see test_module_source_repoint_reaches_bespoke_app_file — but no wrong import here.)
    src = "rows = session.query(Profile).get(pid)\n"
    res = _fix(src, "app/ai/extract.py")
    assert res.modified is False
    assert res.code == src  # byte-identical — query rewrite is spine-only


def test_module_source_repoint_reaches_bespoke_app_file():
    # FR-CAR-12b (RUN-038 #5): the unambiguous app.models->app.tables repoint reaches bespoke app
    # routers (app/jobs.py) the spine guard excludes — and splits tables from schemas.
    from startd8.repair.steps.python_convention_fix import _is_app_package_file

    src = "from app.models import TailoredAsset, TailoredMatch, JobSchema\n"
    res = _fix(src, "generated/app/job_export.py")
    assert res.modified is True
    assert "from app.tables import TailoredAsset, TailoredMatch" in res.code
    assert "from app.models import JobSchema" in res.code  # schema stays put
    assert "module_source_repoint" in res.metrics.get("rules", [])
    # test files are excluded — their convention authority is the FR-CAR-12c prompt, not this fixer
    assert _is_app_package_file(__import__("pathlib").Path("tests/test_jobs.py")) is False


def test_safe_fix_skips_bespoke_view():
    # app/jobs.py (the RUN-028 file) is not a generator-owned kind → escalate, don't fix.
    res = _fix("x = session.query(Job).get(j)\n", "app/jobs.py")
    assert res.modified is False


def test_python_convention_route_registered():
    from startd8.repair.routing import _ROUTING_TABLE, _STEP_FACTORIES

    assert "python_convention_fix" in _STEP_FACTORIES
    assert any(
        cat == "convention" and lang == "python"
        for (cat, _pat, _steps, _conf, lang) in _ROUTING_TABLE
    )


# --------------------------------------------------------------------------- #
# Phase B.3 — escalate-don't-silence: the convention residual (FR-CAR-6 / R1-F9)
# --------------------------------------------------------------------------- #

def test_repair_outcome_carries_unrepaired_diagnostics():
    from startd8.repair.models import RepairOutcome

    # The residual contract exists and defaults empty (backward compatible).
    assert RepairOutcome().unrepaired_diagnostics == []


def test_convention_residual_surfaces_wrong_files_only(tmp_path):
    # R1-F9: detection on the final files — the surfacing the post-gen path would otherwise skip
    # (a lint-clean Flask file leaves no syntax/lint diagnostic).
    from startd8.repair.convention import unrepaired_convention_residual

    (tmp_path / "app").mkdir()
    wrong = tmp_path / "app" / "jobs.py"
    wrong.write_text(RUN028_LIKE, encoding="utf-8")
    clean = tmp_path / "app" / "routers.py"
    clean.write_text(render_routers(SCHEMA), encoding="utf-8")

    residual = unrepaired_convention_residual([wrong, clean])
    files = {d.file for d in residual}
    assert str(wrong) in files          # the Flask file's violations are surfaced
    assert str(clean) not in files      # the generated-clean file contributes nothing
    assert all(d.category == "convention" for d in residual)


def test_convention_residual_ignores_missing_and_non_python(tmp_path):
    from startd8.repair.convention import unrepaired_convention_residual

    assert unrepaired_convention_residual([tmp_path / "nope.py"]) == []
    txt = tmp_path / "readme.txt"
    txt.write_text("from flask import x\n", encoding="utf-8")
    assert unrepaired_convention_residual([txt]) == []  # non-.py ignored


# --------------------------------------------------------------------------- #
# Phase C — reach the cheapest tier: micro-prime generation guidance (FR-CAR-5)
# --------------------------------------------------------------------------- #

def test_render_convention_guidance_states_idioms_and_negatives():
    from startd8.repair.convention import render_convention_guidance

    g = render_convention_guidance()
    # positive house style (module names track CANONICAL_LAYOUT)
    for pos in ("FastAPI", "SQLModel", "Jinja2Templates", "app.tables", "app.models"):
        assert pos in g, pos
    # explicit negatives — the RUN-028 fallbacks
    for neg in ("Flask", "session.query", "render_template"):
        assert neg in g, neg


def test_from_prime_injects_guidance_for_python_targets_only():
    from startd8.micro_prime.context import MicroPrimeContext

    py = MicroPrimeContext.from_prime({}, None, ["app/jobs.py"], True)
    assert "FastAPI" in py.convention_guidance  # Python target → guidance injected

    go = MicroPrimeContext.from_prime({}, None, ["src/frontend/main.go"], True)
    assert go.convention_guidance == ""  # non-Python target → no Python guidance


def test_context_guidance_defaults_empty_backward_compatible():
    from startd8.micro_prime.context import MicroPrimeContext

    c = MicroPrimeContext(manifest=None, target_files=["x.py"])
    assert c.convention_guidance == ""  # frozen-dataclass field is defaulted


# --------------------------------------------------------------------------- #
# Phase D.9 — lock-step parity meta-test (FR-CAR-8)
# --------------------------------------------------------------------------- #

def test_lockstep_all_generated_python_is_convention_clean():
    # FR-CAR-8 lock-step guard: EVERY generator-owned Python artifact must be convention-clean.
    # The generators and the detector must agree by construction — if a generator ever emits a
    # house-style violation (Flask/session.query/render_template/app.models table import), or a new
    # artifact kind regresses, this test fails. This is what keeps repair coverage in step with the
    # expanding deterministic-generation surface.
    from startd8.backend_codegen import render_backend

    py_artifacts = [(p, c) for p, c in render_backend(SCHEMA) if p.endswith(".py")]
    assert len(py_artifacts) >= 5, "expected the full Python spine to be generated"
    offenders = {
        p: [f"{d.convention_kind}:{d.symbol}" for d in detect_conventions(c, file=p)]
        for p, c in py_artifacts
    }
    offenders = {p: v for p, v in offenders.items() if v}
    assert offenders == {}, f"generator emitted convention violations: {offenders}"


# --------------------------------------------------------------------------- #
# Phase D.10 — Kaizen convention feedback (FR-CAR-9)
# --------------------------------------------------------------------------- #

def test_kaizen_convention_cause_to_suggestion_registered():
    from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION

    entry = CAUSE_TO_SUGGESTION.get("requirement_convention_gap")
    assert entry is not None, "convention gap must feed Kaizen (FR-CAR-9)"
    assert entry["phase"] == "draft"
    hint = entry["hint"]
    assert "FastAPI" in hint and "SQLModel" in hint and "app.tables" in hint
    assert "Flask" in hint and "session.query" in hint  # negatives in the next-run hint
