"""Deterministic ``app/auth.py`` — the deployed-mode AUTH SEAM (FR-IDN-2/3/4, M2/A6).

Emitted **only in deployed mode**. Provides a reference principal-resolution dependency
(``get_principal``) + a ``require_principal`` guard, wired to the project-owned ``app/user_routers.py``
seam — the **mechanism**, not a credential/session store (bucket-4 policy stays the operator's). The
``REFERENCE_AUTH_SEAM`` marker is **machine-detectable** (R1-F4) so gates/wireframe can flag an
unreplaced reference seam. The module banner carries the FR-IDN-4 *authenticated-but-not-tenant-
isolated* warning (tenant row-scoping is Tier B / M3).

Drift: the body is constant (it does not vary by schema or mode value — it only *exists* in deployed
mode), so the schema-only skip-hook verifies it like any standard artifact via the ``_renderers`` map
(schema-sha staleness + full byte re-render); no self-embedded mode is needed (unlike ``settings.py``).
``app/main.py`` is **unchanged**: ``auth.py`` is a dependency module the operator applies through the
``user_routers.py`` seam (``from .auth import require_principal``), so nothing is mounted in main.
"""

from __future__ import annotations

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_standard

_BODY = '''\
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

# REFERENCE auth seam (FR-IDN-2/3) — machine-detectable marker (R1-F4). This is a REFERENCE scaffold,
# NOT a production credential/session store: replace get_principal's body with your real identity
# provider (OAuth/OIDC/verified session or JWT) before deploying. While this stays True, gates and
# `startd8 wireframe` flag the seam as unreplaced.
REFERENCE_AUTH_SEAM = True

# FR-IDN-4 — AUTHENTICATED BUT NOT TENANT-ISOLATED: this seam authenticates a principal, but the
# generated CRUD queries are NOT row-scoped (tenant isolation is a later increment). Until then EVERY
# authenticated principal can read/mutate EVERY row. Legal only for a single-owner or shared-read-only
# deployment; do not treat this as multi-tenant-safe.


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Extend with the fields your identity provider supplies."""

    id: str


def get_principal(
    x_principal_id: Optional[str] = Header(default=None, alias="X-Principal-Id"),
) -> Optional[Principal]:
    """REFERENCE resolver — trusts an ``X-Principal-Id`` header. NOT production: replace this body with
    real verification (validate a signed session/JWT, look the subject up, etc.)."""
    if not x_principal_id:
        return None
    return Principal(id=x_principal_id)


def require_principal(principal: Optional[Principal] = Depends(get_principal)) -> Principal:
    """FastAPI dependency that ENFORCES authentication (401 when no principal resolves). Apply it via
    the project-owned ``app/user_routers.py`` seam — the generated CRUD routes are not auto-guarded::

        from fastapi import Depends
        from .auth import require_principal

        @router.get("/secure", dependencies=[Depends(require_principal)])
        def secure(...): ...
    """
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return principal
'''


def render_auth_seam(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/auth.py`` — the deployed-only reference auth seam (FR-IDN-2). Deterministic."""
    sha = schema_sha256(schema_text)
    return header_standard(source_file, sha, "python-auth-seam") + "\n\n" + _BODY


def is_reference_auth_seam(auth_text: str) -> bool:
    """True iff *auth_text* still carries the unreplaced reference marker (R1-F4) — gates/wireframe use
    this to advise that the reference ``get_principal`` was never swapped for a real provider."""
    return "REFERENCE_AUTH_SEAM = True" in (auth_text or "")
