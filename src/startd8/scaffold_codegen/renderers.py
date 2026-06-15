"""Deterministic plumbing emitters (class-2 determinism — manifest-derived, REQ-SCAF-3).

Pure, no-LLM projection of ``app.yaml`` into the project plumbing ``backend_codegen`` does *not*
emit (it owns ``app/``; this owns the project around it): ``pyproject.toml`` (the #1 rebuild
blocker — no project env = no mypy/pytest/boot), a rotating file-logging module, the Alembic
baseline (``t-migrations``), and a ``Dockerfile``. Every file carries a ``#`` GENERATED header
(.toml/.py/.ini/Dockerfile all support ``#`` comments) hashing ``app.yaml`` — owned, drift-checked,
byte-identical.

Deliberately **non-overlapping with backend_codegen** (v1): WAL/async/cold-start touch app code the
backend owns and are deferred (see SCAFFOLD_GENERATOR_REQUIREMENTS.md OQ/Non-Goals).
"""

from __future__ import annotations

from typing import List, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256  # generic sha256-over-text hasher
from .manifest import parse_app_manifest

# The generated app's runtime + dev deps (fixed by the FastAPI+SQLModel+HTMX stack, not manifest-derived).
_RUNTIME_DEPS: Tuple[str, ...] = (
    "fastapi",
    "sqlmodel",
    "pydantic>=2",
    "jinja2",
    "uvicorn[standard]",
    "python-multipart",
    "anthropic",
)
_DEV_DEPS: Tuple[str, ...] = ("mypy", "pytest", "httpx", "alembic")


def _header(kind: str, sha: str) -> str:
    """The ``#``-comment GENERATED/provenance header (one truth; hashes app.yaml, not the schema)."""
    return (
        "# GENERATED from app.yaml — do not edit by hand; regenerate via `startd8 generate scaffold`.\n"
        f"# startd8-artifact: {kind}\n"
        "# Source of truth: the app manifest.\n"
        f"# manifest-sha256: {sha}"
    )


def _toml_list(items: Tuple[str, ...]) -> str:
    return "[\n" + "".join(f"    {i!r},\n" for i in items) + "]"


def render_pyproject(manifest_text: str) -> str:
    """``pyproject.toml`` — the project env (deps + build system). THE #1 rebuild blocker."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = (
        "[build-system]\n"
        'requires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{m.name}"\n'
        'version = "0.1.0"\n'
        f'requires-python = ">={m.python_version}"\n'
        # G4: contract-stack deps + any owned-glue deps declared in app.yaml `extra_dependencies`.
        f"dependencies = {_toml_list(_RUNTIME_DEPS + m.extra_dependencies)}\n\n"
        "[project.optional-dependencies]\n"
        f"dev = {_toml_list(_DEV_DEPS)}\n\n"
        "[tool.setuptools]\n"
        f'packages = ["{m.package}"]\n'
    )
    return _header("scaffold-pyproject", sha) + "\n\n" + body


def render_logging(manifest_text: str) -> str:
    """``<package>/logging_config.py`` — rotating file logging (the local-first app's only diagnosability)."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = (
        "from __future__ import annotations\n\n"
        "import logging\n"
        "from logging.handlers import RotatingFileHandler\n"
        "from pathlib import Path\n\n"
        f'_LOG_FILE = Path({m.log_file!r})\n'
        "_CONFIGURED = False\n\n\n"
        "def get_logger(name: str) -> logging.Logger:\n"
        '    """A logger that writes to a rotating local file (configured once, idempotent)."""\n'
        "    global _CONFIGURED\n"
        "    if not _CONFIGURED:\n"
        "        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)\n"
        "        handler = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=3)\n"
        "        handler.setFormatter(\n"
        '            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")\n'
        "        )\n"
        "        root = logging.getLogger()\n"
        "        root.setLevel(logging.INFO)\n"
        "        if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):\n"
        "            root.addHandler(handler)\n"
        "        _CONFIGURED = True\n"
        "    return logging.getLogger(name)\n"
    )
    return _header("scaffold-logging", sha) + "\n\n" + body


