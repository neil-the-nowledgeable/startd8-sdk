"""Deterministic FastAPI CRUD + app-spine generation (Python contract-codegen, Step 4 / FR-3, FR-11).

Projects the ``.prisma`` contract into the owned FastAPI spine, alongside the Step 1 Pydantic models
and Step 2 SQLModel tables:

- ``routers.py`` — one ``APIRouter`` per entity with list / detail / create / update / delete
  handlers (validate via the SQLModel class → session op → response), gathered into ``all_routers``.
- ``db.py`` — the SQLite engine + ``get_session`` dependency + ``init_db`` (near-static plumbing).
- ``main.py`` — the ``FastAPI`` app, wired to ``init_db`` on startup and every router included.

**Canonical layout (FR-11):** all files live in one ``app/`` package, so the generated imports
(``from .db import get_session``, ``from .tables import X``, ``from .routers import all_routers``)
resolve by construction — the Step 3 build gate fails on any invented path.

**OQ-3 (v1):** the SQLModel table class is used directly as the request body + response. The
``Create``/``Read`` DTO split (to hide server-set fields like ``id`` on create) is the deferred
refinement. Detail/update/delete are emitted only for entities with a single-column primary key
(``@id``); a keyless entity (e.g. a relation-only join model) gets list + create only.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header  # shared provenance header (one source of truth)
from .pydantic_renderer import _PY_SCALAR

# Canonical generated layout: artifact-kind -> path relative to the project root (FR-11).
CANONICAL_LAYOUT: Dict[str, str] = {
    "pydantic-models": "app/models.py",
    "sqlmodel-tables": "app/tables.py",
    "fastapi-routers": "app/routers.py",
    "fastapi-db": "app/db.py",
    "fastapi-main": "app/main.py",
    "fastapi-web": "app/web.py",
    "python-export": "app/export.py",
    "python-ai-schemas": "app/ai_schemas.py",
    "python-completeness": "app/completeness.py",
    "python-requirements": "requirements.txt",
    "python-settings": "app/settings.py",  # deployed-only (FR-CFG-7); the single mode-varying file
}




def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _pk_field(schema: PrismaSchema, name: str) -> Optional[PrismaField]:
    """The single-column primary key for an entity: prefer ``@id``, else a single ``@unique``."""
    scalars = schema.scalar_fields(name)
    for f in scalars:
        if f.is_id:
            return f
    uniques = [f for f in scalars if f.is_unique]
    return uniques[0] if len(uniques) == 1 else None


_LIST_CREATE = """\
{rname} = APIRouter(prefix="/{prefix}", tags=["{prefix}"])


@{rname}.get("/")
def list_{prefix}(session: Session = Depends(get_session)) -> list[{name}Read]:
    return list(session.exec(select({name})).all())


@{rname}.post("/")
def create_{prefix}(item: {name}Create, session: Session = Depends(get_session)) -> {name}Read:
    obj = {name}(**item.model_dump())
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj"""


_BY_PK = """


@{rname}.get("/{{item_id}}")
def get_{prefix}(item_id: {pktype}, session: Session = Depends(get_session)) -> {name}Read:
    obj = session.get({name}, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="{name} not found")
    return obj


