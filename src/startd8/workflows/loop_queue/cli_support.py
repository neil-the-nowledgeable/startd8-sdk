# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""CLI helpers for Workflow Loop Queue root resolution and stdout hygiene (FR-17/24)."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_QUEUE_RELATIVE = Path(".startd8/workflow-loop-queue")
STARTD8_WLOOP_ROOT_ENV = "STARTD8_WLOOP_ROOT"
_QUEUE_MARKER = ".wlq-root"


def resolve_queue_root(
    explicit: Optional[Path] = None,
    *,
    env: Optional[dict] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve WLQ root: explicit ``--root`` → ``$STARTD8_WLOOP_ROOT`` → CWD default.

    FR-24. Does not create directories.
    """
    if explicit is not None:
        # Typer always passes a Path for --root; treat the relative default as
        # "unspecified" when env is set by comparing to the module default string
        # only when callers pass None for "use resolver fully".
        return Path(explicit).expanduser().resolve()
    environ = env if env is not None else os.environ
    from_env = environ.get(STARTD8_WLOOP_ROOT_ENV)
    if from_env and str(from_env).strip():
        return Path(from_env).expanduser().resolve()
    base = Path(cwd) if cwd is not None else Path.cwd()
    return (base / DEFAULT_QUEUE_RELATIVE).resolve()


def resolve_cli_root(cli_root: Path) -> Path:
    """Resolve ``--root`` for Typer commands.

    If the user left the Typer default (relative
    ``.startd8/workflow-loop-queue``) and ``$STARTD8_WLOOP_ROOT`` is set, prefer
    the env. An absolute ``--root`` or a non-default relative path always wins.
    """
    default_name = DEFAULT_QUEUE_RELATIVE.as_posix()
    # Typer may give a relative Path equal to the default option value.
    if not cli_root.is_absolute() and cli_root.as_posix() in {
        default_name,
        DEFAULT_QUEUE_RELATIVE.name,  # unlikely
    }:
        env = os.environ.get(STARTD8_WLOOP_ROOT_ENV)
        if env and str(env).strip():
            return Path(env).expanduser().resolve()
    return Path(cli_root).expanduser().resolve()


def is_fresh_queue_root(root: Path) -> bool:
    """True when *root* has no prior job envelopes and no queue marker."""
    root = Path(root)
    if not root.exists():
        return True
    jobs = root / "jobs"
    if jobs.is_dir() and any(jobs.glob("*_startd8_wloop.json")):
        return False
    if (root / _QUEUE_MARKER).is_file():
        return False
    # Existing non-empty artifact dirs also mean "not brand new".
    if root.is_dir():
        for child in root.iterdir():
            if child.name in {"jobs", _QUEUE_MARKER}:
                continue
            return False
    return True


def ensure_queue_marker(root: Path) -> None:
    """Touch a marker so subsequent enqueues do not re-warn (FR-24)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _QUEUE_MARKER
    if not marker.exists():
        marker.write_text(
            "WLQ queue root marker (FR-24). Do not delete.\n", encoding="utf-8"
        )


def warn_if_fresh_queue_root(root: Path, *, stream=None) -> bool:
    """Print FR-24 soft warn to stderr when creating/using a brand-new root.

    Returns True when a warning was emitted.
    """
    root = Path(root).resolve()
    if not is_fresh_queue_root(root):
        return False
    out = stream if stream is not None else sys.stderr
    print(
        f"note: created a NEW queue at {root} — is this the intended loop root? "
        f"(docs live elsewhere; pass --root or set ${STARTD8_WLOOP_ROOT_ENV})",
        file=out,
    )
    return True


def quiet_otel_exporters() -> None:
    """Suppress noisy OTLP exporter failures so they cannot spoil JSON stdout."""
    for name in (
        "opentelemetry",
        "opentelemetry.sdk",
        "opentelemetry.exporter",
        "opentelemetry.exporter.otlp",
        "opentelemetry.exporter.otlp.proto.grpc",
        "opentelemetry.exporter.otlp.proto.http",
        "opentelemetry._logs",
        "opentelemetry.sdk._logs",
        "opentelemetry.sdk._logs.export",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def route_sdk_logs_to_stderr() -> None:
    """Point StreamHandlers at stderr so INFO logs cannot trail JSON on stdout."""
    for name in ("startd8", ""):
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            stream = getattr(handler, "stream", None)
            if stream is sys.stdout:
                handler.stream = sys.stderr


def print_json_stdout(value: Any) -> None:
    """Write one JSON document to stdout only (FR-17 CLI contract)."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    sys.stdout.write(json.dumps(value, default=str, indent=2))
    sys.stdout.write("\n")
    sys.stdout.flush()
