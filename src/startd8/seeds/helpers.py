"""
Seed helper utilities — checksums, context files, onboarding injection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "sha256_file_hex",
    "context_files_with_checksums",
    "ensure_onboarding_in_context_files",
]


def sha256_file_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def context_files_with_checksums(
    context_files: Optional[List[str]],
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build context_files list with optional checksums for seed/handoff."""
    if not context_files:
        return []
    result: List[Dict[str, Any]] = []
    base = base_dir or Path.cwd()
    for p in context_files:
        entry: Dict[str, Any] = {"path": p}
        try:
            resolved = Path(p) if Path(p).is_absolute() else base / p
            if resolved.exists() and resolved.is_file():
                content = resolved.read_bytes()
                entry["checksum"] = hashlib.sha256(content).hexdigest()
            else:
                entry["checksum"] = None
        except OSError:
            entry["checksum"] = None
        result.append(entry)
    return result


def ensure_onboarding_in_context_files(
    context_files_list: Optional[List[Dict[str, Any]]],
    onboarding: Optional[Dict[str, Any]],
    output_dir: Path,
) -> None:
    """REQ-PI-014: Append onboarding-metadata.json to context_files if missing."""
    if not context_files_list or not onboarding:
        return
    existing_names = {
        entry.get("path", "").rsplit("/", 1)[-1] for entry in context_files_list
    }
    if "onboarding-metadata.json" not in existing_names:
        ob_path = output_dir / "onboarding-metadata.json"
        if ob_path.exists():
            context_files_list.append(
                {
                    "path": str(ob_path),
                    "checksum": sha256_file_hex(ob_path),
                }
            )
            logger.info(
                "REQ-PI-014: added onboarding-metadata.json to context_files"
            )
