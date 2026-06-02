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
}


def _header(source_file: str, sha: str, kind: str) -> str:
    return (
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {sha}"
    )


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
def list_{prefix}(session: Session = Depends(get_session)) -> list[{name}]:
    return list(session.exec(select({name})).all())


@{rname}.post("/")
def create_{prefix}(item: {name}, session: Session = Depends(get_session)) -> {name}:
    session.add(item)
    session.commit()
    session.refresh(item)
    return item"""


_BY_PK = """


@{rname}.get("/{{item_id}}")
def get_{prefix}(item_id: {pktype}, session: Session = Depends(get_session)) -> {name}:
    obj = session.get({name}, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="{name} not found")
    return obj


@{rname}.patch("/{{item_id}}")
def update_{prefix}(
    item_id: {pktype}, data: {name}, session: Session = Depends(get_session)
) -> {name}:
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
        imports += "from .tables import " + ", ".join(sorted(names)) + "\n"

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
        "import os\n"
        "from collections.abc import Iterator\n\n"
        "from sqlmodel import Session, SQLModel, create_engine\n\n"
        "from . import tables  # noqa: F401  (import registers tables on SQLModel.metadata)\n\n"
        "# Local-first SQLite (NFR-1); override with the DATABASE_URL env var.\n"
        'DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")\n'
        "engine = create_engine(DATABASE_URL, echo=False)\n\n\n"
        "def init_db() -> None:\n"
        "    SQLModel.metadata.create_all(engine)\n\n\n"
        "def get_session() -> Iterator[Session]:\n"
        "    with Session(engine) as session:\n"
        "        yield session\n"
    )
    return header + "\n\n" + body


def render_main(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/main.py`` — the FastAPI app, init_db on startup, all routers included."""
    sha = schema_sha256(schema_text)
    header = _header(source_file, sha, "fastapi-main")
    body = (
        "from __future__ import annotations\n\n"
        "from contextlib import asynccontextmanager\n\n"
        "from fastapi import FastAPI\n\n"
        "from .db import init_db\n"
        "from .routers import all_routers\n\n\n"
        "@asynccontextmanager\n"
        "async def lifespan(app: FastAPI):\n"
        "    init_db()\n"
        "    yield\n\n\n"
        'app = FastAPI(title="StartDate", lifespan=lifespan)\n\n'
        "for _router in all_routers:\n"
        "    app.include_router(_router)\n"
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
