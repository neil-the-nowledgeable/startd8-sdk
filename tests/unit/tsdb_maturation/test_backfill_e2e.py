"""M5 E2E backfill dedup proof (R1-S3) — the load-bearing FR-8/FR-14 integration.

Drives the FULL real path: infer → generate imports.yaml (M3) → render_backend → run the generated
``from_json`` importer against an in-memory SQLite DB TWICE, asserting the second run creates **0 new
rows** (it dedups on the inferred composite identity, not on ``id`` — which TSDB rows lack). This is
the proof CRP_FOCUS #2 demanded: *not* merely that ``parse_imports`` accepts the manifest, but that
the generated importer actually dedups on the inferred key.
"""

from __future__ import annotations

import importlib
import sys
from itertools import product

import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("fastapi")

from startd8.backend_codegen import render_backend  # noqa: E402
from startd8.tsdb_maturation import (  # noqa: E402
    ReadResult,
    Series,
    Specimen,
    generate_imports_yaml,
    infer_schema,
    records_to_json,
)

pytestmark = pytest.mark.unit

ENTITY = "DepartmentBudget"
METRIC = "gov_expenditure_amount"


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def _michigan_specimen():
    series, v = [], 1_000_000.0
    for dept, fy, status, fund in product(
        ["corrections", "health"], ["2025", "2026"], ["enacted", "proposed"], ["general", "federal"]
    ):
        labels = {
            "department": dept, "fiscal_year": fy, "budget_status": status,
            "fund_source": fund, "source": "hfa_mi",
        }
        series.append(Series(labels=labels, value=round(v, 2), timestamp=1_700_000_000.0))
        v += 1000.0
    return Specimen.from_read_result(ReadResult(metric=METRIC, lookback="3000d", series=tuple(series)))


@pytest.fixture(scope="module")
def _generated(tmp_path_factory):
    """Infer → imports.yaml → render_backend → import the generated app once."""
    import os

    spec = _michigan_specimen()
    result = infer_schema(spec, entity_name=ENTITY)
    imports_text = generate_imports_yaml([result])
    payload_text, _built = records_to_json(spec, result, metric=METRIC)

    root = tmp_path_factory.mktemp("tsdb_backfill_app")
    for rel, content in render_backend(result.schema_text, imports_text=imports_text):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    sys.path.insert(0, str(root))
    _purge_app_modules()
    os.environ["DATABASE_URL"] = f"sqlite:///{root/'app.db'}"
    try:
        tables = importlib.import_module("app.tables")
        importer = importlib.import_module("app.importer")
        yield tables, importer, payload_text, result
    finally:
        sys.path.remove(str(root))
        _purge_app_modules()
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture()
def app_db(_generated):
    from sqlmodel import SQLModel, Session, create_engine

    tables, importer, payload_text, result = _generated
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        yield tables, importer, payload_text, result, engine, Session
    finally:
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def test_importer_bakes_composite_identity(_generated):
    _tables, importer, _payload, _res = _generated
    ident = importer._IDENTITY[ENTITY]
    # The whole FR-14 point: dedup on the inferred composite, NOT the default `id`.
    assert ident["kind"] == "composite"
    assert set(ident["fields"]) == {"department", "fiscalYear", "budgetStatus", "fundSource"}


def test_first_backfill_creates_all_rows(app_db):
    _tables, importer, payload_text, _res, engine, Session = app_db
    with Session(engine) as s:
        result = importer.from_json(payload_text, s)
        assert result.ok, result.errors
        assert result.created == 16  # 2*2*2*2 series
        assert result.updated == 0


def test_re_run_backfill_creates_zero_new_rows(app_db):
    """R1-S3: re-run the SAME payload twice → 0 new rows (idempotent upsert on the inferred key).

    Every row matches its identity twin on the second pass (created == 0). They are *skipped* rather
    than updated because the emitter's bookkeeping ``confirmed`` defaults to ``true`` and the importer
    never clobbers a confirmed row (FR-8 parity) — even safer than update. The load-bearing invariant
    is unchanged: no infinite duplication, table size stable.
    """
    _tables, importer, payload_text, _res, engine, Session = app_db
    with Session(engine) as s:
        importer.from_json(payload_text, s)
    with Session(engine) as s:
        second = importer.from_json(payload_text, s)
        assert second.ok, second.errors
        assert second.created == 0                    # <-- no infinite duplication
        assert second.updated + second.skipped == 16  # every row matched its identity twin

    from sqlmodel import select

    with Session(engine) as s:
        rows = s.exec(select(_tables.DepartmentBudget)).all()
        assert len(rows) == 16            # table size stable after two backfills


def test_decimal_and_datetime_coerced_back(app_db):
    _tables, importer, payload_text, _res, engine, Session = app_db
    from decimal import Decimal
    from datetime import datetime

    from sqlmodel import select

    with Session(engine) as s:
        importer.from_json(payload_text, s)
    with Session(engine) as s:
        row = s.exec(select(_tables.DepartmentBudget)).first()
        assert isinstance(row.amount, Decimal)          # Decimal round-trips (financial fidelity)
        assert isinstance(row.observedAt, datetime)     # DateTime coerced from the ISO string
        assert row.dataSource == "hfa_mi"               # renamed label value preserved
