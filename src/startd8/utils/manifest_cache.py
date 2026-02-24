"""
Manifest cache — batch generation and digest-based caching for code manifests.

Provides project-wide scanning, cache storage in .startd8/manifests/,
and staleness detection for CI integration.

See docs/design/CODE_MANIFEST_PLAN.md Section 6 for caching strategy.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional, Union

from startd8.logging_config import get_logger
from startd8.utils.code_manifest import (
    FileManifest,
    SCHEMA_VERSION,
    generate_file_manifest,
)

logger = get_logger(__name__)

# Directories to skip during batch scanning
_SKIP_DIRS: set[str] = {
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    ".egg-info",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".startd8",
    "dist",
    "build",
    ".eggs",
}

_INDEX_FILE = "_index.json"

# Python version tag for cache key — symtable behaviour can differ across
# interpreter versions (e.g. __annotate__ scopes in 3.10+, PEP 709
# comprehension inlining in 3.12).  Including the major.minor version
# prevents stale cache hits when the interpreter is upgraded.
_PYTHON_VERSION_TAG = f"{sys.version_info.major}.{sys.version_info.minor}"


def _default_cache_dir(project_root: Path) -> Path:
    return project_root / ".startd8" / "manifests"


def _default_source_root(project_root: Path) -> Path:
    src_dir = project_root / "src"
    if src_dir.is_dir():
        return src_dir
    return project_root


def _should_skip_dir(name: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if name in _SKIP_DIRS:
        return True
    if name.endswith(".egg-info"):
        return True
    return False


def _scan_python_files(root: Path) -> list[Path]:
    """Recursively scan for .py files, skipping excluded directories."""
    files: list[Path] = []
    if not root.is_dir():
        return files

    for item in sorted(root.iterdir()):
        if item.is_dir():
            if not _should_skip_dir(item.name):
                files.extend(_scan_python_files(item))
        elif item.is_file() and item.suffix == ".py":
            files.append(item)

    return files


def _compute_file_digest(file_path: Path) -> str:
    """Compute SHA-256 digest of a file's content."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_index(
    cache_dir: Path,
    mode: str = "static",
) -> dict[str, str]:
    """Load the cache index mapping file paths to digests.

    The index stores a ``_meta`` key with ``schema_version``,
    ``python_version``, and ``mode``.  If any differs from the current
    runtime, the entire index is discarded so that all manifests are
    regenerated.
    """
    index_path = cache_dir / _INDEX_FILE
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load manifest cache index; rebuilding")
        return {}

    # Validate meta — discard on version mismatch
    meta = data.pop("_meta", None)
    if not isinstance(meta, dict):
        logger.info("Cache index missing _meta; rebuilding")
        return {}
    if meta.get("schema_version") != SCHEMA_VERSION:
        logger.info(
            "Schema version changed (%s -> %s); rebuilding cache",
            meta.get("schema_version"),
            SCHEMA_VERSION,
        )
        return {}
    if meta.get("python_version") != _PYTHON_VERSION_TAG:
        logger.info(
            "Python version changed (%s -> %s); rebuilding cache",
            meta.get("python_version"),
            _PYTHON_VERSION_TAG,
        )
        return {}
    if meta.get("mode", "static") != mode:
        logger.info(
            "Mode changed (%s -> %s); rebuilding cache",
            meta.get("mode", "static"),
            mode,
        )
        return {}

    return data


def _save_index(
    cache_dir: Path,
    index: dict[str, str],
    mode: str = "static",
) -> None:
    """Save the cache index with version metadata."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / _INDEX_FILE
    payload = {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "python_version": _PYTHON_VERSION_TAG,
            "mode": mode,
        },
        **index,
    }
    index_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def _cache_key(digest: str) -> str:
    """Derive a cache filename from a digest."""
    # Strip the 'sha256:' prefix for the filename
    hex_part = digest.split(":", 1)[-1] if ":" in digest else digest
    return f"sha256_{hex_part}.json"


def _load_cached_manifest(cache_dir: Path, digest: str) -> Optional[FileManifest]:
    """Load a cached manifest by digest if it exists."""
    cache_path = cache_dir / _cache_key(digest)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return FileManifest.model_validate(data)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("Failed to load cached manifest %s: %s", cache_path, exc)
        return None


def _save_cached_manifest(cache_dir: Path, manifest: FileManifest) -> None:
    """Save a manifest to the cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / _cache_key(manifest.digest)
    cache_path.write_text(
        json.dumps(manifest.model_dump(), indent=2), encoding="utf-8"
    )


