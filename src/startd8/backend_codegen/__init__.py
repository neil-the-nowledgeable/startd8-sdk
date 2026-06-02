"""Python contract-codegen path — deterministic Prisma→Pydantic (+ later SQLModel/FastAPI/HTMX).

The Python sibling of ``frontend_codegen`` (Prisma→Zod). Step 1 ships the Pydantic-models
renderer, the owned-file drift check, the deterministic-file provider (skip-hook integration), and
the render-fidelity gate. The ``.prisma`` schema is the single neutral contract IDL; Pydantic is a
projection of it.
"""

from __future__ import annotations

from .crud_generator import (
    CANONICAL_LAYOUT,
    render_db,
    render_main,
    render_routers,
    render_spine,
)
from .drift import check_drift, is_owned_generated_file, owned_file_in_sync
from .gates import verify_pydantic_fidelity, verify_sqlmodel_fidelity
from .provider import PydanticSQLModelProvider
from .pydantic_renderer import PydanticRenderResult, render_pydantic_models
from .sqlmodel_renderer import SQLModelRenderResult, render_sqlmodel_tables

__all__ = [
    "render_pydantic_models",
    "PydanticRenderResult",
    "render_sqlmodel_tables",
    "SQLModelRenderResult",
    "render_routers",
    "render_db",
    "render_main",
    "render_spine",
    "CANONICAL_LAYOUT",
    "check_drift",
    "owned_file_in_sync",
    "is_owned_generated_file",
    "PydanticSQLModelProvider",
    "verify_pydantic_fidelity",
    "verify_sqlmodel_fidelity",
]
