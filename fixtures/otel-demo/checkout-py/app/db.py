# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-db
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

from sqlalchemy import event, inspect as _sa_inspect
from sqlmodel import Session, SQLModel, create_engine

from . import tables  # noqa: F401  (import registers tables on SQLModel.metadata)

try:  # deployed mode emits app/settings.py (mode-aware DB url/pool/gate); absent = installed.
    from . import settings as _settings
except ImportError:  # installed: today's local-first SQLite behavior (no settings module).
    #   ImportError (not just ModuleNotFoundError): `from . import settings` against an empty
    #   app/__init__.py can surface as 'cannot import name settings' — catch the parent class.
    _settings = None

if _settings is not None:
    # Deployed: connection string + pooled engine from the mode-aware settings (FR-PER-2/FR-CON-1).
    DATABASE_URL = _settings.database_url()
    engine = create_engine(DATABASE_URL, echo=False, **_settings.engine_options())
else:
    # Installed default (NFR-1): local-first SQLite; override with the DATABASE_URL env var.
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
    engine = create_engine(DATABASE_URL, echo=False)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
        # WAL + busy_timeout: avoid 'database is locked' under async HTMX bursts (R3-S2).
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


def init_db() -> None:
    # FR-CFG-4: in deployed mode, refuse to start if the runtime env claims a mode this app
    # was NOT generated for (directional fail-closed); a no-op in installed mode.
    if _settings is not None:
        _settings.validate_runtime_mode()
    # Dev/test bootstrap ONLY: create_all makes MISSING tables but never ALTERS an existing
    # one. On a persistent DB a contract field-add silently diverges until a query 500s, so
    # after create_all we reflect and warn loudly on drift (the 'migration pending' signal).
    # FR-PER-3: installed bootstraps via create_all; deployed relies on managed migrations
    # (should_create_all() is False) and never auto-creates against a shared DB.
    if _settings is None or _settings.should_create_all():
        SQLModel.metadata.create_all(engine)
    _warn_on_schema_drift()


def _warn_on_schema_drift() -> None:
    """Loud warning when the live DB is missing contract columns (run `alembic upgrade head`)."""
    try:
        insp = _sa_inspect(engine)
        existing = set(insp.get_table_names())
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing:
                continue  # create_all just made it — no drift
            db_cols = {c['name'] for c in insp.get_columns(table.name)}
            missing = sorted(c.name for c in table.columns if c.name not in db_cols)
            if missing:
                logging.getLogger('app.db').warning(
                    'schema drift: table %r is missing contract column(s) %s — a migration is '
                    'pending (create_all never ALTERs; run `alembic upgrade head`).',
                    table.name, ', '.join(missing),
                )
    except Exception:  # a drift check must never break boot
        logging.getLogger('app.db').debug('schema-drift check skipped', exc_info=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
