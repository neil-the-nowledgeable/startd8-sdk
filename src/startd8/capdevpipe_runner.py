"""Headless cap-dev-pipe orchestration entry (FR-17 / Increment D3).

Resolves an embedded ``.cap-dev-pipe/`` directory, ensures the embed package is importable,
and delegates to ``pipeline.cli.main(['run', ...])`` so all stage flags stay aligned with
``python3 -m pipeline run``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from .capdevpipe_installer import EMBED_DIR_NAME, MANAGED_ENV_KEYS
from .exceptions import ConfigurationError, ValidationError
from .logging_config import get_logger

logger = get_logger(__name__)

_PIPELINE_RUN_FLAGS = frozenset(
    {
        "--config",
        "--plan",
        "--requirements",
        "--project-root",
        "--project",
        "--name",
        "--route",
        "--cost-budget",
        "--run-id",
        "--label",
        "--reuse-export",
        "--stop-after",
        "--generation-profile",
        "--profile",
        "--question-answers",
        "--kaizen-dir",
        "--kaizen-keep",
        "--extra-delivery-args",
        "--extra-contractor-args",
    }
)
_PIPELINE_RUN_BOOL_FLAGS = frozenset(
    {
        "--dry-run",
        "--skip-validate",
        "--skip-polish",
        "--skip-observability",
        "--deterministic-output",
        "--force-provenance",
        "--no-post-run-hooks",
        "--pause",
        "--retry-incomplete",
        "--yes",
        "--interactive",
        "--kaizen",
        "--no-kaizen",
    }
)


def resolve_embed_dir(
    start: Path | None = None,
    *,
    embed_dir: Path | None = None,
) -> Path:
    """Locate ``.cap-dev-pipe/`` under *start* or return an explicit *embed_dir*."""
    if embed_dir is not None:
        resolved = embed_dir.expanduser().resolve()
        if not resolved.is_dir():
            raise ValidationError(
                f"embed directory not found: {resolved}. "
                "Run `startd8 capdevpipe install` or bootstrap the host embed first."
            )
        return resolved

    root = (start or Path.cwd()).resolve()
    candidate = root / EMBED_DIR_NAME
    if candidate.is_dir():
        return candidate

    raise ValidationError(
        f"Missing {EMBED_DIR_NAME}/ under {root}. "
        "Bootstrap the embed (e.g. `python -m pipeline embed` or host bootstrap script) "
        f"or pass --embed-dir /path/to/{EMBED_DIR_NAME}."
    )


def ensure_pipeline_import(embed_dir: Path) -> None:
    """Put the embed directory on ``sys.path`` so ``import pipeline`` resolves."""
    embed_dir = embed_dir.resolve()
    pipeline_pkg = embed_dir / "pipeline"
    if not pipeline_pkg.is_dir():
        raise ValidationError(
            f"embed directory {embed_dir} is missing the managed `pipeline/` package. "
            "Re-run embed or repair before invoking `startd8 capdevpipe run`."
        )
    embed_str = str(embed_dir)
    if embed_str not in sys.path:
        sys.path.insert(0, embed_str)


def resolve_run_config(embed_dir: Path, config_path: Path | None) -> Path | None:
    """Resolve which ``pipeline.yaml`` a run should use, or ``None`` for a config-free run.

    Precedence: an explicit ``config_path`` (from ``--config``) wins and MUST exist —
    asking for a named config that is absent is a real error. Otherwise the embed's default
    ``<embed>/pipeline.yaml`` is used when present. When neither exists the run falls back to
    a **config-free** invocation (issue #220): the ``orchestrator`` embed profile ships
    ``pipeline.env`` + the ``pipeline/`` package but no ``pipeline.yaml``, and the embedded
    pipeline supports a config-free ``run`` (it resolves its script dir from the package
    location and still reads ``pipeline.env``). A missing *default* is therefore not an error.
    """
    if config_path is not None:
        resolved = config_path.expanduser().resolve()
        if not resolved.is_file():
            raise ValidationError(
                f"Missing pipeline config: {resolved}. "
                "Create it, point --config at an existing file, or omit --config to run "
                "config-free (supply --plan/--requirements/--project as passthrough flags)."
            )
        return resolved
    default = (embed_dir / "pipeline.yaml").resolve()
    return default if default.is_file() else None


def build_pipeline_run_argv(
    embed_dir: Path,
    extra_argv: Sequence[str] | None = None,
    *,
    config_path: Path | None = None,
) -> list[str]:
    """Build ``pipeline run`` argv with embed defaults applied.

    Injects ``--config`` when a config is resolvable (explicit or the embed default) and the
    caller has not already supplied ``--config`` in ``extra_argv``. When no config exists the
    run proceeds config-free — the argv simply omits ``--config`` (issue #220).
    """
    embed_dir = embed_dir.resolve()
    extras = list(extra_argv or [])
    if not _argv_has_flag(extras, "--config"):
        config = resolve_run_config(embed_dir, config_path)
        if config is not None:
            extras = ["--config", str(config), *extras]

    argv = ["run", *extras]
    if not _argv_has_flag(argv[1:], "--yes") and not _argv_has_flag(
        argv[1:], "--interactive"
    ):
        argv.extend(["--yes"])
    return argv


#: Managed ``pipeline.env`` keys → the ``pipeline run`` CLI flag that carries the same value.
#: Used to guard against clobbering an explicit CLI flag: the embedded pipeline applies
#: process-env *after* CLI args, so a blindly-exported env var would silently outrank a flag
#: the user actually passed. Keys absent here (CONTEXTCORE_ROOT/SDK_ROOT) have no run flag.
_ENV_KEY_TO_RUN_FLAG = {
    "PROJECT_ROOT": "--project-root",
    "PROJECT_NAME": "--project",
}


def _set_run_env_default(key: str, value: str, extras: Sequence[str]) -> None:
    """``setdefault`` an env var unless the caller passed its equivalent CLI flag (issue #220).

    Skips when *value* is blank, when the corresponding run flag is present in *extras* (env
    would wrongly outrank an explicit CLI arg), or when the key is already set in the
    environment (an explicit export stays authoritative).
    """
    if not value:
        return
    flag = _ENV_KEY_TO_RUN_FLAG.get(key)
    if flag is not None and _argv_has_flag(extras, flag):
        return
    os.environ.setdefault(key, value)


def _hydrate_env_from_pipeline_env(embed_dir: Path, extras: Sequence[str]) -> None:
    """Export managed keys from ``<embed>/pipeline.env`` for a config-free run (issue #220).

    A config-free run resolves the pipeline's script dir from the imported ``pipeline``
    package. For a **symlink** embed that resolves through the symlink to the canonical
    checkout, so the embed's ``pipeline.env`` is never loaded and ``--project`` would be
    unset. The embedded pipeline honors these process-env keys, so hydrating them here makes a
    bare ``capdevpipe run`` work on an orchestrator install whose profile ships no
    ``pipeline.yaml``. Parsing mirrors cap-dev-pipe's ``load_pipeline_env``: plain
    ``KEY=value`` (optionally quoted), ``#`` comments and blank lines skipped, no shell
    sourcing.
    """
    env_path = embed_dir / "pipeline.env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable env degrades to pipeline defaults
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in MANAGED_ENV_KEYS:
            continue
        value = value.strip().strip('"').strip("'")
        _set_run_env_default(key, value, extras)


def discover_profile_docs(embed_dir: Path) -> list[tuple[str, Path, Path]]:
    """Find installed language-profile doc pairs under the embed dir.

    The installer writes each profile as ``<embed>/<lang>/<lang>-plan.md`` +
    ``<lang>-requirements.md`` (``CapDevPipeInstaller.create_profile``). A directory qualifies
    only when *both* convention-named docs are present, which excludes the ``pipeline/`` /
    ``design/`` / ``prompts/`` embed subtrees. Returns ``(lang, plan, requirements)`` triples
    with the docs resolved to absolute paths (profile docs may be relative symlinks), sorted by
    language for determinism.
    """
    found: list[tuple[str, Path, Path]] = []
    if not embed_dir.is_dir():
        return found
    for child in sorted(embed_dir.iterdir()):
        if not child.is_dir():
            continue
        plan = child / f"{child.name}-plan.md"
        reqs = child / f"{child.name}-requirements.md"
        if plan.is_file() and reqs.is_file():
            found.append((child.name, plan.resolve(), reqs.resolve()))
    return found


def _autofill_profile_docs(embed_dir: Path, extras: list[str]) -> list[str]:
    """Inject ``--plan``/``--requirements`` from the sole installed profile (issue #220 → zero-flag).

    The embedded pipeline auto-selects a lone profile, but only one declared in ``pipeline.yaml``
    — a config-free orchestrator install has none, so that path is unreachable. The installer,
    however, already wrote the profile's plan/requirements on disk; discover the single pair and
    inject it so a bare ``capdevpipe run`` works without the caller re-typing embed-relative paths.

    No-ops (returns *extras* unchanged) when the caller already selected inputs
    (``--plan``/``--reuse-export``/``--profile``) or when no profile is installed — the latter
    leaves the pipeline to report its own "plan required" error. Refuses to guess when more than
    one profile is installed: raises with the candidate languages so the caller disambiguates via
    ``--plan``/``--requirements``.
    """
    if (
        _argv_has_flag(extras, "--plan")
        or _argv_has_flag(extras, "--reuse-export")
        or _argv_has_flag(extras, "--profile")
    ):
        return extras
    discovered = discover_profile_docs(embed_dir)
    if not discovered:
        return extras
    if len(discovered) > 1:
        langs = ", ".join(lang for lang, _, _ in discovered)
        raise ValidationError(
            f"Multiple language profiles installed under {embed_dir} ({langs}); cannot "
            "auto-select. Pass --plan/--requirements explicitly (or --profile <name> with a "
            "pipeline.yaml) to choose one."
        )
    lang, plan, reqs = discovered[0]
    logger.info(
        "capdevpipe run: config-free, auto-selected profile %r (plan=%s)",
        lang,
        plan,
        extra={"pipeline_name": "capdevpipe_run"},
    )
    return ["--plan", str(plan), "--requirements", str(reqs), *extras]


def run_embedded_pipeline(
    *,
    cwd: Path | None = None,
    embed_dir: Path | None = None,
    extra_argv: Sequence[str] | None = None,
    config_path: Path | None = None,
) -> int:
    """Run the embedded pipeline orchestrator and return its exit code."""
    workdir = (cwd or Path.cwd()).resolve()
    embed = resolve_embed_dir(workdir, embed_dir=embed_dir)
    ensure_pipeline_import(embed)

    extras = list(extra_argv or [])
    config_free = not _argv_has_flag(extras, "--config") and (
        resolve_run_config(embed, config_path) is None
    )

    os.environ.setdefault("PROCESS_HOME", str(embed))
    if config_free:
        # Load project identity from pipeline.env so a symlink embed (whose pipeline.env the
        # config-free pipeline never reads) still resolves --project/--project-root.
        _hydrate_env_from_pipeline_env(embed, extras)
        # Bridge the installer's on-disk profile dir into the run the pipeline can't auto-select
        # config-free (issue #220 → zero-flag run).
        extras = _autofill_profile_docs(embed, extras)
    _set_run_env_default("PROJECT_ROOT", str(workdir), extras)

    argv = build_pipeline_run_argv(embed, extras, config_path=config_path)

    previous_cwd = Path.cwd()
    try:
        os.chdir(workdir)
        return _invoke_pipeline_main(argv, embed_dir=embed)
    finally:
        os.chdir(previous_cwd)


def _invoke_pipeline_main(argv: list[str], *, embed_dir: Path) -> int:
    """Import and invoke ``pipeline.cli.main`` (patchable for tests).

    ``embed_dir`` is used only to name the missing package in the failure message (and is
    reserved for future script-dir override hooks).
    """
    try:
        from pipeline.cli import main as pipeline_main
    except ImportError as exc:
        raise ConfigurationError(
            "Could not import the embedded pipeline package. "
            f"Ensure {embed_dir / 'pipeline'} exists and PYTHONPATH includes the embed directory."
        ) from exc
    return pipeline_main(argv)


def _argv_has_flag(argv: Sequence[str], flag: str) -> bool:
    if flag not in _PIPELINE_RUN_FLAGS and flag not in _PIPELINE_RUN_BOOL_FLAGS:
        return flag in argv
    if flag in _PIPELINE_RUN_BOOL_FLAGS:
        return flag in argv
    for index, token in enumerate(argv):
        if token == flag:
            return True
        if token.startswith(f"{flag}="):
            return True
    return False
