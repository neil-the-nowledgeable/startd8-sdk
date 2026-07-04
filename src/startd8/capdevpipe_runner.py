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

from .capdevpipe_installer import EMBED_DIR_NAME
from .exceptions import ConfigurationError, ValidationError

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


def build_pipeline_run_argv(
    embed_dir: Path,
    extra_argv: Sequence[str] | None = None,
    *,
    config_path: Path | None = None,
) -> list[str]:
    """Build ``pipeline run`` argv with embed defaults applied."""
    embed_dir = embed_dir.resolve()
    config = (config_path or embed_dir / "pipeline.yaml").resolve()
    if not config.is_file():
        raise ValidationError(
            f"Missing pipeline config: {config}. "
            f"Create {embed_dir / 'pipeline.yaml'} or pass --config."
        )

    extras = list(extra_argv or [])
    if not _argv_has_flag(extras, "--config"):
        extras = ["--config", str(config), *extras]

    argv = ["run", *extras]
    if not _argv_has_flag(argv[1:], "--yes") and not _argv_has_flag(argv[1:], "--interactive"):
        argv.extend(["--yes"])
    return argv


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

    os.environ.setdefault("PROCESS_HOME", str(embed))
    os.environ.setdefault("PROJECT_ROOT", str(workdir))

    argv = build_pipeline_run_argv(embed, extra_argv, config_path=config_path)

    previous_cwd = Path.cwd()
    try:
        os.chdir(workdir)
        return _invoke_pipeline_main(argv, embed_dir=embed)
    finally:
        os.chdir(previous_cwd)


def _invoke_pipeline_main(argv: list[str], *, embed_dir: Path) -> int:
    """Import and invoke ``pipeline.cli.main`` (patchable for tests)."""
    del embed_dir  # reserved for future script_dir override hooks
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
