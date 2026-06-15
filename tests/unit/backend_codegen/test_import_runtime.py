"""Phase 3 — FR-IMP-1 ``from_json`` importer, exercised against real SQLModel (importorskip).

Generates the full backend (with imports.yaml) to a temp project, then drives the generated
``app/importer.py`` against an in-memory SQLite DB. Validates the import-unique semantics the static
checks can't: round-trip restore, id-upsert idempotency, confirmed-row non-clobber, FK ordering,
type coercion (DateTime/Int back from ``default=str``), and strict-vs-allow-lossy atomicity.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("fastapi")

from startd8.backend_codegen import render_backend  # noqa: E402

pytestmark = pytest.mark.unit

SCHEMA = """\
model Capability {
  id        String   @id
  ownerId   String   @default("local")
  source    String   @default("user")
  confirmed Boolean  @default(false)
  name      String?
  weight    Int?
  createdAt DateTime @default(now())
}

model Outcome {
  id           String  @id
  ownerId      String  @default("local")
  source       String  @default("user")
  confirmed    Boolean @default(false)
  label        String?
  capabilityId String?
  capability   Capability? @relation(fields: [capabilityId], references: [id])
}
"""

IMPORTS = """\
imports:
  Capability:
    format: json
    identity: id
  Outcome:
    format: json
    identity: id
"""


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


@pytest.fixture(scope="module")
def _generated_app(tmp_path_factory):
    """Generate + import the app ONCE (SQLModel registers tables on the global metadata, so a
    per-test re-import would clash). Each test gets a fresh engine over the same metadata."""
    root = tmp_path_factory.mktemp("import_app")
    for rel, content in render_backend(SCHEMA, imports_text=IMPORTS):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    sys.path.insert(0, str(root))
    _purge_app_modules()
    tables = importlib.import_module("app.tables")
    importer = importlib.import_module("app.importer")
    export = importlib.import_module("app.export")
    try:
        yield tables, importer, export
    finally:
        sys.path.remove(str(root))
        _purge_app_modules()


@pytest.fixture()
def app_modules(_generated_app):
    """A fresh in-memory DB per test over the once-registered metadata."""
    from sqlmodel import SQLModel, Session, create_engine

    tables, importer, export = _generated_app
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        yield tables, importer, export, engine, Session
    finally:
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def test_importer_emitted_and_imports(app_modules):
    tables, importer, export, engine, Session = app_modules
    assert hasattr(importer, "from_json")
    assert hasattr(importer, "ImportResult")
    # FK order baked parent-before-child
    assert importer.IMPORT_ORDER.index("Capability") < importer.IMPORT_ORDER.index("Outcome")


def test_round_trip_restore(app_modules):
    tables, importer, export, engine, Session = app_modules
    payload = {
        "Capability": [{"id": "c1", "name": "Ship", "weight": 3}],
        "Outcome": [{"id": "o1", "label": "Faster", "capabilityId": "c1"}],
    }
    import json

    with Session(engine) as s:
        result = importer.from_json(json.dumps(payload), s)
        assert result.ok, result.errors
        assert result.created == 2
    # re-export and compare the meaningful fields survived
    with Session(engine) as s:
        from sqlmodel import select

        cap = s.exec(select(tables.Capability)).first()
        out = s.exec(select(tables.Outcome)).first()
        assert cap.name == "Ship" and cap.weight == 3
        assert out.capabilityId == "c1"


def test_id_upsert_is_idempotent(app_modules):
    tables, importer, export, engine, Session = app_modules
    import json
    from sqlmodel import select

    payload = {"Capability": [{"id": "c1", "name": "Ship", "weight": 1}]}
    with Session(engine) as s:
        importer.from_json(json.dumps(payload), s)
    # second import with a changed field → update, not duplicate
    payload["Capability"][0]["weight"] = 9
    with Session(engine) as s:
        r = importer.from_json(json.dumps(payload), s)
        assert r.updated == 1 and r.created == 0
    with Session(engine) as s:
        caps = s.exec(select(tables.Capability)).all()
        assert len(caps) == 1 and caps[0].weight == 9


def test_confirmed_row_not_clobbered(app_modules):
    tables, importer, export, engine, Session = app_modules
    import json
    from sqlmodel import select

    with Session(engine) as s:
        s.add(tables.Capability(id="c1", name="UserEdited", confirmed=True, weight=5))
        s.commit()
    # import tries to overwrite the confirmed row → skipped, value preserved
    payload = {"Capability": [{"id": "c1", "name": "ImportWins", "weight": 99}]}
    with Session(engine) as s:
        r = importer.from_json(json.dumps(payload), s)
        assert r.skipped == 1 and r.updated == 0
    with Session(engine) as s:
        cap = s.exec(select(tables.Capability)).first()
        assert cap.name == "UserEdited" and cap.weight == 5


def test_type_coercion_int_and_datetime(app_modules):
    tables, importer, export, engine, Session = app_modules
    import json
    from datetime import datetime
    from sqlmodel import select

    # weight arrives as a STRING (hand-edited payload); createdAt as an ISO string (default=str export)
    payload = {
        "Capability": [
            {"id": "c1", "name": "X", "weight": "7", "createdAt": "2026-06-15T12:00:00"}
        ]
    }
    with Session(engine) as s:
        r = importer.from_json(json.dumps(payload), s)
        assert r.ok, r.errors
    with Session(engine) as s:
        cap = s.exec(select(tables.Capability)).first()
        assert cap.weight == 7 and isinstance(cap.weight, int)
        assert isinstance(cap.createdAt, datetime)


def test_strict_atomic_rollback_on_bad_row(app_modules):
    tables, importer, export, engine, Session = app_modules
    import json
    from sqlmodel import select

    # second Capability has an uncoercible weight → strict aborts the WHOLE file (nothing persists)
    payload = {
        "Capability": [
            {"id": "c1", "name": "Good", "weight": 1},
            {"id": "c2", "name": "Bad", "weight": "not-a-number"},
        ]
    }
    with Session(engine) as s:
        r = importer.from_json(json.dumps(payload), s, strict=True)
        assert not r.ok and r.errors
    with Session(engine) as s:
        assert s.exec(select(tables.Capability)).all() == []  # full rollback


def test_allow_lossy_skips_bad_row(app_modules):
    tables, importer, export, engine, Session = app_modules
    import json
    from sqlmodel import select

    payload = {
        "Capability": [
            {"id": "c1", "name": "Good", "weight": 1},
            {"id": "c2", "name": "Bad", "weight": "not-a-number"},
        ]
    }
    with Session(engine) as s:
        r = importer.from_json(json.dumps(payload), s, strict=False)
        assert r.created == 1 and len(r.errors) == 1
    with Session(engine) as s:
        caps = s.exec(select(tables.Capability)).all()
        assert len(caps) == 1 and caps[0].id == "c1"


def test_invalid_json_is_structured_error(app_modules):
    tables, importer, export, engine, Session = app_modules
    with Session(engine) as s:
        r = importer.from_json("{not json", s)
        assert not r.ok and "invalid JSON" in r.errors[0]
