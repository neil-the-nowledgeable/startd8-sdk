"""
Jsonnet compilation — binary and Python backends (DC-105).
"""

import json
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from startd8.dashboard_creator.discovery import MixinContext, ToolchainInfo
from startd8.exceptions import Startd8Error
from startd8.logging_config import get_logger

logger = get_logger(__name__)


class CompilationError(Startd8Error):
    """Jsonnet compilation failed."""

    def __init__(self, message: str, source_path: str = "", line: int = 0):
        self.source_path = source_path
        self.line = line
        super().__init__(message)


@dataclass
class CompilationResult:
    """Result of a successful Jsonnet compilation."""

    json_str: str
    duration_ms: int
    backend: str  # "binary" or "python"


def compile_jsonnet(
    source_path: Path,
    mixin: MixinContext,
    toolchain: ToolchainInfo,
    timeout_seconds: int = 30,
) -> CompilationResult:
    """DC-105: Compile .libsonnet to JSON.

    Binary backend:
      jsonnet -J vendor/ -J lib/ <source_path>

    Python backend:
      _gojsonnet.evaluate_file(str(source_path), jpathdir=[...])

    Raises:
      CompilationError — Jsonnet syntax/semantic error
      TimeoutError — Compilation exceeded timeout
    """
    start = time.monotonic()
    logger.debug("Compiling %s via %s backend", source_path, toolchain.backend)

    if toolchain.backend == "binary":
        result_json = _compile_binary(
            source_path, mixin, toolchain, timeout_seconds
        )
    else:
        result_json = _compile_python(source_path, mixin, timeout_seconds)

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info("Compilation completed in %dms (%s)", duration_ms, toolchain.backend)

    # Validate output is parseable JSON
    try:
        json.loads(result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CompilationError(
            f"Jsonnet produced invalid JSON: {exc}",
            source_path=str(source_path),
        )

    return CompilationResult(
        json_str=result_json,
        duration_ms=duration_ms,
        backend=toolchain.backend,
    )


def compile_jsonnet_string(
    source: str,
    mixin: MixinContext,
    toolchain: ToolchainInfo,
    timeout_seconds: int = 30,
) -> CompilationResult:
    """Compile Jsonnet from a string (writes to tempfile, compiles, cleans up)."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".libsonnet",
        dir=str(mixin.dashboards_dir),
        delete=True,
        encoding="utf-8",
    ) as f:
        f.write(source)
        f.flush()
        return compile_jsonnet(
            Path(f.name), mixin, toolchain, timeout_seconds
        )


def _compile_binary(
    source_path: Path,
    mixin: MixinContext,
    toolchain: ToolchainInfo,
    timeout_seconds: int,
) -> str:
    """Compile using the jsonnet CLI binary."""
    cmd = [
        toolchain.binary_path or "jsonnet",
        "-J", str(mixin.vendor_dir),
        "-J", str(mixin.mixin_dir / "lib"),
        "-J", str(mixin.mixin_dir),
        str(source_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(
            f"Jsonnet compilation timed out after {timeout_seconds}s"
        )

    if proc.returncode != 0:
        raise CompilationError(
            proc.stderr.strip() or f"jsonnet exited with code {proc.returncode}",
            source_path=str(source_path),
        )

    return proc.stdout


def _compile_python(
    source_path: Path,
    mixin: MixinContext,
    timeout_seconds: int,
) -> str:
    """Compile using the _gojsonnet Python package.

    Timeout is enforced via a daemon thread — if evaluation exceeds the
    limit, TimeoutError is raised.  The background thread cannot be
    cancelled (C-extension limitation) but is marked daemon so it won't
    block process exit.
    """
    try:
        import _gojsonnet  # type: ignore[import-untyped]
    except ImportError:
        raise CompilationError(
            "Python backend requested but _gojsonnet is not installed. "
            "Install with: pip install gojsonnet"
        )

    jpathdir = [
        str(mixin.vendor_dir),
        str(mixin.mixin_dir / "lib"),
        str(mixin.mixin_dir),
    ]

    result_box: List[Optional[str]] = [None]
    error_box: List[Optional[Exception]] = [None]

    def _worker() -> None:
        try:
            result_box[0] = _gojsonnet.evaluate_file(
                str(source_path),
                jpathdir=jpathdir,
            )
        except Exception as exc:
            error_box[0] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(
            f"Jsonnet compilation timed out after {timeout_seconds}s "
            f"(Python backend)"
        )

    if error_box[0] is not None:
        raise CompilationError(
            str(error_box[0]), source_path=str(source_path)
        )

    if result_box[0] is None:
        raise CompilationError(
            "Jsonnet evaluation returned no output (Python backend)",
            source_path=str(source_path),
        )

    return result_box[0]
