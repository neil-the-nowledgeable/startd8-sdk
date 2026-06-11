"""Deterministic ``app/settings.py`` generation (deployment-mode capability, FR-CFG-7 / FR-CFG-7a).

``settings.py`` is the **single** generated file whose bytes vary by deployment mode. It bakes the
``DEPLOYMENT_MODE`` constant and centralizes the runtime env reads (DB URL, engine pool options,
``create_all`` gate, bind host) plus the directional fail-closed runtime validation (FR-CFG-4). The
body below is deliberately **mode-invariant text** — every behavioral difference is a *runtime*
branch on ``DEPLOYMENT_MODE`` — so the only bytes that differ between an installed and a deployed
``settings.py`` are the ``# startd8-mode:`` header line and the ``DEPLOYMENT_MODE = "…"`` assignment.

The mode is **self-described** in the header (see :func:`startd8.backend_codegen._headers.header_settings`)
so the schema-only skip-hook re-renders it from the file's own header without reading ``app.yaml``.

Emission policy (D11): this file is emitted **only in ``deployed`` mode**. Installed mode is the
settings-absent default and stays byte-identical to today (R4). ``render_settings`` itself accepts
either mode value so the drift re-render can reconstruct a file from its self-described mode.
"""

from __future__ import annotations

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_settings

# The two declared modes (kept in sync with scaffold_codegen.manifest._VALID_DEPLOYMENT_MODES).
INSTALLED = "installed"
DEPLOYED = "deployed"
_VALID_MODES = frozenset({INSTALLED, DEPLOYED})

# The mode-invariant body. `{mode}` is the ONLY interpolation — everything else branches on the baked
# DEPLOYMENT_MODE constant at runtime, so installed/deployed settings.py differ by exactly one line.
_BODY = '''\
from __future__ import annotations

import os
import sys

# The deployment mode this app was generated for (FR-CFG-1). Baked at generation from app.yaml's
# `deployment.mode`; the structural shape was generated for THIS mode and is not switched at runtime
# (NR-3). `installed` = single-user, local; `deployed` = multi-user, shared compute/persistence.
DEPLOYMENT_MODE = "{mode}"

_INSTALLED = "installed"
_DEPLOYED = "deployed"


def database_url() -> str:
    """The DB connection string (runtime binding, FR-PER-2). The default differs by mode; an explicit
    DATABASE_URL always wins. Deployed has no local default — it must point at the shared database."""
    default = "sqlite:///./app.db" if DEPLOYMENT_MODE == _INSTALLED else ""
    url = os.environ.get("DATABASE_URL", default)
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required in deployed mode (there is no local SQLite default); "
            "point it at the shared database."
        )
    return url


def engine_options() -> dict:
    """SQLAlchemy create_engine kwargs (FR-CON-1). Deployed gets a connection pool sized for
    concurrent requests against the shared DB; installed keeps SQLite single-writer defaults."""
    if DEPLOYMENT_MODE == _DEPLOYED:
        return {{
            "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
            "pool_pre_ping": True,
        }}
    return {{}}


def should_create_all() -> bool:
    """Whether init_db() may create tables on startup (FR-PER-3). Installed: yes (dev bootstrap).
    Deployed: no — a shared DB evolves via managed migrations (`alembic upgrade head`)."""
    return DEPLOYMENT_MODE == _INSTALLED


def bind_host() -> str:
    """Default bind host (FR-NET-1): installed -> loopback; deployed -> all interfaces. HOST wins."""
    default = "127.0.0.1" if DEPLOYMENT_MODE == _INSTALLED else "0.0.0.0"
    return os.environ.get("HOST", default)


def validate_runtime_mode() -> None:
    """Directional fail-closed runtime check (FR-CFG-4). If the environment claims a mode the binary
    was NOT generated for, refuse to start in the security-DOWNGRADE direction (env says deployed but
    this binary is installed-shaped -> it lacks the auth/isolation the env implies); warn-and-continue
    in the safe direction. Never silently switch the structural shape the code was generated for."""
    env = os.environ.get("STARTD8_DEPLOYMENT_MODE")
    if not env or env == DEPLOYMENT_MODE:
        return
    msg = (
        "deployment-mode mismatch: STARTD8_DEPLOYMENT_MODE=" + repr(env)
        + " but this app was generated for " + repr(DEPLOYMENT_MODE) + "."
    )
    if env == _DEPLOYED and DEPLOYMENT_MODE == _INSTALLED:
        # Dangerous direction: the environment expects multi-user auth/isolation this binary lacks.
        raise SystemExit(
            msg + " Refusing to start (an installed-shaped app must not serve as deployed)."
        )
    sys.stderr.write("warning: " + msg + " Continuing with the generated mode.\\n")
'''


def render_settings(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    mode: str = DEPLOYED,
) -> str:
    """Render ``app/settings.py`` for *mode* (FR-CFG-7). Deterministic; mode self-described in header.

    *mode* must be one of the two declared modes. The schema hash is embedded for staleness; the mode
    is embedded so the schema-only skip-hook re-renders this file from its own header (FR-CFG-7a).
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"render_settings: mode must be one of {sorted(_VALID_MODES)}, got {mode!r}"
        )
    sha = schema_sha256(schema_text)
    header = header_settings(source_file, sha, mode)
    return header + "\n\n" + _BODY.format(mode=mode)
