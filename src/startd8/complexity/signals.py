"""Complexity signal extraction utilities.

Provides manifest-based cross-file edge detection and signal extraction
for Artisan (chunk-level), Prime Contractor (feature-level), and Micro
Prime (element-level) routing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from startd8.logging_config import get_logger

from .models import TaskComplexitySignals

logger = get_logger(__name__)

# Maximum number of .py files to scan when computing blast_radius.
_BLAST_RADIUS_SCAN_LIMIT = 500

# Directories excluded from blast radius scans — historical artifacts,
# generated outputs, and tool state inflate the count without representing
# live source.  Run-027 Kaizen: `logger` stem matched 35+ files across
# archive/ and .cap-dev-pipe/pipeline-output/, triggering false COMPLEX.
# Run-045 Kaizen: `prime-contractor-run-*` old output dirs inflated
# blast_radius from 4 to 7 for PI-001 (logger.py), forcing false COMPLEX.
_BLAST_RADIUS_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".startd8",
    ".cap-dev-pipe",
    ".claude",
    "archive",
    "generated",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
})

# Directory prefixes that indicate non-source artifacts.  Unlike the exact
# set above, these are matched with str.startswith() to catch timestamped
# output dirs like prime-contractor-run-2026-02-26-10-00/.
_BLAST_RADIUS_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "prime-contractor-run-",
    "artisan-run-",
    "run-",
)


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
    except (AttributeError, TypeError, KeyError) as exc:
        logger.debug("Cross-file edge detection failed: %s", exc)
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

    # file_extension: use the first target file's extension for routing
    file_extension = ".py"
    if target_files:
        try:
            ext = Path(target_files[0]).suffix
            if ext:
                file_extension = ext.lower()
        except (TypeError, ValueError):
            pass

    # edit_mode: "create" if no target files exist on disk, "edit" if any do.
    #
    # Pipeline-poisoning guard: when a ForwardManifest covers a target file
    # the file will be (re)generated from a skeleton — the Micro Prime
    # file-whole path starts from the skeleton every time, so prior run
    # outputs on disk are irrelevant.  Treat manifest-covered files as
    # "create" regardless of filesystem state.
    edit_mode = "create"
    manifest_covered_files: set[str] = set()
    if manifest is not None:
        try:
            file_specs = getattr(manifest, "file_specs", None) or {}
            manifest_covered_files = set(file_specs.keys())
        except (TypeError, AttributeError):
            pass

    try:
        for tf in target_files:
            if tf in manifest_covered_files:
                continue  # Manifest-covered → always "create"
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

    # blast_radius: count .py files under project_root that import any target.
    # Exclude manifest-covered files — they are being regenerated in this
    # run, so their imports are pipeline artifacts, not live coupling.
    blast_radius = _compute_blast_radius(
        target_files, project_root,
        exclude_files=manifest_covered_files,
    )

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
        file_extension=file_extension,
    )


def _compute_blast_radius(
    target_files: List[str],
    project_root: Path,
    exclude_files: Optional[set] = None,
) -> int:
    """Count .py files under *project_root* that import any target file.

    Bounded scan: stops after ``_BLAST_RADIUS_SCAN_LIMIT`` files.

    Uses path-qualified import patterns to avoid false positives from
    common module names (e.g. ``logger``, ``utils``, ``config``).  For a
    target ``src/emailservice/logger.py``, matches:
    - ``from emailservice.logger import ...``
    - ``from emailservice import logger``
    - ``import emailservice.logger``
    In addition to the legacy bare-stem match ``import logger`` for
    flat-layout projects.

    Excludes non-source directories (archives, generated output, tool
    state) via ``_BLAST_RADIUS_EXCLUDED_DIRS`` — Run-027 Kaizen showed
    these inflating blast_radius from 0 to 35+ for ``logger.py``.

    Pipeline-poisoning guard: files listed in ``exclude_files`` (typically
    manifest-covered files being regenerated in the same run) are not
    counted — their imports are pipeline artifacts, not live coupling.
    """
    if not target_files:
        return 0

    # Build qualified and bare import patterns for each target file.
    # Example for "src/emailservice/logger.py":
    #   qualified: ["emailservice.logger", "emailservice import logger"]
    #   bare:      ["import logger", "from logger"]
    import_patterns: List[str] = []
    for tf in target_files:
        try:
            p = Path(tf)
            stem = p.stem
            if not stem or stem == "__init__":
                continue

            # Qualified patterns from parent package(s)
            parts = list(p.with_suffix("").parts)
            # Strip leading "src" — it's a filesystem convention, not a package
            if parts and parts[0] == "src":
                parts = parts[1:]
            if len(parts) >= 2:
                # "emailservice.logger" (dotted module path)
                dotted = ".".join(parts)
                import_patterns.append(f"import {dotted}")
                import_patterns.append(f"from {dotted}")
                # "from emailservice import logger"
                parent_dotted = ".".join(parts[:-1])
                import_patterns.append(f"from {parent_dotted} import {stem}")
            # Bare stem fallback for flat layouts
            import_patterns.append(f"import {stem}")
            import_patterns.append(f"from {stem} import")
        except (TypeError, ValueError):
            pass

    if not import_patterns:
        return 0

    count = 0
    scanned = 0
    try:
        for dirpath, dirnames, filenames in os.walk(project_root):
            # Prune excluded directories in-place (modifying dirnames
            # prevents os.walk from descending into them).
            dirnames[:] = [
                d for d in dirnames
                if d not in _BLAST_RADIUS_EXCLUDED_DIRS
                and not d.startswith(_BLAST_RADIUS_EXCLUDED_PREFIXES)
            ]

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
                # Pipeline-poisoning guard: skip manifest-covered files
                if exclude_files and rel in exclude_files:
                    continue

                scanned += 1
                if scanned > _BLAST_RADIUS_SCAN_LIMIT:
                    return count

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(8192)  # Only scan first 8KB
                    for pattern in import_patterns:
                        if pattern in content:
                            count += 1
                            break
                except OSError as exc:
                    logger.debug("Blast radius scan: failed to read %s: %s", fpath, exc)
    except OSError as exc:
        logger.debug("Blast radius scan: os.walk failed: %s", exc)

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
        except OSError as exc:
            logger.debug("Cross-import check: failed to read %s: %s", tf, exc)
    return False


def _compute_manifest_coverage(
    target_files: List[str], manifest: Any
) -> str:
    """Return 'full' if all target files are in the manifest, else 'none'.

    Supports both dict-like manifests (ManifestRegistry) and Pydantic
    ForwardManifest objects (lookup via ``file_specs`` attribute).
    """
    if not target_files:
        return "none"
    # ForwardManifest (Pydantic) has .file_specs dict; ManifestRegistry has .get()
    file_specs = getattr(manifest, "file_specs", None)
    if file_specs is not None:
        for tf in target_files:
            if tf not in file_specs:
                return "none"
        return "full"
    # Fallback: dict-like .get() (ManifestRegistry, raw dict)
    for tf in target_files:
        try:
            if not manifest.get(tf):
                return "none"
        except AttributeError:
            return "none"
    return "full"


# ── Chunk-level extraction (Artisan, REQ-MP-800) ────────────────────────


def extract_signals_from_chunk(
    chunk: Any,
    manifest_registry: Any,
) -> TaskComplexitySignals:
    """Extract complexity signals from an Artisan chunk + manifest registry.

    Port of ``context_seed/design_support._extract_complexity_signals()``.
    Never raises — all lookups wrapped in try/except with safe defaults.

    Args:
        chunk: A ``DevelopmentChunk``-like object with ``metadata`` dict
            and ``file_targets`` list.
        manifest_registry: A ``ManifestRegistry`` instance, or ``None``
            when manifest data is unavailable.

    Returns:
        Populated ``TaskComplexitySignals`` instance.
    """
    meta = getattr(chunk, "metadata", {}) or {}
    _chunk_id = getattr(chunk, "chunk_id", "?")

    # --- Signals from chunk metadata (populated by earlier enrichment) ---
    blast_radius = 0
    caller_count = 0
    has_cross_file_edges = False
    manifest_coverage = "none"

    try:
        cg_callers = meta.get("_call_graph_callers", [])
        if cg_callers:
            blast_radius = max(
                (entry.get("blast_radius", 0) for entry in cg_callers),
                default=0,
            )
            caller_count = sum(
                len(entry.get("direct_callers", []))
                for entry in cg_callers
            )
    except (TypeError, AttributeError) as exc:
        logger.debug(
            "CMR: call graph caller extraction failed for %s: %s",
            _chunk_id, exc,
        )

    # Edit mode from classification (normalized at extraction boundary)
    edit_mode = "unknown"
    try:
        edit_mode_dict = meta.get("_edit_mode")
        if edit_mode_dict and isinstance(edit_mode_dict, dict):
            edit_mode = str(edit_mode_dict.get("mode", "unknown")).strip().lower()
        elif isinstance(edit_mode_dict, str):
            edit_mode = edit_mode_dict.strip().lower()
    except (TypeError, AttributeError) as exc:
        logger.debug(
            "CMR: edit mode extraction failed for %s: %s", _chunk_id, exc,
        )

    # Estimated LOC from seed task
    estimated_loc = 0
    try:
        estimated_loc = int(meta.get("estimated_loc", 0) or 0)
    except (ValueError, TypeError):
        logger.debug("estimated_loc coercion failed", exc_info=True)

    # Target file count
    target_files = getattr(chunk, "file_targets", []) or []
    target_file_count = max(len(target_files), 1)

    # --- Signals from manifest registry (Phase 5/6 data) ---
    has_dynamic_dispatch = False
    is_closure = False
    mro_depth = 0
    unresolved_call_count = 0
    manifests_found = 0

    if manifest_registry is not None:
        flatten_fn = None
        try:
            from startd8.utils.manifest_registry import _flatten_elements
            flatten_fn = _flatten_elements
        except ImportError:
            logger.debug(
                "CMR: manifest_registry import failed for %s", _chunk_id,
            )

        if flatten_fn is not None:
            try:
                for tf in target_files:
                    manifest = manifest_registry.get(tf)
                    if manifest is None:
                        continue
                    manifests_found += 1
                    try:
                        elements = flatten_fn(manifest.elements)
                    except (TypeError, AttributeError) as exc:
                        logger.debug(
                            "CMR: element flattening failed for %s in %s: %s",
                            tf, _chunk_id, exc,
                        )
                        continue

                    for elem in elements:
                        # Dynamic dispatch + unresolved call detection
                        try:
                            cg = getattr(elem, "call_graph", None)
                            if cg is not None:
                                for call in getattr(cg, "calls", []):
                                    if getattr(call, "is_dynamic", False):
                                        has_dynamic_dispatch = True
                                        break
                                unresolved_call_count += sum(
                                    1 for c in getattr(cg, "calls", [])
                                    if getattr(c, "target_fqn", None) is None
                                )
                        except (TypeError, AttributeError) as exc:
                            logger.debug(
                                "CMR: call graph inspection failed for "
                                "element in %s: %s",
                                _chunk_id, exc,
                            )

                        # Closure detection
                        if getattr(elem, "is_closure", False):
                            is_closure = True

                        # MRO depth (Phase 5)
                        try:
                            inspect_info = getattr(elem, "inspect_info", None)
                            if inspect_info is not None:
                                depth = getattr(
                                    inspect_info, "mro_depth", 0,
                                ) or 0
                                mro_depth = max(mro_depth, depth)
                        except (TypeError, AttributeError) as exc:
                            logger.debug(
                                "CMR: MRO depth extraction failed for "
                                "element in %s: %s",
                                _chunk_id, exc,
                            )

                # Cross-file call edges
                if len(target_files) > 1:
                    has_cross_file_edges = detect_cross_file_edges(
                        target_files, manifest_registry, flatten_fn,
                    )
            except Exception:
                logger.debug(
                    "CMR: manifest signal extraction failed for %s",
                    _chunk_id, exc_info=True,
                )

    # Simplified confidence signal: binary manifest coverage.
    manifest_coverage = (
        "full"
        if manifest_registry is not None
        and target_files
        and manifests_found == len(target_files)
        else "none"
    )

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


# ── Element-level extraction (Micro Prime, REQ-MP-806) ──────────────────


def extract_signals_from_element(
    element: Any,
    file_spec: Any,
    contracts: Any,
) -> TaskComplexitySignals:
    """Extract complexity signals from a Micro Prime element spec.

    Bridges element-level signals to task-level signal space. Signals
    that have no element-level equivalent use safe defaults (MODERATE).

    Args:
        element: A ``ForwardElementSpec``-like object.
        file_spec: A ``ForwardFileSpec``-like object.
        contracts: List of ``InterfaceContract`` objects (may be empty).

    Returns:
        Populated ``TaskComplexitySignals`` instance.
    """
    estimated_loc = 0
    has_dynamic_dispatch = False
    mro_depth = 0
    target_file_count = 1

    try:
        # Estimate LOC from docstring length heuristic
        docstring = getattr(element, "docstring_hint", "") or ""
        estimated_loc = max(len(docstring) // 2, 1)

        # Check for dynamic dispatch markers (complex decorators)
        decorators = getattr(element, "decorators", None) or []
        _DISPATCH_MARKERS = {"dispatch", "singledispatch", "abstractmethod"}
        for dec in decorators:
            if any(marker in dec for marker in _DISPATCH_MARKERS):
                has_dynamic_dispatch = True
                break

        # MRO depth from bases
        bases = getattr(element, "bases", None) or []
        if len(bases) > 1:
            mro_depth = len(bases)  # Multi-inheritance → elevated MRO

        # Estimate target file count from file_spec
        target_file_count = 1

    except (TypeError, AttributeError) as exc:
        logger.debug(
            "Element signal extraction failed for %s: %s",
            getattr(element, "name", "?"), exc,
        )

    return TaskComplexitySignals(
        blast_radius=0,
        caller_count=0,
        has_dynamic_dispatch=has_dynamic_dispatch,
        is_closure=False,
        estimated_loc=estimated_loc,
        target_file_count=target_file_count,
        edit_mode="create",
        mro_depth=mro_depth,
        unresolved_call_count=0,
        has_cross_file_edges=False,
        manifest_coverage="full",
    )