@{rname}.patch("/{{item_id}}")
def update_{prefix}(
    item_id: {pktype}, data: {name}Update, session: Session = Depends(get_session)
) -> {name}Read:
    obj = session.get({name}, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="{name} not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@{rname}.delete("/{{item_id}}")
def delete_{prefix}(item_id: {pktype}, session: Session = Depends(get_session)) -> dict:
    obj = session.get({name}, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="{name} not found")
    session.delete(obj)
    session.commit()
    return {{"ok": True}}"""


def _entity_block(schema: PrismaSchema, name: str) -> str:
    prefix = name.lower()
    rname = f"{prefix}_router"
    block = _LIST_CREATE.format(rname=rname, prefix=prefix, name=name)
    pk = _pk_field(schema, name)
    if pk is not None:
        pktype = _PY_SCALAR.get(pk.type, "str")
        block += _BY_PK.format(rname=rname, prefix=prefix, name=name, pktype=pktype)
    return block


def render_routers(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/routers.py`` — one APIRouter per entity, gathered into ``all_routers``."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    header = _header(source_file, sha, "fastapi-routers")
    imports = (
        "from __future__ import annotations\n\n"
        "from fastapi import APIRouter, Depends, HTTPException\n"
        "from sqlmodel import Session, select\n\n"
        "from .db import get_session\n"
    )
    if names:
        imported: List[str] = []
        for n in names:
            imported += [n, f"{n}Create", f"{n}Read"]
            if _pk_field(schema, n) is not None:
                imported.append(f"{n}Update")  # only by-id PATCH uses the Update DTO
        imports += "from .tables import " + ", ".join(sorted(set(imported))) + "\n"

    blocks = [_entity_block(schema, n) for n in names]
    all_routers = (
        "all_routers = [" + ", ".join(f"{n.lower()}_router" for n in names) + "]"
    )

    body_parts = ["\n\n\n".join(blocks)] if blocks else []
    body_parts.append(all_routers)
    body = "\n\n\n".join(body_parts)

    return header + "\n\n" + imports + "\n\n" + body + "\n"


def render_db(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/db.py`` — SQLite engine, ``get_session`` dependency, ``init_db`` (NFR-1 local)."""
    sha = schema_sha256(schema_text)
    header = _header(source_file, sha, "fastapi-db")
    body = (
        "from __future__ import annotations\n\n"
        "import logging\n"
        "import os\n"
        "from collections.abc import Iterator\n\n"
        "from sqlalchemy import event, inspect as _sa_inspect\n"
        "from sqlmodel import Session, SQLModel, create_engine\n\n"
        "from . import tables  # noqa: F401  (import registers tables on SQLModel.metadata)\n\n"
        "# Local-first SQLite (NFR-1); override with the DATABASE_URL env var.\n"
        'DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")\n'
        "engine = create_engine(DATABASE_URL, echo=False)\n\n\n"
        "if engine.dialect.name == \"sqlite\":\n\n"
        "    @event.listens_for(engine, \"connect\")\n"
        "    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001\n"
        "        # WAL + busy_timeout: avoid 'database is locked' under async HTMX bursts (R3-S2).\n"
        "        cursor = dbapi_connection.cursor()\n"
        "        cursor.execute(\"PRAGMA journal_mode=WAL;\")\n"
        "        cursor.execute(\"PRAGMA busy_timeout=5000;\")\n"
        "        cursor.close()\n\n\n"
        "def init_db() -> None:\n"
        "    # Dev/test bootstrap ONLY: create_all makes MISSING tables but never ALTERS an existing\n"
        "    # one. On a persistent DB a contract field-add silently diverges until a query 500s, so\n"
        "    # after create_all we reflect and warn loudly on drift (the 'migration pending' signal).\n"
        "    SQLModel.metadata.create_all(engine)\n"
        "    _warn_on_schema_drift()\n\n\n"
        "def _warn_on_schema_drift() -> None:\n"
        "    \"\"\"Loud warning when the live DB is missing contract columns (run `alembic upgrade head`).\"\"\"\n"
        "    try:\n"
        "        insp = _sa_inspect(engine)\n"
        "        existing = set(insp.get_table_names())\n"
        "        for table in SQLModel.metadata.sorted_tables:\n"
        "            if table.name not in existing:\n"
        "                continue  # create_all just made it — no drift\n"
        "            db_cols = {c['name'] for c in insp.get_columns(table.name)}\n"
        "            missing = sorted(c.name for c in table.columns if c.name not in db_cols)\n"
        "            if missing:\n"
        "                logging.getLogger('app.db').warning(\n"
        "                    'schema drift: table %r is missing contract column(s) %s — a migration is '\n"
        "                    'pending (create_all never ALTERs; run `alembic upgrade head`).',\n"
        "                    table.name, ', '.join(missing),\n"
        "                )\n"
        "    except Exception:  # a drift check must never break boot\n"
        "        logging.getLogger('app.db').debug('schema-drift check skipped', exc_info=True)\n\n\n"
        "def get_session() -> Iterator[Session]:\n"
        "    with Session(engine) as session:\n"
        "        yield session\n"
    )
    return header + "\n\n" + body


def render_main(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/main.py`` — the FastAPI app, init_db on startup, JSON + HTML routers mounted.

    Content pages are an optional layer: ``app/pages.py`` is emitted only by
    ``generate backend --pages``. The mount below is **tolerant** (present in every app, a no-op when
    ``app/pages.py`` is absent) so ``main.py`` stays a single deterministic, schema-only artifact —
    no pages-awareness leaks into its drift hash.

    The same tolerant shape gives projects a **regen-safe composition seam** for their own routers:
    ``main.py`` always imports an optional, project-**owned** ``app/user_routers.py`` (a list named
    ``user_routers``) that the generator never writes. Owned routers/views mounted via that list
    therefore survive ``generate backend`` — no hand-edit of this generated file is needed or kept."""
    sha = schema_sha256(schema_text)
    header = _header(source_file, sha, "fastapi-main")
    body = (
        "from __future__ import annotations\n\n"
        "from contextlib import asynccontextmanager\n\n"
        "from fastapi import FastAPI\n\n"
        "# Secrets hydration (FR-GEN-1..3): populate os.environ from the configured backend\n"
        "# (e.g. Doppler, via ~/.startd8/config.json) BEFORE any import that reads env. The db\n"
        "# module reads DATABASE_URL at import time, so this runs before that import below.\n"
        "# Fully guarded: a no-op when startd8 isn't installed or the backend is 'local', and\n"
        "# fail-open if the backend is unreachable — the app runs identically either way.\n"
        "try:  # optional managed-secrets hydration (startd8.secrets); no-op for the 'local' backend\n"
        "    from startd8.secrets import hydrate as _hydrate_secrets\n"
        "    _hydrate_secrets()\n"
        "except Exception:\n"
        "    pass\n\n"
        "from .db import init_db\n"
        "from .routers import all_routers\n"
        "from .web import web_router\n\n\n"
        "@asynccontextmanager\n"
        "async def lifespan(app: FastAPI):\n"
        "    init_db()\n"
        "    yield\n\n\n"
        'app = FastAPI(title="StartDate", lifespan=lifespan)\n\n'
        "for _router in all_routers:\n"
        "    app.include_router(_router)\n"
        "app.include_router(web_router)  # server-rendered HTMX UI at /ui/*\n\n"
        "try:  # optional presentation-polish static mount (startd8 polish); no-op until polish runs\n"
        "    from .static_setup import mount_static\n"
        "except ModuleNotFoundError:\n"
        "    mount_static = None\n"
        "if mount_static is not None:\n"
        "    mount_static(app)  # serves /static/* (e.g. the polished stylesheet) when present\n\n"
        "try:  # optional OWNED routers — the regen-safe composition seam (D2).\n"
        "    from .user_routers import user_routers  # project-authored list; never generated\n"
        "except ModuleNotFoundError:\n"
        "    user_routers = []\n"
        "for _user_router in user_routers:\n"
        "    app.include_router(_user_router)  # owned routers/views survive regenerate\n\n"
        "try:  # optional content-pages layer (generate backend --pages)\n"
        "    from .pages import pages_router\n"
        "except ModuleNotFoundError:\n"
        "    pages_router = None\n"
        "if pages_router is not None:\n"
        "    app.include_router(pages_router)  # home / and content slugs\n\n"
        "try:  # optional page-authoring UI (generate backend --pages-authoring)\n"
        "    from .pages_admin import pages_admin_router\n"
        "except ModuleNotFoundError:\n"
        "    pages_admin_router = None\n"
        "if pages_admin_router is not None:\n"
        "    app.include_router(pages_admin_router)  # /ui/pages authoring screens\n\n"
        "try:  # optional AI layer (generate backend --ai-passes); /ai/* one POST per pass (F-9)\n"
        "    from .ai.routes import ai_router\n"
        "except ModuleNotFoundError:\n"
        "    ai_router = None\n"
        "if ai_router is not None:\n"
        "    app.include_router(ai_router)  # AI passes reachable at /ai/* via app.main\n"
        "try:  # optional AI-pass UI triggers (ai_passes.yaml `trigger:`); detail-page buttons (FR-AIT)\n"
        "    from .ai.ui import ai_ui_router\n"
        "except ModuleNotFoundError:\n"
        "    ai_ui_router = None\n"
        "if ai_ui_router is not None:\n"
        "    app.include_router(ai_ui_router)  # POST /ui/<entity>/{id}/run-<pass>\n"
        "try:  # optional step-state flows (views.yaml `flows:`); /flow/<name>/* (FR-WZ-5)\n"
        "    from .flows import flow_routers\n"
        "except ModuleNotFoundError:\n"
        "    flow_routers = []\n"
        "for _flow_router in flow_routers:\n"
        "    app.include_router(_flow_router)  # start/resume/advance/back\n"
        "try:  # optional bulk child-field editors (views.yaml `editors:`); <route> per editor (FR-ED-8)\n"
        "    from .editors import editor_routers\n"
        "except ModuleNotFoundError:\n"
        "    editor_routers = []\n"
        "for _editor_router in editor_routers:\n"
        "    app.include_router(_editor_router)  # GET grouped editor + POST bulk save\n"
    )
    return header + "\n\n" + body


def render_spine(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> Tuple[Tuple[str, str], ...]:
    """All FastAPI-spine artifacts as ``(relative_path, text)`` pairs (routers, db, main)."""
    return (
        (CANONICAL_LAYOUT["fastapi-routers"], render_routers(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-db"], render_db(schema_text, source_file)),
        (CANONICAL_LAYOUT["fastapi-main"], render_main(schema_text, source_file)),
    )
