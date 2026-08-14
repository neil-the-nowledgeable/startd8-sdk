"""Deterministic ``app/auth.py`` — the deployed-mode AUTH SEAM (FR-IDN-2/3/4, M2/A6).

Emitted **only in deployed mode**. Provides a reference principal-resolution dependency
(``get_principal``) + a ``require_principal`` guard, wired to the project-owned ``app/user_routers.py``
seam — the **mechanism**, not a credential/session store (bucket-4 policy stays the operator's).

Contract (AUTH_SEAM_JWT Tier 1.1): Bearer JWT decode-only (stdlib), trusts an upstream gateway/IdP
to have verified the signature. Spoofable ``X-Principal-Id`` is **not** accepted.

The ``REFERENCE_AUTH_SEAM`` marker is **machine-detectable** (R1-F4) so gates/wireframe can flag an
unreplaced reference seam. ``VERIFIED_UPSTREAM = False`` (FR-JWT-9) marks the DECODE-ONLY trust
posture. The module banner carries the FR-IDN-4 *authenticated-but-not-tenant-isolated* warning
(tenant row-scoping is Tier B / M3).

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

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status

# REFERENCE auth seam (FR-IDN-2/3) — machine-detectable marker (R1-F4). This is a REFERENCE scaffold,
# NOT a production credential/session store: replace get_principal's body with your real identity
# provider (OAuth/OIDC/verified session or JWT) before deploying. While this stays True, gates and
# `startd8 wireframe` flag the seam as unreplaced.
REFERENCE_AUTH_SEAM = True

# FR-JWT-9 — DECODE-ONLY trust posture. Machine-detectable: while False, the seam DECODES the JWT
# but does NOT cryptographically verify the signature. Safe ONLY behind a gateway/IdP that already
# verified the token. For direct-internet exposure, replace `_decode_jwt_claims` with PyJWT + JWKS
# verification (add `pyjwt[crypto]` to requirements) and set this True.
VERIFIED_UPSTREAM = False

# FR-IDN-4 — AUTHENTICATED BUT NOT TENANT-ISOLATED: this seam authenticates a principal, but the
# generated CRUD queries are NOT row-scoped (tenant isolation is a later increment). Until then EVERY
# authenticated principal can read/mutate EVERY row. Legal only for a single-owner or shared-read-only
# deployment; do not treat this as multi-tenant-safe.

# DECODE-ONLY (FR-JWT-3/9): this module DECODES Bearer JWTs (stdlib base64url + JSON) and does NOT
# verify signatures. Safe ONLY behind a gateway/IdP that verified the token. For direct exposure,
# replace `_decode_jwt_claims` with PyJWT + JWKS verification and flip VERIFIED_UPSTREAM.


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. ``id`` is ``sub`` (mandatory for tenancy / require_principal)."""

    id: str
    iss: Optional[str] = None
    aud: Optional[Any] = None
    exp: Optional[int] = None
    scopes: tuple[str, ...] = field(default_factory=tuple)


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _decode_jwt_claims(token: str) -> dict:
    """Decode JWT payload only (no signature verify). Returns {} on any malformation."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        raw = _b64url_decode(parts[1])
        claims = json.loads(raw.decode("utf-8"))
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def _scopes_from_claims(claims: dict) -> tuple[str, ...]:
    out: list[str] = []
    scope = claims.get("scope")
    if isinstance(scope, str) and scope.strip():
        out.extend(scope.split())
    for key in ("scopes", "roles", "groups"):
        val = claims.get(key)
        if isinstance(val, str) and val.strip():
            out.extend(val.split())
        elif isinstance(val, (list, tuple)):
            out.extend(str(x) for x in val if x is not None and str(x).strip())
    # dedupe, preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return tuple(uniq)


def get_principal(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Optional[Principal]:
    """REFERENCE resolver — ``Authorization: Bearer <JWT>``, decode-only (FR-JWT-1..4).

    Trusts an upstream gateway/IdP to have verified the signature (VERIFIED_UPSTREAM=False).
    Single Bearer ingress only (no spoofable custom-header fallback). Missing/malformed/expired
    → None (401 via ``require_principal``).
    """
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    claims = _decode_jwt_claims(parts[1].strip())
    if not claims:
        return None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        return None
    exp = claims.get("exp")
    if exp is None:
        return None  # FR-JWT-4 fail-closed: missing exp → no principal
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return None  # unparseable exp → fail closed
    if exp_i < int(time.time()):
        return None  # expired → no principal → 401 via require_principal
    return Principal(
        id=sub.strip(),
        iss=claims.get("iss") if isinstance(claims.get("iss"), str) else None,
        aud=claims.get("aud"),
        exp=exp_i,
        scopes=_scopes_from_claims(claims),
    )


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


def is_verified_auth_seam(auth_text: str) -> bool:
    """True iff *auth_text* declares ``VERIFIED_UPSTREAM = True`` (FR-JWT-9).

    Default emitted seam is decode-only (``VERIFIED_UPSTREAM = False``) → this returns False so
    gates/wireframe can advise that the seam is not hardened for direct exposure.
    """
    return "VERIFIED_UPSTREAM = True" in (auth_text or "")
