"""Scoped relational AI-pass shape — FR-SRP (strtd8 FR-MSG interviewer-message harness → $0).

A per-row pass scoped to a source row resolves a relational join (FK traversal + whole-model confirmed
context) into the prompt and writes a cascade-FK child (real FK from the join + loose provenance),
degrading to needs_more_data when the scope/required-relation/confirmed-context is missing.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen.ai_layer import ScopeRelation, parse_ai_passes, render_ai_pass

pytestmark = pytest.mark.unit

SCHEMA = """
model Contact {
  id              String  @id @default(cuid())
  ownerId         String  @default("local")
  source          String  @default("user")
  confirmed       Boolean @default(true)
  name            String?
  interviewerType String?
  jobDescriptionId String?
  companyId       String?
}

model JobDescription {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  confirmed Boolean @default(true)
  title     String?
}

model Company {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  confirmed Boolean @default(true)
  name      String?
}

model ValueProp {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  confirmed Boolean @default(false)
  statement String?
}

model TailoredAsset {
  id               String  @id @default(cuid())
  ownerId          String  @default("local")
  source           String  @default("user")
  confirmed        Boolean @default(false)
  kind             String?
  body             String?
  jobDescriptionId String
  companyId        String?
  contactId        String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

MANIFEST = """
passes:
  - name: draft_interviewer_message
    output_entities: [TailoredAsset]
    route_path: /draft-message
    prompt: prompts/draft_message.md
    scope: Contact
    scope_relations:
      - { via: jobDescriptionId, entity: JobDescription }
      - { via: companyId, entity: Company, optional: true }
    reads_confirmed: [ValueProp]
    output_fk: { jobDescriptionId: JobDescription }
    source_binding: contactId
    trigger: { entity: Contact, text_field: name, label: Draft message }
""".strip()

# mark the harness-set fields human-owned so the edge schema doesn't ask the AI to author them
HUMAN = (
    "fields:\n"
    "  - target: TailoredAsset.jobDescriptionId\n    authored_by: human\n"
    "  - target: TailoredAsset.contactId\n    authored_by: human\n"
)


# --------------------------------------------------------------------------- #
# FR-SRP-1 manifest
# --------------------------------------------------------------------------- #

def test_scoped_pass_parses():
    ps = parse_ai_passes(MANIFEST)[0]
    assert ps.is_scoped and ps.scope == "Contact"
    assert ps.scope_relations == (
        ScopeRelation("jobDescriptionId", "JobDescription", False),
        ScopeRelation("companyId", "Company", True),
    )
    assert ps.reads_confirmed == ("ValueProp",)
    assert ps.output_fk == (("jobDescriptionId", "JobDescription"),)


@pytest.mark.parametrize("old,new,msg", [
    ("scope: Contact", "scope: Nope", "scope 'Nope' is not a model"),
    ("via: jobDescriptionId", "via: nopeId", "via 'nopeId' is not a field"),
    ("entity: Company", "entity: Nope", "entity 'Nope' is not a model"),
    ("reads_confirmed: [ValueProp]", "reads_confirmed: [Nope]", "reads_confirmed 'Nope' is not a model"),
])
def test_scoped_validation_fails_loud(old, new, msg):
    with pytest.raises(ValueError, match=msg):
        render_ai_pass(SCHEMA, MANIFEST.replace(old, new), HUMAN, pass_name="draft_interviewer_message")


def test_output_fk_must_target_a_required_relation():
    # companyId is optional → an output_fk onto Company would risk a null FK → loud fail.
    m = MANIFEST.replace("output_fk: { jobDescriptionId: JobDescription }",
                         "output_fk: { jobDescriptionId: JobDescription, companyId: Company }")
    with pytest.raises(ValueError, match="must be a REQUIRED scope_relations entity"):
        render_ai_pass(SCHEMA, m, HUMAN, pass_name="draft_interviewer_message")


# --------------------------------------------------------------------------- #
# FR-SRP-2/3/4 codegen
# --------------------------------------------------------------------------- #

def test_scoped_harness_renders_join_persist_and_degradation():
    code = render_ai_pass(SCHEMA, MANIFEST, HUMAN, pass_name="draft_interviewer_message")
    compile(code, "<scoped>", "exec")
    # FR-SRP-2: scoped signature + FK traversal + confirmed read
    assert "def draft_interviewer_message(text: str, session: Session, source_id: str)" in code
    assert "scope = session.get(Contact, source_id)" in code
    assert "_jobdescription = session.get(JobDescription, _fkid)" in code      # required FK
    assert "_company = session.get(Company, _fkid)" in code                    # optional FK
    assert "_valueprop_rows = session.exec(select(ValueProp).where(ValueProp.confirmed.is_(True))).all()" in code
    # FR-SRP-4: needs_more_data floors (scope missing / required relation / no confirmed context)
    assert "'status': 'needs_more_data'" in code
    assert code.count("return _needs") >= 2
    # FR-SRP-3: real FK from the resolved join + loose provenance, via the scoped persist
    assert "_persist_scoped(session, TailoredAsset, result, source_id, _PROVENANCE_FIELD, {'jobDescriptionId': _jobdescription.id})" in code
    assert "_PROVENANCE_FIELD = 'contactId'" in code
    assert "setattr(row, prov_field, source_id)" in code and "setattr(row, _fk, _val)" in code


def test_scoped_pass_drift_round_trips():
    # FR-SRP-5: the scoped pass is the `ai-pass` kind → drift re-renders it; round-trips to in_sync.
    from startd8.backend_codegen import check_drift, render_backend

    files = dict(render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN))
    mod = files["app/ai/draft_interviewer_message.py"]
    res = check_drift(SCHEMA, mod, manifest_text=MANIFEST, human_inputs_text=HUMAN)
    assert res.status == "in_sync", res.reason


