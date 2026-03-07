"""
Copy Detection - Identifies identical-copy tasks for Phase 0 early-exit.

Scans feature descriptions for duplication signals and validates that the
task is a pure file copy (not a copy-and-modify). Used by PrimeContractor
to bypass LLM generation when a task simply duplicates a predecessor's output.

Requirements: REQ-MP-1000, REQ-MP-1001.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Signals that indicate an identical-copy task.
_DUPLICATION_SIGNALS = (
    "identical copy",
    "duplicated identically",
    "exact copy",
    "same as",
    "mirror of",
)

# Signals that indicate modification — if present alongside duplication
# signals, the task is copy_and_modify, not file_copy.
_MODIFICATION_SIGNALS = (
    "with changes",
    "adapted for",
    "modified to",
)


@dataclass
class CopySource:
    """Descriptor for a file-copy source."""

    predecessor_id: str
    source_file: str
    workspace_root: str = ""


def detect_copy_task(feature, predecessor: "Optional[object]" = None) -> Optional[CopySource]:
    """Detect whether *feature* is an identical-copy task.

    Args:
        feature: A ``FeatureSpec`` instance.
        predecessor: Optional predecessor ``FeatureSpec`` used for fallback
            inference of ``copy_source_file`` when not explicitly set.

    Returns:
        A :class:`CopySource` if the feature qualifies, otherwise ``None``.
    """
    # If copy_source_task_id is already set, trust it.
    if feature.copy_source_task_id is not None:
        source_file = feature.copy_source_file
        if source_file is None and predecessor is not None:
            target_files = getattr(predecessor, "target_files", [])
            if len(target_files) == 1:
                source_file = target_files[0]
        return CopySource(
            predecessor_id=feature.copy_source_task_id,
            source_file=source_file or "",
        )

    description = (feature.description or "").lower()

    # Check for duplication signals.
    has_duplication = any(signal in description for signal in _DUPLICATION_SIGNALS)
    if not has_duplication:
        return None

    # Check for modification signals — if both present, this is
    # copy_and_modify, not file_copy.
    has_modification = any(signal in description for signal in _MODIFICATION_SIGNALS)
    if has_modification:
        logger.debug(
            "Feature '%s' has both duplication and modification signals — "
            "not a file_copy task",
            getattr(feature, "name", feature.id),
        )
        return None

    # Require exactly one dependency.
    dependencies = getattr(feature, "dependencies", [])
    if len(dependencies) != 1:
        logger.debug(
            "Feature '%s' has %d dependencies (need exactly 1 for copy detection)",
            getattr(feature, "name", feature.id),
            len(dependencies),
        )
        return None

    predecessor_id = dependencies[0]

    # Infer source file from predecessor if not explicitly set.
    source_file = feature.copy_source_file
    if source_file is None and predecessor is not None:
        target_files = getattr(predecessor, "target_files", [])
        if len(target_files) == 1:
            source_file = target_files[0]

    return CopySource(
        predecessor_id=predecessor_id,
        source_file=source_file or "",
    )


def validate_copy_path(source_file: str, workspace_root: str) -> Path:
    """Validate and resolve *source_file* within *workspace_root*.

    Raises:
        ValueError: If the resolved path escapes *workspace_root* (path
            traversal attempt).
    """
    workspace = Path(workspace_root).resolve()
    resolved = Path(workspace_root, source_file).resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError(
            f"Path traversal detected: '{source_file}' resolves to "
            f"'{resolved}' which is outside workspace '{workspace}'"
        )
    return resolved
