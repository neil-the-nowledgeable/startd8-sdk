"""End-to-end HTTP verification of the source-bound extraction ROUTE (FR-IMP-4/5).

The spike (SOURCE_BOUND_EXTRACTION_SPIKE_FINDINGS.md §7) exercised the generated harness directly
against real SQLModel, but NOT the FastAPI route — so the H-INT router wiring (the `_Request.source_id`
field + `body.source_id` threading) was inspected, never executed. This closes that gap.

Boots the generated AI layer for real (needs fastapi/sqlmodel) for a ProofPoint-like entity whose
`sourceDocumentId` loose-ref field is auto-DERIVED as the provenance binding (no `source_binding:`
key anywhere), with the SDK agent mocked. It then proves, over a live TestClient:
  * POST {"text": ..., "source_id": "doc-A"}  → a stamped row (sourceDocumentId == "doc-A",
    source == "ai", confirmed is False);
  * a second identical POST is idempotent-by-source (the prior UNCONFIRMED row is replaced, not
    duplicated — still exactly one unconfirmed row for doc-A);
  * a hand-CONFIRMED row of the same source survives both runs (clear-prior touches unconfirmed only).

Mirrors test_ai_layer_runtime.py: same render_backend boot, same agent mock, same shared-metadata
table hygiene (SQLModel registers tables on a process-global MetaData that sys.modules purge can't
unregister).
"""

import importlib
import sys

import pytest

pytest.importorskip("fastapi")
sqlmodel = pytest.importorskip("sqlmodel")

from startd8.backend_codegen import render_backend  # noqa: E402

# Drop the tables this test owns from the shared metadata at start + teardown (scoped — never
# touches other suites' models). See test_ai_layer_runtime.py for the rationale.
_MY_TABLES = {"proofpoint", "aicall"}


def _drop_my_tables() -> None:
    md = sqlmodel.SQLModel.metadata
    for name in list(_MY_TABLES):
        table = md.tables.get(name)
        if table is not None:
            md.remove(table)


# ProofPoint carries a server-managed loose-ref field (`sourceDocumentId`: optional String, not PK,
# human-owned) — the exact shape that DERIVES a source binding with zero `source_binding:` config.
SCHEMA = """
model ProofPoint {
  id               String  @id @default(cuid())
  ownerId          String  @default("local")
  source           String  @default("user")
  confirmed        Boolean @default(false)
  title            String?
  sourceDocumentId String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

# Text-mode pass (no input_entities) → free-text → single output entity. No `source_binding:` key:
# the binding is DERIVED from the loose-ref field + human_inputs marking below.
MANIFEST = """
passes:
  - name: extract_points
    output_entities: [ProofPoint]
    route_path: /extract-points
    prompt: prompts/extract_points.md
""".strip()

# Mark the loose-ref field human-owned — the third derivation fact (keeps it out of the edge schema
# AND tags it as the server-managed provenance target).
HUMAN = (
    "fields:\n"
    "  - target: ProofPoint.sourceDocumentId\n"
    "    authored_by: human\n"
)


def _purge_app():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_bound_route_stamps_and_is_idempotent_by_source(tmp_path, monkeypatch):
    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # Sanity: the generated harness is the BOUND shape (3-arg signature, _persist_source) and the
    # router threads body.source_id via the _Request.source_id field — derived, not authored.
    pass_src = (tmp_path / "app/ai/extract_points.py").read_text(encoding="utf-8")
    routes_src = (tmp_path / "app/ai/routes.py").read_text(encoding="utf-8")
    assert "def extract_points(text: str, session: Session, source_id: str)" in pass_src
    assert "_persist_source" in pass_src
    assert 'source_id: str | None = None' in routes_src
    assert "source_id=body.source_id" in routes_src

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    # Dummy key to clear the route's keyless precheck (FR-23); the agent is mocked below, so no real
    # call is made — the test runs fully offline. Without this the route returns 503 before the mock.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sys.path.insert(0, str(tmp_path))
    _purge_app()
    _drop_my_tables()  # defensive: clear any leftovers from a prior table-defining test
    try:
        importlib.import_module("app.main")
        server = importlib.import_module("app.server")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        ai_service = importlib.import_module("app.ai.service")  # binds resolve_agent_spec
        from fastapi.testclient import TestClient
        from sqlmodel import Session, select
        from startd8.models import GenerateResult

        # Mock the SDK agent: generate_structured returns one ProofPointEdge-shaped result. The edge
        # schema omits the human-owned sourceDocumentId, so the AI never authors provenance — the
        # harness stamps it from source_id.
        class _FakeAgent:
            def generate_structured(self, prompt, output_schema, **kw):
                value = output_schema(title="Led a 12-person team")
                return value, GenerateResult("{}", 1, None)

        monkeypatch.setattr(ai_service, "resolve_agent_spec", lambda *a, **k: _FakeAgent())

        with TestClient(server.app) as c:
            # A hand-CONFIRMED row of the same source — must survive every re-run (clear-prior is
            # UNCONFIRMED-only).
            with Session(db.engine) as s:
                s.add(tables.ProofPoint(
                    title="hand-entered", sourceDocumentId="doc-A",
                    source="user", confirmed=True,
                ))
                s.commit()

            # Run 1: stamps a fresh AI row for doc-A.
            r1 = c.post("/ai/extract-points", json={"text": "resume text", "source_id": "doc-A"})
            assert r1.status_code == 200, r1.text
            assert r1.json()["created"] == {"ProofPoint": 1}

            with Session(db.engine) as s:
                rows = s.exec(select(tables.ProofPoint)).all()
            ai_rows = [r for r in rows if r.source == "ai"]
            assert len(ai_rows) == 1
            stamped = ai_rows[0]
            assert stamped.sourceDocumentId == "doc-A"   # server-stamped provenance (FR-IMP-5)
            assert stamped.source == "ai"
            assert stamped.confirmed is False

            # Run 2: same source_id — idempotent. The prior UNCONFIRMED ai row is replaced, not
            # appended, so there is still exactly one unconfirmed ai row for doc-A.
            r2 = c.post("/ai/extract-points", json={"text": "resume text again", "source_id": "doc-A"})
            assert r2.status_code == 200, r2.text
            assert r2.json()["created"] == {"ProofPoint": 1}

            with Session(db.engine) as s:
                rows = s.exec(select(tables.ProofPoint)).all()
            ai_unconfirmed = [r for r in rows if r.source == "ai" and r.confirmed is False
                              and r.sourceDocumentId == "doc-A"]
            assert len(ai_unconfirmed) == 1  # idempotent by source: no duplicate unconfirmed row

            # The hand-confirmed row of the same source survived both runs untouched.
            confirmed = [r for r in rows if r.confirmed is True and r.sourceDocumentId == "doc-A"]
            assert len(confirmed) == 1
            assert confirmed[0].source == "user"
            assert confirmed[0].title == "hand-entered"
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app()
        _drop_my_tables()  # leave the shared metadata clean for the next table-defining test