def generate_project_manifests(
    project_root: Union[Path, str],
    source_root: Union[Path, str, None] = None,
    cache_dir: Union[Path, str, None] = None,
    mode: str = "static",
) -> dict[str, FileManifest]:
    """
    Generate manifests for all Python files in a project.

    Args:
        project_root: Project root directory.
        source_root: Source directory to scan (default: project_root/src or project_root).
        cache_dir: Cache directory (default: project_root/.startd8/manifests).
        mode: Analysis mode — ``"static"`` (default), ``"ast_only"``,
            ``"introspect"`` (adds runtime introspection), or
            ``"bytecode"`` (adds call graph extraction).

    Returns:
        Dict mapping relative file paths to FileManifest instances.
        Uses cached manifests when source digest matches.
    """
    project_root = Path(project_root).resolve()
    source_root_path = (
        Path(source_root).resolve()
        if source_root
        else _default_source_root(project_root)
    )
    cache_dir_path = (
        Path(cache_dir).resolve() if cache_dir else _default_cache_dir(project_root)
    )

    py_files = _scan_python_files(source_root_path)
    manifests: dict[str, FileManifest] = {}
    index: dict[str, str] = {}
    cache_hits = 0
    cache_misses = 0

    for file_path in py_files:
        try:
            relative = str(file_path.relative_to(project_root))
        except ValueError:
            relative = str(file_path)

        try:
            digest = _compute_file_digest(file_path)
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            continue

        # Try cache — validate digest and schema version
        cached = _load_cached_manifest(cache_dir_path, digest)
        if (
            cached is not None
            and cached.digest == digest
            and cached.schema_version == SCHEMA_VERSION
        ):
            manifests[relative] = cached
            index[relative] = digest
            cache_hits += 1
            continue

        # Generate fresh
        try:
            manifest = generate_file_manifest(file_path, project_root, mode=mode)
            manifests[relative] = manifest
            index[relative] = manifest.digest
            _save_cached_manifest(cache_dir_path, manifest)
            cache_misses += 1
        except Exception as exc:
            logger.warning("Failed to generate manifest for %s: %s", file_path, exc)
            continue

    # Save index
    _save_index(cache_dir_path, index, mode=mode)

    logger.info(
        "Manifest generation complete: %d files (%d cached, %d generated)",
        len(manifests),
        cache_hits,
        cache_misses,
    )
    return manifests


def check_manifests_fresh(
    project_root: Union[Path, str],
    source_root: Union[Path, str, None] = None,
    cache_dir: Union[Path, str, None] = None,
    mode: str = "static",
) -> tuple[bool, list[str]]:
    """
    Check if cached manifests are up-to-date.

    Returns:
        (all_fresh, stale_files) — True if all manifests are current,
        plus list of files that need regeneration.
    """
    project_root = Path(project_root).resolve()
    source_root_path = (
        Path(source_root).resolve()
        if source_root
        else _default_source_root(project_root)
    )
    cache_dir_path = (
        Path(cache_dir).resolve() if cache_dir else _default_cache_dir(project_root)
    )

    index = _load_index(cache_dir_path, mode=mode)
    py_files = _scan_python_files(source_root_path)
    stale_files: list[str] = []

    for file_path in py_files:
        try:
            relative = str(file_path.relative_to(project_root))
        except ValueError:
            relative = str(file_path)

        stored_digest = index.get(relative)
        if stored_digest is None:
            stale_files.append(relative)
            continue

        try:
            current_digest = _compute_file_digest(file_path)
        except OSError:
            stale_files.append(relative)
            continue

        if stored_digest != current_digest:
            stale_files.append(relative)

    return (len(stale_files) == 0, stale_files)
