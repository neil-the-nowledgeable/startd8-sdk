"""Repair staging area management (REQ-RPL-006).

Provides isolated staging directories for repair operations so that
repairs are applied to copies, not originals. On success, repaired
files are atomically swapped into the project.

Security: dirs created with mode 0o700, symlink inputs rejected,
paths validated via ``security.sanitize_path()`` (R3-S4).

Atomic writes delegate to ``utils/file_operations.atomic_write()`` (R3-S3).
"""

from __future__ import annotations

import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, Optional

from ..logging_config import get_logger
from ..security import sanitize_path
from ..utils.file_operations import atomic_write
from .models import StagingError

logger = get_logger(__name__)

# Mode for staging directories (R1-S7)
_STAGING_DIR_MODE = 0o700


@dataclass
class StagingContext:
    """Context manager for an isolated staging directory.

    Copies files into the staging dir, yields paths for repair, and
    cleans up on success (retains on failure for debugging).

    Attributes:
        staging_dir: Path to the staging directory.
        files: Map of original path → staging copy content.
        file_paths: Map of original path → staging copy path.
    """

    staging_dir: Path
    files: Dict[Path, str] = field(default_factory=dict)
    file_paths: Dict[Path, Path] = field(default_factory=dict)
    _retain_on_failure: bool = True
    _applied: bool = False

    @property
    def paths(self) -> list[Path]:
        """List of staged file paths."""
        return list(self.file_paths.values())

    def write_repaired(self, repaired_files: Dict[Path, str]) -> None:
        """Write repaired content to staging copies.

        Args:
            repaired_files: Map of original path → repaired content.
        """
        for orig_path, content in repaired_files.items():
            staged_path = self.file_paths.get(orig_path)
            if staged_path is None:
                logger.warning(
                    "No staging copy for %s — skipping write", orig_path,
                )
                continue
            try:
                staged_path.write_text(content, encoding="utf-8")
            except OSError as exc:
                raise StagingError(
                    f"Failed to write repaired content to staging: {exc}",
                    file_path=str(staged_path),
                    original_error=exc,
                )

    def apply_atomic(self) -> None:
        """Atomically swap staged files into original locations (R1-S4, R3-S3).

        Delegates to ``atomic_write()`` for each file. On failure,
        already-applied files have backups from ``atomic_write(backup=True)``.
        """
        applied: list[Path] = []
        last_path: str = ""
        try:
            for orig_path, staged_path in self.file_paths.items():
                last_path = str(orig_path)
                if not staged_path.exists():
                    continue
                content = staged_path.read_bytes()
                atomic_write(orig_path, content, mode="wb", backup=True)
                applied.append(orig_path)
            self._applied = True
        except OSError as exc:
            raise StagingError(
                f"Atomic swap failed after {len(applied)} files: {exc}",
                file_path=last_path,
                original_error=exc,
            )


@contextmanager
def create_staging(
    files: Dict[Path, str],
    staging_root: Optional[Path],
    feature_name: str,
    attempt: int,
    project_root: Optional[Path] = None,
) -> Generator[StagingContext, None, None]:
    """Create an isolated staging directory with file copies.

    Args:
        files: Map of file path → content to copy into staging.
        staging_root: Root directory for staging. Uses project_root/.startd8/repair
            if None.
        feature_name: Feature name for directory naming.
        attempt: Attempt number for directory naming.
        project_root: Project root for path validation.

    Yields:
        StagingContext with files copied into the staging directory.

    Raises:
        StagingError: On path validation or I/O failure.
    """
    if staging_root is None:
        if project_root:
            staging_root = project_root / ".startd8" / "repair"
        else:
            staging_root = Path(".startd8") / "repair"

    # Create unique staging directory
    timestamp = int(time.time() * 1000)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in feature_name)
    staging_dir = staging_root / safe_name / f"{attempt}_{timestamp}"

    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.chmod(_STAGING_DIR_MODE)
    except OSError as exc:
        raise StagingError(
            f"Failed to create staging directory: {exc}",
            file_path=str(staging_dir),
            original_error=exc,
        )

    ctx = StagingContext(staging_dir=staging_dir)
    success = False

    try:
        # Copy files into staging
        for file_path, content in files.items():
            # R1-S7: Reject symlink inputs
            if file_path.is_symlink():
                raise StagingError(
                    f"Symlink input rejected: {file_path}",
                    file_path=str(file_path),
                )

            # R3-S4: Path validation via sanitize_path()
            if project_root:
                try:
                    sanitize_path(str(file_path), base_dir=project_root)
                except Exception as exc:
                    raise StagingError(
                        f"Path validation failed for {file_path}: {exc}",
                        file_path=str(file_path),
                        original_error=exc,
                    )

            # Create staged copy
            staged_path = staging_dir / file_path.name
            try:
                staged_path.write_text(content, encoding="utf-8")
            except OSError as exc:
                raise StagingError(
                    f"Failed to copy file to staging: {exc}",
                    file_path=str(staged_path),
                    original_error=exc,
                )

            ctx.files[file_path] = content
            ctx.file_paths[file_path] = staged_path

        yield ctx
        success = True

    finally:
        if success:
            _cleanup_staging_dir(staging_dir)
        # On failure: retain staging dir for debugging (R1-S6)


def cleanup_expired_staging(staging_root: Path, retention_hours: int = 24) -> int:
    """Remove staging directories older than the retention period (R1-S6).

    Args:
        staging_root: Root staging directory to scan.
        retention_hours: Maximum age in hours.

    Returns:
        Number of directories removed.
    """
    if not staging_root.exists():
        return 0

    cutoff = time.time() - (retention_hours * 3600)
    removed = 0

    for feature_dir in staging_root.iterdir():
        if not feature_dir.is_dir():
            continue
        for attempt_dir in feature_dir.iterdir():
            if not attempt_dir.is_dir():
                continue
            try:
                mtime = attempt_dir.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(attempt_dir)
                    removed += 1
            except OSError:
                logger.debug("Failed to remove expired staging dir %s", attempt_dir)

        # Remove empty feature dirs
        try:
            if feature_dir.is_dir() and not any(feature_dir.iterdir()):
                feature_dir.rmdir()
        except OSError:
            logger.debug("Failed to remove empty feature dir %s", feature_dir)

    return removed


def _cleanup_staging_dir(staging_dir: Path) -> None:
    """Remove a staging directory."""
    try:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
    except OSError as exc:
        logger.warning("Failed to clean up staging dir %s: %s", staging_dir, exc)