def render_dockerfile(manifest_text: str) -> str:
    """``Dockerfile`` — a minimal container for the generated app (build input only).

    The container always binds ``0.0.0.0`` (a loopback container is unreachable). The mode-derived
    *local* bind (installed → loopback) lives in ``run.sh`` (FR-NET-1/2); installed mode's primary run
    is that local script, not this public-server container."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = (
        f"# deployment mode: {m.deployment_mode} — the container binds 0.0.0.0 for reachability; "
        "installed mode's primary run is the local run.sh (loopback).\n"
        f"FROM python:{m.python_version}-slim\n\n"
        "WORKDIR /app\n"
        "COPY pyproject.toml .\n"
        "RUN pip install --no-cache-dir .\n"
        "COPY . .\n\n"
        "EXPOSE 8000\n"
        f'CMD ["uvicorn", "{m.package}.main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
    )
    return _header("scaffold-dockerfile", sha) + "\n\n" + body


def render_run_script(manifest_text: str) -> str:
    """``run.sh`` — the local run script; bind host is mode-derived (FR-NET-1/2).

    installed → loopback (``127.0.0.1``, single-user local — the PRIMARY installed run path); deployed
    → all interfaces (``0.0.0.0``). ``PORT`` env overrides the port. The shebang stays line 1; the
    GENERATED header follows as bash comments so drift/ownership still recognize it."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    bind = "127.0.0.1" if m.deployment_mode == "installed" else "0.0.0.0"
    body = (
        "set -euo pipefail\n\n"
        f"# deployment mode: {m.deployment_mode} — bind {bind} (FR-NET-1).\n"
        f'exec uvicorn {m.package}.main:app --host {bind} --port "${{PORT:-8000}}"\n'
    )
    return "#!/usr/bin/env bash\n" + _header("scaffold-run-script", sha) + "\n\n" + body


def render_alembic_ini(manifest_text: str) -> str:
    """``alembic.ini`` — the migration config (t-migrations baseline)."""
    sha = schema_sha256(manifest_text)
    body = (
        "[alembic]\n"
        "script_location = alembic\n"
        "prepend_sys_path = .\n\n"
        "[loggers]\n"
        "keys = root\n\n"
        "[handlers]\n"
        "keys = console\n\n"
        "[formatters]\n"
        "keys = generic\n\n"
        "[logger_root]\n"
        "level = WARN\n"
        "handlers = console\n"
        "qualname =\n\n"
        "[handler_console]\n"
        "class = StreamHandler\n"
        "args = (sys.stderr,)\n"
        "level = NOTSET\n"
        "formatter = generic\n\n"
        "[formatter_generic]\n"
        "format = %(levelname)-5.5s [%(name)s] %(message)s\n"
    )
    return _header("scaffold-alembic-ini", sha) + "\n\n" + body


def render_alembic_env(manifest_text: str) -> str:
    """``alembic/env.py`` — autogenerate against the owned SQLModel metadata (regen-safe migrations)."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = (
        "from __future__ import annotations\n\n"
        "import os\n\n"
        "from alembic import context\n"
        "from sqlalchemy import engine_from_config, pool\n"
        "from sqlmodel import SQLModel\n\n"
        f"import {m.package}.tables  # noqa: F401 — registers every table on SQLModel.metadata\n\n"
        "config = context.config\n"
        f'_url = os.environ.get("DATABASE_URL", "sqlite:///{m.db_path}")\n'
        'config.set_main_option("sqlalchemy.url", _url)\n'
        "target_metadata = SQLModel.metadata\n\n\n"
        "def run_migrations_offline() -> None:\n"
        "    context.configure(url=_url, target_metadata=target_metadata, literal_binds=True,\n"
        "                      render_as_batch=True)  # SQLite needs batch mode to ALTER\n"
        "    with context.begin_transaction():\n"
        "        context.run_migrations()\n\n\n"
        "def run_migrations_online() -> None:\n"
        "    connectable = engine_from_config(\n"
        '        config.get_section(config.config_ini_section, {}),\n'
        '        prefix="sqlalchemy.",\n'
        "        poolclass=pool.NullPool,\n"
        "    )\n"
        "    with connectable.connect() as connection:\n"
        "        context.configure(connection=connection, target_metadata=target_metadata,\n"
        "                          render_as_batch=True)  # SQLite needs batch mode to ALTER\n"
        "        with context.begin_transaction():\n"
        "            context.run_migrations()\n\n\n"
        "if context.is_offline_mode():\n"
        "    run_migrations_offline()\n"
        "else:\n"
        "    run_migrations_online()\n"
    )
    return _header("scaffold-alembic-env", sha) + "\n\n" + body


def render_alembic_mako(manifest_text: str) -> str:
    """``alembic/script.py.mako`` — the revision template Alembic needs to GENERATE a revision.

    Without it ``alembic revision`` fails; the scaffold previously emitted env.py + ini but not this,
    so a generated app could not actually produce a migration (FR-MG-1). Canonical Alembic template.
    """
    sha = schema_sha256(manifest_text)
    body = (
        '"""${message}\n\n'
        "Revision ID: ${up_revision}\n"
        "Revises: ${down_revision | comma,n}\n"
        "Create Date: ${create_date}\n\n"
        '"""\n'
        "from typing import Sequence, Union\n\n"
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "${imports if imports else ''}\n\n"
        "# revision identifiers, used by Alembic.\n"
        "revision: str = ${repr(up_revision)}\n"
        "down_revision: Union[str, None] = ${repr(down_revision)}\n"
        "branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}\n"
        "depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}\n\n\n"
        "def upgrade() -> None:\n"
        "    ${upgrades if upgrades else 'pass'}\n\n\n"
        "def downgrade() -> None:\n"
        "    ${downgrades if downgrades else 'pass'}\n"
    )
    return _header("scaffold-alembic-mako", sha) + "\n\n" + body


