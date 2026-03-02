"""
Mixin library discovery and Jsonnet toolchain detection (DC-000, DC-004).
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

from startd8.exceptions import ConfigurationError
from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MixinContext:
    """Resolved paths for the startd8-mixin/ directory."""

    mixin_dir: Path
    panels_path: Path
    variables_path: Path
    config_path: Path
    dashboards_dir: Path
    vendor_dir: Path
    mixin_libsonnet: Path


@dataclass
class ToolchainInfo:
    """Detected Jsonnet compilation toolchain."""

    backend: Literal["binary", "python"]
    version: str
    binary_path: Optional[str] = None  # For binary backend


_REQUIRED_FILES = [
    "lib/panels.libsonnet",
    "lib/variables.libsonnet",
    "config.libsonnet",
]


def discover_mixin(search_paths: Optional[List[Path]] = None) -> MixinContext:
    """DC-000: Locate and validate startd8-mixin/ directory.

    Search order:
    1. Explicit search_paths (if provided)
    2. SDK package root (Path(__file__).parents[3] / "startd8-mixin")
    3. Current working directory / "startd8-mixin"

    Raises ConfigurationError if mixin directory not found, required files
    missing, or vendor/ missing/empty.
    """
    candidates: List[Path] = []

    if search_paths:
        candidates.extend(search_paths)

    # SDK package root (src/startd8/dashboard_creator -> repo root)
    sdk_root = Path(__file__).resolve().parents[3]
    candidates.append(sdk_root / "startd8-mixin")

    # Current working directory
    candidates.append(Path.cwd() / "startd8-mixin")

    mixin_dir: Optional[Path] = None
    for candidate in candidates:
        logger.debug("Checking mixin candidate: %s", candidate)
        if candidate.is_dir():
            mixin_dir = candidate.resolve()
            logger.debug("Found mixin directory: %s", mixin_dir)
            break

    if mixin_dir is None:
        searched = ", ".join(str(c) for c in candidates)
        raise ConfigurationError(
            f"startd8-mixin/ directory not found. Searched: {searched}"
        )

    # Validate required files
    missing = [f for f in _REQUIRED_FILES if not (mixin_dir / f).is_file()]
    if missing:
        raise ConfigurationError(
            f"startd8-mixin/ is incomplete. Missing files: {', '.join(missing)}"
        )

    # Validate vendor/
    vendor_dir = mixin_dir / "vendor"
    if not vendor_dir.is_dir() or not any(vendor_dir.iterdir()):
        raise ConfigurationError(
            "startd8-mixin/vendor/ is missing or empty. "
            "Run 'jb install' in startd8-mixin/ to install dependencies."
        )

    return MixinContext(
        mixin_dir=mixin_dir,
        panels_path=mixin_dir / "lib" / "panels.libsonnet",
        variables_path=mixin_dir / "lib" / "variables.libsonnet",
        config_path=mixin_dir / "config.libsonnet",
        dashboards_dir=mixin_dir / "dashboards",
        vendor_dir=vendor_dir,
        mixin_libsonnet=mixin_dir / "mixin.libsonnet",
    )


def detect_toolchain() -> ToolchainInfo:
    """DC-004: Detect jsonnet compilation toolchain.

    Check order:
    1. jsonnet binary on $PATH (shutil.which("jsonnet"))
    2. _gojsonnet Python package (import _gojsonnet)

    Raises ConfigurationError with installation instructions if neither found.
    """
    # Try binary first
    binary_path = shutil.which("jsonnet")
    if binary_path:
        version = _get_binary_version(binary_path)
        logger.debug("Using jsonnet binary: %s (%s)", binary_path, version)
        return ToolchainInfo(
            backend="binary", version=version, binary_path=binary_path
        )

    # Try Python package
    try:
        import _gojsonnet  # type: ignore[import-untyped]

        version = getattr(_gojsonnet, "__version__", "unknown")
        logger.debug("Using _gojsonnet Python package (%s)", version)
        return ToolchainInfo(backend="python", version=version)
    except ImportError:
        pass

    raise ConfigurationError(
        "No Jsonnet toolchain found. Install one of:\n"
        "  - Binary: brew install jsonnet  (or go install github.com/google/go-jsonnet/cmd/jsonnet@latest)\n"
        "  - Python: pip install gojsonnet"
    )


def _get_binary_version(binary_path: str) -> str:
    """Extract version from jsonnet binary."""
    try:
        result = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or result.stderr.strip() or "unknown"
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"
