"""Complexity signal extraction utilities.

Provides manifest-based cross-file edge detection and feature-level
signal extraction for Prime Contractor routing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import TaskComplexitySignals

# Maximum number of .py files to scan when computing blast_radius.
_BLAST_RADIUS_SCAN_LIMIT = 500


def detect_cross_file_edges(
    target_files: List[str],
    manifest_registry: Any,
    flatten_fn: Callable[[Any], Any],
) -> bool:
    """Check whether any target files have call edges to each other.

    Port of ``_detect_cross_file_edges`` from ``context_seed_handlers.py``.

    Args:
        target_files: Relative file paths (must have ``len > 1``).
        manifest_registry: Object with ``call_graph()`` and ``get(path)``
            methods.
        flatten_fn: Callable that flattens a manifest's ``elements`` list.

    Returns:
        ``True`` if any element in one target file calls an element in
        another target file.
    """
    try:
        forward = manifest_registry.call_graph()
        fqn_to_file: Dict[str, str] = {}
        for tf in target_files:
            m = manifest_registry.get(tf)
            if m:
                for e in flatten_fn(m.elements):
                    if e.fqn:
                        fqn_to_file[e.fqn] = tf
        for fqn, file_path in fqn_to_file.items():
            for callee in forward.get(fqn, set()):
                callee_file = fqn_to_file.get(callee)
                if callee_file and callee_file != file_path:
                    return True
    except (AttributeError, TypeError, KeyError):
        pass
    return False


def extract_signals_from_feature(
    feature: Any,
    project_root: Path,
    manifest: Optional[Any] = None,
) -> TaskComplexitySignals:
    """Extract complexity signals from a Prime Contractor feature spec.

    Designed for ``PrimeContractorWorkflow.develop_feature()`` integration.
    Never raises — all I/O is wrapped in try/except.

    Args:
        feature: Object with ``target_files`` (list[str]),
            ``description`` (str), and ``metadata`` (dict) attributes.
        project_root: Absolute path to the project root.
        manifest: Optional manifest registry for deeper analysis.
            When ``None``, manifest-dependent signals default to 0/False.

    Returns:
        Populated ``TaskComplexitySignals`` instance.
    """
    target_files: List[str] = []
    description: str = ""
    metadata: Dict[str, Any] = {}

    try:
        target_files = list(getattr(feature, "target_files", None) or [])
    except (TypeError, ValueError):
        pass

    try:
        description = str(getattr(feature, "description", "") or "")
    except (TypeError, ValueError):
        pass

    try:
        metadata = dict(getattr(feature, "metadata", None) or {})
    except (TypeError, ValueError):
        pass

    target_file_count = max(len(target_files), 1)

    # edit_mode: "create" if no target files exist on disk, "edit" if any do
    edit_mode = "create"
    try:
        for tf in target_files:
            candidate = project_root / tf
            if candidate.is_file():
                edit_mode = "edit"
                break
    except (OSError, TypeError):
        pass

    # estimated_loc: prefer metadata, else rough heuristic from description
    estimated_loc = 0
    try:
        estimated_loc = int(metadata.get("estimated_loc", 0))
    except (TypeError, ValueError):
        pass
    if estimated_loc <= 0:
        estimated_loc = max(len(description) // 3, 1)

    # blast_radius: count .py files under project_root that import any target
    blast_radius = _compute_blast_radius(target_files, project_root)

    # has_cross_file_edges: True if multi-file and any target imports another
    has_cross_file_edges = False
    if target_file_count > 1:
        has_cross_file_edges = _check_cross_imports(target_files, project_root)

    # Manifest-dependent signals
    caller_count = 0
    has_dynamic_dispatch = False
    is_closure = False
    mro_depth = 0
    unresolved_call_count = 0
    manifest_coverage = "none"

    if manifest is not None:
        try:
            manifest_coverage = _compute_manifest_coverage(
                target_files, manifest
            )
        except (AttributeError, TypeError):
            pass

    return TaskComplexitySignals(
        blast_radius=blast_radius,
        caller_count=caller_count,
        has_dynamic_dispatch=has_dynamic_dispatch,
        is_closure=is_closure,
        estimated_loc=estimated_loc,
        target_file_count=target_file_count,
        edit_mode=edit_mode,
        mro_depth=mro_depth,
        unresolved_call_count=unresolved_call_count,
        has_cross_file_edges=has_cross_file_edges,
        manifest_coverage=manifest_coverage,
    )


def _compute_blast_radius(
    target_files: List[str], project_root: Path
) -> int:
    """Count .py files under *project_root* that import any target file.

    Bounded scan: stops after ``_BLAST_RADIUS_SCAN_LIMIT`` files.
    """
    if not target_files:
        return 0

    # Build set of module-like names from target file stems
    target_stems = set()
    for tf in target_files:
        try:
            stem = Path(tf).stem
            if stem and stem != "__init__":
                target_stems.add(stem)
        except (TypeError, ValueError):
            pass

    if not target_stems:
        return 0

    count = 0
    scanned = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(project_root):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, fname)
                # Skip target files themselves
                try:
                    rel = os.path.relpath(fpath, project_root)
                except ValueError:
                    continue
                if rel in target_files:
                    continue

                scanned += 1
                if scanned > _BLAST_RADIUS_SCAN_LIMIT:
                    return count

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(8192)  # Only scan first 8KB
                    for stem in target_stems:
                        if f"import {stem}" in content or f"from {stem}" in content:
                            count += 1
                            break
                except OSError:
                    pass
    except OSError:
        pass

    return count


def _check_cross_imports(
    target_files: List[str], project_root: Path
) -> bool:
    """Check if any target file imports another target file (lightweight)."""
    if len(target_files) < 2:
        return False

    target_stems = set()
    for tf in target_files:
        try:
            stem = Path(tf).stem
            if stem:
                target_stems.add(stem)
        except (TypeError, ValueError):
            pass

    for tf in target_files:
        try:
            fpath = project_root / tf
            if not fpath.is_file():
                continue
            content = fpath.read_text(encoding="utf-8", errors="ignore")[:8192]
            other_stems = target_stems - {Path(tf).stem}
            for stem in other_stems:
                if f"import {stem}" in content or f"from {stem}" in content:
                    return True
        except OSError:
            pass
    return False


def _compute_manifest_coverage(
    target_files: List[str], manifest: Any
) -> str:
    """Return 'full' if all target files are in the manifest, else 'none'."""
    if not target_files:
        return "none"
    for tf in target_files:
        if not manifest.get(tf):
            return "none"
    return "full"