def render_owned_requirements(manifest_text: str) -> str:
    """``requirements-owned.txt`` — owned-glue runtime deps from app.yaml `extra_dependencies` (G4).

    The SDK-fixed runtime stack stays in the backend's ``requirements.txt``; owned-capability deps
    (e.g. reportlab/pypdf for an owned PDF path) land here so a deploy can
    ``pip install -r requirements.txt -r requirements-owned.txt`` instead of hand-maintaining a file.
    Emitted only when ``extra_dependencies`` is non-empty (see render_scaffold).
    """
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = "\n".join(m.extra_dependencies)
    return _header("scaffold-owned-requirements", sha) + "\n\n" + body + "\n"


def render_env_example(manifest_text: str) -> str:
    """``.env.example`` — the local-config template (API key, DB url, cost budget). Bucket-1 plumbing."""
    m = parse_app_manifest(manifest_text)
    sha = schema_sha256(manifest_text)
    body = (
        "ANTHROPIC_API_KEY=\n"
        f"DATABASE_URL=sqlite:///{m.db_path}\n"
        "COST_BUDGET_USD=10\n"
    )
    return _header("scaffold-env", sha) + "\n\n" + body


def render_scaffold(manifest_text: str) -> Tuple[Tuple[str, str], ...]:
    """Every plumbing artifact as ``(relative_path, text)`` pairs, gated by the manifest's flags."""
    m = parse_app_manifest(manifest_text)
    out: List[Tuple[str, str]] = [
        ("pyproject.toml", render_pyproject(manifest_text)),
        (f"{m.package}/logging_config.py", render_logging(manifest_text)),
        (".env.example", render_env_example(manifest_text)),
        ("run.sh", render_run_script(manifest_text)),  # local run; bind mode-derived (FR-NET-1/2)
    ]
    if m.extra_dependencies:  # G4: only when the app declares owned-glue deps
        out.append(("requirements-owned.txt", render_owned_requirements(manifest_text)))
    if m.dockerfile:
        out.append(("Dockerfile", render_dockerfile(manifest_text)))
    if m.migrations:
        out.append(("alembic.ini", render_alembic_ini(manifest_text)))
        out.append(("alembic/env.py", render_alembic_env(manifest_text)))
        out.append(("alembic/script.py.mako", render_alembic_mako(manifest_text)))
        # versions/ must exist for `alembic revision`/`upgrade`; .gitkeep keeps the empty dir in git.
        out.append(("alembic/versions/.gitkeep", ""))
    return tuple(out)


# Artifact-kind → renderer, for the provider/drift re-render path (each takes the manifest text).
SCAFFOLD_RENDERERS = {
    "scaffold-pyproject": render_pyproject,
    "scaffold-logging": render_logging,
    "scaffold-dockerfile": render_dockerfile,
    "scaffold-alembic-ini": render_alembic_ini,
    "scaffold-alembic-env": render_alembic_env,
    "scaffold-alembic-mako": render_alembic_mako,
    "scaffold-owned-requirements": render_owned_requirements,
    "scaffold-env": render_env_example,
    "scaffold-run-script": render_run_script,
}
