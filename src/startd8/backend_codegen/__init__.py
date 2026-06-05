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
from .assembler import render_backend
from .derived import (
    render_ai_schemas,
    render_completeness,
    render_derived,
    render_export,
    render_requirements,
)
from .drift import check_drift, is_owned_generated_file, owned_file_in_sync
from .htmx_generator import render_ui, render_web
from .pages_generator import (
    parse_pages,
    render_pages,
    render_pages_router,
    render_page_shell,
)
from .pages_authoring import render_authoring
from .gates import verify_pydantic_fidelity, verify_sqlmodel_fidelity
from .provider import PydanticSQLModelProvider
from .pydantic_renderer import PydanticRenderResult, render_pydantic_models
from .sqlmodel_renderer import SQLModelRenderResult, render_sqlmodel_tables
from .test_emitter import (
    COMPLETENESS_TESTS_PATH,
    CONTRACT_TESTS_PATH,
    render_completeness_tests,
    render_contract_tests,
)

__all__ = [
    "render_pydantic_models",
    "PydanticRenderResult",
    "render_sqlmodel_tables",
    "SQLModelRenderResult",
    "render_routers",
    "render_db",
    "render_main",
    "render_spine",
    "render_web",
    "render_ui",
    "parse_pages",
    "render_pages",
    "render_pages_router",
    "render_page_shell",
    "render_authoring",
    "render_export",
    "render_ai_schemas",
    "render_completeness",
    "render_derived",
    "render_requirements",
    "render_contract_tests",
    "render_completeness_tests",
    "CONTRACT_TESTS_PATH",
    "COMPLETENESS_TESTS_PATH",
    "render_backend",
    "CANONICAL_LAYOUT",
    "check_drift",
    "owned_file_in_sync",
    "is_owned_generated_file",
    "PydanticSQLModelProvider",
    "verify_pydantic_fidelity",
    "verify_sqlmodel_fidelity",
]