def test_optional_relation_has_no_degradation_guard():
    code = render_ai_pass(SCHEMA, MANIFEST, HUMAN, pass_name="draft_interviewer_message")
    # the required job relation guards; the optional company one does not return _needs
    job_idx = code.index("_jobdescription = session.get")
    comp_idx = code.index("_company = session.get")
    between_job = code[job_idx:comp_idx]
    assert "return _needs" in between_job                                       # job (required) guards
    after_comp = code[comp_idx:code.index("_valueprop_rows")]
    assert "if _company is None" not in after_comp                              # company (optional) doesn't


# --------------------------------------------------------------------------- #
# FR-SRP runtime — the join resolves, the child persists with a real FK, degradation works
# --------------------------------------------------------------------------- #

_MY_TABLES = {"contact", "jobdescription", "company", "valueprop", "tailoredasset", "aicall"}


def _purge():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_scoped_pass_runtime(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    def _drop():
        md = sqlmodel.SQLModel.metadata
        for n in list(_MY_TABLES):
            t = md.tables.get(n)
            if t is not None:
                md.remove(t)

    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    sys.path.insert(0, str(tmp_path))
    _purge()
    _drop()
    try:
        main = importlib.import_module("app.main")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        ai_service = importlib.import_module("app.ai.service")
        from fastapi.testclient import TestClient
        from sqlmodel import Session, select
        from startd8.models import GenerateResult

        class _FakeAgent:
            def generate_structured(self, prompt, output_schema, **kw):
                # the AI authors only edge fields (kind/body); FKs are harness-set
                return output_schema(kind="outreach_email", body="Hi there"), GenerateResult("{}", 1, None)

        monkeypatch.setattr(ai_service, "resolve_agent_spec", lambda *a, **k: _FakeAgent())

        with TestClient(main.app) as c:
            with Session(db.engine) as s:
                job = tables.JobDescription(title="Staff Eng")
                s.add(job)
                s.commit()
                s.refresh(job)
                job_id = job.id
                s.add(tables.ValueProp(statement="I ship", confirmed=True))   # confirmed context
                linked = tables.Contact(name="Ada", interviewerType="hiring_manager", jobDescriptionId=job_id)
                unlinked = tables.Contact(name="Grace")                          # no job → needs_more_data
                s.add(linked)
                s.add(unlinked)
                s.commit()
                s.refresh(linked)
                s.refresh(unlinked)
                linked_id, unlinked_id = linked.id, unlinked.id

            # linked contact → a TailoredAsset with the REAL job FK + loose contactId
            ok = c.post(f"/ai/draft-message", json={"text": "", "source_id": linked_id})
            assert ok.status_code == 200, ok.text
            assert ok.json()["status"] == "ok"
            with Session(db.engine) as s:
                assets = s.exec(select(tables.TailoredAsset)).all()
            assert len(assets) == 1
            a = assets[0]
            assert a.jobDescriptionId == job_id          # REAL FK from the resolved join (not null)
            assert a.contactId == linked_id              # loose provenance
            assert a.source == "ai" and a.confirmed is False and a.kind == "outreach_email"

            # unlinked contact (no job) → graceful needs_more_data, no draft
            nd = c.post(f"/ai/draft-message", json={"text": "", "source_id": unlinked_id})
            assert nd.status_code == 200 and nd.json()["status"] == "needs_more_data"
            with Session(db.engine) as s:
                assert len(s.exec(select(tables.TailoredAsset)).all()) == 1   # still just the one
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge()
        _drop()


# --------------------------------------------------------------------------- #
# FRSRP test-gen mismatch — the generated per-pass test must call the helper the
# SCOPED harness actually defines (`_persist_scoped`), not `_persist_source`.
# Regression for the red gate the app team filed 2026-06-11.
# --------------------------------------------------------------------------- #

def test_scoped_generated_test_calls_persist_scoped_not_source():
    from startd8.backend_codegen.ai_layer import render_ai_pass_tests

    test_src = render_ai_pass_tests(SCHEMA, MANIFEST, HUMAN)
    harness = render_ai_pass(SCHEMA, MANIFEST, HUMAN, pass_name="draft_interviewer_message")
    compile(test_src, "<ai_tests>", "exec")
    # the test calls the scoped helper + provenance symbol, NOT the source-bound helper…
    assert "_persist_scoped(" in test_src
    assert "mod._PROVENANCE_FIELD" in test_src
    assert "_persist_source(" not in test_src
    # …and the helper/symbol it calls are exactly the ones the harness defines (no mismatch).
    assert "def _persist_scoped(" in harness and "_PROVENANCE_FIELD =" in harness


def test_scoped_generated_test_runs_green_against_harness(tmp_path):
    """End-to-end: generate the backend for a scoped pass, then run its GENERATED test_ai_passes.py.
    Pre-fix this failed (NameError: _persist_source) — the red gate. Post-fix it must pass."""
    import os
    import subprocess
    import sys

    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_ai_passes.py",
         "-q", "-k", "scoped", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"generated scoped test failed:\n{r.stdout}\n{r.stderr}"
