"""H1 runtime verification — the generated read-mode harness actually reads + persists.

Boots the generated AI layer for real (needs fastapi/sqlmodel) and exercises a read-mode pass with
the SDK agent mocked (no live call): seed a confirmed ProofPoint → POST /ai/caps → assert Capability
+ Outcome persisted source="ai", confirmed=False. Validates the harness body against real SQLModel:
`select(...).where(confirmed.is_(True))`, `_summary`, `call_ai_service`, the per-item savepoint, and
`_persist` (incl. the dedup + provenance stamping) — the parts compile-checks can't reach.
"""

import importlib
import sys

import pytest

pytest.importorskip("fastapi")
sqlmodel = pytest.importorskip("sqlmodel")

from startd8.backend_codegen import render_backend  # noqa: E402

# SQLModel registers tables on a process-global MetaData; purging sys.modules does NOT unregister
# them. Two runtime tests each defining e.g. `proofpoint` would collide. Drop the tables this test
# owns from the shared metadata at start + teardown (scoped — never touches other suites' models).
_MY_TABLES = {"proofpoint", "capability", "outcome", "aicall"}


def _drop_my_tables() -> None:
    md = sqlmodel.SQLModel.metadata
    for name in list(_MY_TABLES):
        table = md.tables.get(name)
        if table is not None:
            md.remove(table)

SCHEMA = """
model ProofPoint {
  id          String  @id @default(cuid())
  ownerId     String  @default("local")
  source      String  @default("user")
  confirmed   Boolean @default(true)
  title       String?
  description String?
}

model Capability {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  name      String?
  category  String?
}

model Outcome {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  name      String?
  category  String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

MANIFEST = """
passes:
  - name: suggest_caps
    input_entities: [ProofPoint]
    output_entities: [Capability, Outcome]
    route_path: /caps
    prompt: prompts/caps.md
""".strip()


def _purge_app():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_read_mode_pass_reads_inputs_and_persists(tmp_path, monkeypatch):
    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

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

        # Mock the SDK agent: generate_structured returns a validated Result with one cap + one outcome.
        class _FakeAgent:
            def generate_structured(self, prompt, output_schema, **kw):
                value = output_schema(
                    capabilities=[{"name": "Leadership", "category": "soft"}],
                    outcomes=[{"name": "Revenue growth", "category": "business"}],
                )
                return value, GenerateResult("{}", 1, None)

        monkeypatch.setattr(ai_service, "resolve_agent_spec", lambda *a, **k: _FakeAgent())

        with TestClient(server.app) as c:
            # init_db ran via lifespan; seed a CONFIRMED ProofPoint directly on the engine.
            with Session(db.engine) as s:
                s.add(tables.ProofPoint(title="Led a 12-person team", description="delivered $2M"))
                s.commit()

            resp = c.post("/ai/caps")
            assert resp.status_code == 200, resp.text
            assert resp.json()["created"] == {"Capability": 1, "Outcome": 1}

            # rows persisted with AI provenance
            with Session(db.engine) as s:
                caps = s.exec(select(tables.Capability)).all()
                outs = s.exec(select(tables.Outcome)).all()
            assert len(caps) == 1 and caps[0].name == "Leadership"
            assert caps[0].source == "ai" and caps[0].confirmed is False
            assert len(outs) == 1 and outs[0].source == "ai" and outs[0].confirmed is False
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app()
        _drop_my_tables()  # leave the shared metadata clean for the next table-defining test


def test_provider_error_at_call_time_degrades_to_503(tmp_path, monkeypatch):
    """SDK_QUICK_WINS #1 / FR-40: a key present-but-invalid (or rate-limit/network) error raised
    DURING the provider call degrades to a polite 503, not a 500 crash — the runtime sibling of the
    keyless-boot test. Regression for the unwrapped `generate_structured` call in `call_ai_service`.
    """
    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-invalid")  # key PRESENT → past the keyless precheck
    sys.path.insert(0, str(tmp_path))
    _purge_app()
    _drop_my_tables()
    try:
        importlib.import_module("app.main")
        server = importlib.import_module("app.server")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        ai_service = importlib.import_module("app.ai.service")
        from fastapi.testclient import TestClient
        from sqlmodel import Session

        # Mock the SDK agent so the CALL raises a provider-style error (the 401/429/network class).
        class _ExplodingAgent:
            def generate_structured(self, prompt, output_schema, **kw):
                raise RuntimeError("AuthenticationError: 401 invalid x-api-key")

        monkeypatch.setattr(ai_service, "resolve_agent_spec", lambda *a, **k: _ExplodingAgent())

        with TestClient(server.app) as c:
            with Session(db.engine) as s:
                s.add(tables.ProofPoint(title="Led a 12-person team", description="delivered $2M"))
                s.commit()
            resp = c.post("/ai/caps")
            assert resp.status_code == 503, resp.text   # polite no, not a 500 crash
            assert resp.status_code != 500
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app()
        _drop_my_tables()
