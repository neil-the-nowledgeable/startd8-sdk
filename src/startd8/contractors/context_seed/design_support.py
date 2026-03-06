"""Shared design-phase helpers for context seed handlers."""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.context_seed.shared import SeedTask

from startd8.logging_config import get_logger

logger = get_logger("startd8.contractors.context_seed_handlers")

# --------------------------------------------------------------------------
# PCA-605d: Defense-in-depth design→implement file discovery (4 layers)
# --------------------------------------------------------------------------

# Layer 1: bold file markers (original PCA-605c)
_DESIGN_FILE_MARKER_RE = re.compile(r'\*\*File:\s*`([^`]+)`\*\*', re.MULTILINE)

# Layer 2: fenced code block file paths
_DESIGN_FENCED_BLOCK_RE = re.compile(r'```(\S*)\s*\n(.*?)```', re.DOTALL)
_DESIGN_FIRST_LINE_FILE_RE = re.compile(r'^(?://|#)\s*(\S+\.\w+)')

# Layer 3: prose "new file" signals near backtick-quoted filenames
_PROSE_NEW_FILE_RE = re.compile(
    r'(?:new\s+(?:file|module)|extract(?:ed)?\s+to|dedicated\s+(?:module|file)|'
    r'separate\s+(?:module|file)|split\s+(?:into|to)|'
    r'create\s+(?:a\s+)?(?:new\s+)?(?:module|file))'
    r'[^`]{0,80}`([^`]+\.\w{1,5})`',
    re.IGNORECASE | re.MULTILINE,
)
_CONDITIONAL_FILTER_RE = re.compile(
    r'\b(?:when|if\s+(?:needed|required)|eventually|later|future|'
    r'could\s+be|might\s+be)\b',
    re.IGNORECASE,
)

# Layer 4: structured ### Files Touched section (prompt-guided, primary)
_FILES_TOUCHED_SECTION_RE = re.compile(
    r'###\s*Files?\s+Touched\s*\n(.*?)(?=\n##|\n###|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_FILES_TOUCHED_ENTRY_RE = re.compile(r'-\s*`([^`]+\.\w{1,5})`')

# Shared validation
_VALID_FILE_EXTENSIONS = frozenset({
    '.py', '.ts', '.tsx', '.js', '.jsx', '.yaml', '.yml',
    '.json', '.toml', '.cfg', '.sh', '.sql', '.html', '.css',
    '.go', '.rs', '.java', '.kt', '.rb',
})


def _infer_path_prefix(targets: list[str]) -> str:
    """Infer common directory prefix from existing target files."""
    if not targets:
        return ""
    first_target = targets[0]
    slash_idx = first_target.rfind("/")
    if slash_idx >= 0:
        return first_target[: slash_idx + 1]  # includes trailing '/'
    return ""


def _has_valid_extension(path: str) -> bool:
    """Check if path has a recognized source file extension."""
    dot_idx = path.rfind(".")
    if dot_idx < 0:
        return False
    return path[dot_idx:].lower() in _VALID_FILE_EXTENSIONS


def _extract_design_target_files(
    design_doc: str,
    current_targets: list[str],
) -> list[str]:
    """Parse a design document for file decisions and merge with current targets.

    Uses 4 extraction layers in priority order for defense-in-depth:

    - **Layer 4** (primary): ``### Files Touched`` structured section — the
      prompt-guided output format, most reliable when present.
    - **Layer 1** (fallback): ``**File: \\`name\\`**`` bold markers from
      PCA-605c.
    - **Layer 2** (fallback): Fenced code blocks with file paths in the
      language tag or a first-line comment.
    - **Layer 3** (fallback): Prose "new file" signals within 80 chars of a
      backtick-quoted filename, with a conditional-language filter to avoid
      false positives (e.g. "when a second consumer…").

    All layers accumulate into a single list → normalize bare filenames using
    prefix → filter by extension → dedup with ``dict.fromkeys`` → return
    merged list.

    Returns:
        Merged list of target files — original targets first (order preserved),
        then any newly discovered files appended.  Deduped via ``dict.fromkeys``.
    """
    prefix = _infer_path_prefix(current_targets)
    discovered: list[str] = []
    layer_counts: dict[str, int] = {}

    # --- Layer 4 (primary): ### Files Touched section ---
    section_match = _FILES_TOUCHED_SECTION_RE.search(design_doc)
    if section_match:
        entries = _FILES_TOUCHED_ENTRY_RE.findall(section_match.group(1))
        layer_counts["layer4_files_touched"] = len(entries)
        discovered.extend(entries)

    # --- Layer 1 (fallback): **File: `name`** bold markers ---
    bold_matches = _DESIGN_FILE_MARKER_RE.findall(design_doc)
    layer_counts["layer1_bold_markers"] = len(bold_matches)
    discovered.extend(bold_matches)

    # --- Layer 2 (fallback): fenced code blocks with file paths ---
    layer2_count = 0
    for block_match in _DESIGN_FENCED_BLOCK_RE.finditer(design_doc):
        lang_tag = block_match.group(1)
        block_body = block_match.group(2)

        # Check language tag for a file path (must contain '/' and valid ext)
        if lang_tag and "/" in lang_tag and _has_valid_extension(lang_tag):
            discovered.append(lang_tag)
            layer2_count += 1
            continue

        # Check first line for a file-path comment (# path/to/file.py)
        first_line = block_body.split("\n", 1)[0].strip()
        fl_match = _DESIGN_FIRST_LINE_FILE_RE.match(first_line)
        if fl_match:
            candidate = fl_match.group(1)
            if "/" in candidate and _has_valid_extension(candidate):
                discovered.append(candidate)
                layer2_count += 1
    layer_counts["layer2_fenced_blocks"] = layer2_count

    # --- Layer 3 (fallback): prose "new file" signals ---
    layer3_count = 0
    for prose_match in _PROSE_NEW_FILE_RE.finditer(design_doc):
        candidate = prose_match.group(1)
        # Conditional filter: check a 200-char window around the match
        start = max(0, prose_match.start() - 100)
        end = min(len(design_doc), prose_match.end() + 100)
        window = design_doc[start:end]
        if _CONDITIONAL_FILTER_RE.search(window):
            continue
        discovered.append(candidate)
        layer3_count += 1
    layer_counts["layer3_prose_signals"] = layer3_count

    if not discovered:
        return current_targets

    # Build lookups for contradictory-path deduplication (PCA-605d).
    # When current_targets already specify a path for a given basename,
    # the plan's path is authoritative — discovered paths that contradict
    # it are dropped to prevent mixed-layout target lists.
    _current_set = set(current_targets)
    _bn_to_target: dict[str, list[str]] = {}
    for _t in current_targets:
        _bn = _t.rsplit("/", 1)[-1] if "/" in _t else _t
        _bn_to_target.setdefault(_bn, []).append(_t)

    # Normalize bare filenames, filter by valid extension, and exclude test
    # files.  Test files are the TEST phase's responsibility — including them
    # here causes the drafter to generate test code instead of the primary
    # implementation artifact.
    normalized: list[str] = []
    _test_filtered: list[str] = []
    for raw in discovered:
        if "/" not in raw and prefix:
            # PCA-605d: if the bare filename already exists verbatim in
            # current_targets, keep it bare.  Prevents turning root-level
            # ``pyproject.toml`` into ``src/pkg/pyproject.toml``.
            if raw in _current_set:
                path = raw
            else:
                path = prefix + raw
        else:
            path = raw
        if not _has_valid_extension(path):
            continue
        # Exclude test files: tests/ directory, test_*.py, *_test.py
        _basename = path.rsplit("/", 1)[-1] if "/" in path else path
        if (
            path.startswith("tests/")
            or "/tests/" in path
            or _basename.startswith("test_")
            or _basename.endswith("_test.py")
        ):
            _test_filtered.append(path)
            continue
        normalized.append(path)
    if _test_filtered:
        logger.info(
            "PCA-605d: filtered %d test file(s) from design doc discovery "
            "(TEST phase handles these): %s",
            len(_test_filtered),
            _test_filtered,
        )

    if not normalized:
        return current_targets

    # PCA-605d: deduplicate contradictory paths — if a discovered path
    # shares a basename with exactly one current target but at a different
    # directory depth, drop it.  Prevents Layer 2 from injecting e.g.
    # ``src/pkg/pyproject.toml`` when the plan already has ``pyproject.toml``
    # at project root.
    _contradictions: list[str] = []
    _deduped: list[str] = []
    for path in normalized:
        _bn = path.rsplit("/", 1)[-1] if "/" in path else path
        target_paths = _bn_to_target.get(_bn, [])
        if (
            len(target_paths) == 1
            and path != target_paths[0]
            and path not in _current_set
        ):
            _contradictions.append(path)
            continue
        _deduped.append(path)
    if _contradictions:
        logger.info(
            "PCA-605d: dropped %d contradictory path(s) "
            "(basename conflicts with current targets): %s",
            len(_contradictions),
            _contradictions,
        )
    normalized = _deduped

    if not normalized:
        return current_targets

    # Merge: original order first, then new discoveries (deduped).
    merged = list(dict.fromkeys(current_targets + normalized))

    logger.debug(
        "PCA-605d file discovery layers: %s, discovered=%d, merged=%d",
        layer_counts, len(normalized), len(merged),
    )

    return merged


# ============================================================================
# Handoff enrichment helpers — Gaps 1-5
# ============================================================================

# Regex for file-level action annotations: `path/to/file.py` (modify)
_FILE_ACTION_RE = re.compile(
    r'-\s*`([^`]+\.\w{1,5})`\s*(?:\((\w+)\))?',
)

# Regex for element-level references: backtick-quoted identifiers
_ELEMENT_REF_RE = re.compile(
    r'`(\w[\w.]*(?:\([^)]*\))?)`',
)

# Common element action verbs in design docs
_ACTION_VERB_RE = re.compile(
    r'^(add|create|new|introduce|modify|update|change|alter|preserve|keep|retain)',
    re.IGNORECASE,
)


def _extract_structural_delta(
    design_doc: str,
) -> dict[str, list[dict[str, str]]]:
    """Extract per-file structural intent from a design document.

    Parses the ``### Files Touched`` section for file-level create/modify
    annotations and element-level action descriptions.

    Args:
        design_doc: The raw design document text.

    Returns:
        ``{filepath: [{"element": "...", "action": "add|modify|preserve",
        "detail": "..."}]}``  Empty dict if no ``### Files Touched`` section
        is found or the section has no parseable entries.
    """
    delta: dict[str, list[dict[str, str]]] = {}
    section_match = _FILES_TOUCHED_SECTION_RE.search(design_doc)
    if not section_match:
        return delta

    section_text = section_match.group(1)
    current_file: str | None = None
    current_action = "modify"

    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # File entry: - `path/to/file.py` (modify)
        file_match = _FILE_ACTION_RE.match(stripped)
        if file_match:
            current_file = file_match.group(1)
            action_hint = (file_match.group(2) or "modify").lower()
            if action_hint in ("create", "new"):
                current_action = "add"
            elif action_hint in ("modify", "update", "change"):
                current_action = "modify"
            elif action_hint in ("preserve", "keep"):
                current_action = "preserve"
            else:
                current_action = action_hint
            delta.setdefault(current_file, [])
            continue

        # Sub-item under a file (indented bullet or description)
        if current_file and stripped.startswith("-"):
            element_text = stripped.lstrip("- ").strip()
            element_action = current_action
            element_name = ""

            # Detect action verb at start of line
            verb_match = _ACTION_VERB_RE.match(element_text)
            if verb_match:
                verb = verb_match.group(1).lower()
                if verb in ("add", "create", "new", "introduce"):
                    element_action = "add"
                elif verb in ("modify", "update", "change", "alter"):
                    element_action = "modify"
                elif verb in ("preserve", "keep", "retain"):
                    element_action = "preserve"

            # Extract element name from backtick references
            elem_refs = _ELEMENT_REF_RE.findall(element_text)
            if elem_refs:
                element_name = elem_refs[0]

            delta[current_file].append({
                "element": element_name,
                "action": element_action,
                "detail": element_text,
            })

    return delta


def _extract_referenced_elements(
    design_doc: str,
    manifest_elements: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Extract element names referenced in a design document.

    Scans the entire design doc for backtick-quoted identifiers that look
    like code elements (class names, function names, FQNs).  When a manifest
    is provided, only elements that match known manifest entries are included
    (reducing noise from prose references like ``True`` or ``None``).

    Args:
        design_doc: The raw design document text.
        manifest_elements: Optional ``{filepath: [element_name, ...]}`` from
            the manifest registry for cross-validation.

    Returns:
        ``{filepath: [element_name, ...]}`` of elements referenced in the
        design doc that correspond to manifest entries.  Empty dict when
        no manifest is provided or no cross-references are found.
    """
    if not manifest_elements:
        return {}

    # Build reverse lookup: element_name → filepath
    elem_to_file: dict[str, str] = {}
    for fpath, elements in manifest_elements.items():
        for elem in elements:
            # Store both full FQN and simple name
            elem_to_file[elem] = fpath
            if "." in elem:
                simple = elem.rsplit(".", 1)[-1]
                elem_to_file.setdefault(simple, fpath)

    # Scan design doc for backtick-quoted references
    referenced: dict[str, list[str]] = {}
    for ref in _ELEMENT_REF_RE.findall(design_doc):
        # Strip trailing parentheses for matching
        clean_ref = ref.rstrip(")")
        if "(" in clean_ref:
            clean_ref = clean_ref[:clean_ref.index("(")]
        fpath = elem_to_file.get(clean_ref) or elem_to_file.get(ref)
        if fpath:
            referenced.setdefault(fpath, [])
            if clean_ref not in referenced[fpath]:
                referenced[fpath].append(clean_ref)

    return referenced


def _compute_manifest_file_checksums(
    target_files: list[str],
    project_root: str,
) -> dict[str, str]:
    """Compute SHA-256 checksums for target files at design time.

    Args:
        target_files: List of file paths (relative to project_root).
        project_root: Absolute path to the project root.

    Returns:
        ``{filepath: sha256_hex}`` for files that exist and are readable.
    """
    checksums: dict[str, str] = {}
    root = Path(project_root) if project_root else None
    if not root:
        return checksums

    for fpath in target_files:
        full = root / fpath
        if full.exists() and full.is_file():
            try:
                content = full.read_bytes()
                checksums[fpath] = hashlib.sha256(content).hexdigest()
            except OSError as exc:
                logger.debug("Checksum computation failed for %s: %s", fpath, exc)
    return checksums


# ============================================================================
# CCD: Context Correctness by Design helpers
# ============================================================================

# CCD-601/602: Canonical span attribute names for design-phase lane-awareness.
# Changing these names breaks dashboard queries documented in
# docs/design/artisan/plans/CCD_LAYER6_TEMPO_QUERIES.md
_CCD_DESIGN_SPAN_ATTRS = frozenset({
    "task.lane_index",
    "task.lane_peer_count",
    "task.shared_file_count",
    "task.lane_prior_designs_count",
    "task.lane_prior_designs_truncated",
    "design.collision_severity",
})


def _normalize_target_path(path: str) -> str:
    """Normalize a target file path for comparison (CCD-300)."""
    return os.path.normpath(path).replace("\\", "/")


def build_shared_file_manifest(
    tasks: list[SeedTask],
) -> dict[str, list[str]]:
    """Build mapping from target file paths to task IDs that target them.

    Only files targeted by 2+ tasks are included (CCD-300).
    """
    file_to_tasks: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for tf in (task.target_files or []):
            normalized = _normalize_target_path(tf)
            file_to_tasks[normalized].append(task.task_id)
    return {
        path: task_ids
        for path, task_ids in file_to_tasks.items()
        if len(task_ids) >= 2
    }


def compute_lane_to_file_mapping(
    lanes: list[list[SeedTask]],
    shared_file_manifest: dict[str, list[str]],
) -> dict[int, list[str]]:
    """For each lane, which shared files caused its formation (CCD-302)."""
    mapping: dict[int, list[str]] = {}
    for lane_idx, lane_tasks in enumerate(lanes):
        lane_task_ids = {t.task_id for t in lane_tasks}
        lane_files = [
            fpath for fpath, contesting_ids in shared_file_manifest.items()
            if len(lane_task_ids & set(contesting_ids)) >= 2
        ]
        if lane_files:
            mapping[lane_idx] = sorted(lane_files)
    return mapping


def compute_critical_path_tasks(
    tasks: list[SeedTask],
    shared_file_manifest: dict[str, list[str]],
    top_fraction: float = 0.20,
) -> set[str]:
    """Identify tasks with highest shared-file contention score (CCD-403).

    Contention score = sum of (len(contesting_task_ids) - 1) across
    all of a task's target files that appear in the manifest.
    """
    if not tasks or not shared_file_manifest:
        return set()

    scores: dict[str, int] = {}
    for task in tasks:
        score = 0
        for tf in (task.target_files or []):
            normalized = _normalize_target_path(tf)
            contesting = shared_file_manifest.get(normalized, [])
            score += max(0, len(contesting) - 1)
        scores[task.task_id] = score

    contested_scores = [s for s in scores.values() if s > 0]
    if not contested_scores:
        return set()

    threshold_idx = max(0, int(len(contested_scores) * (1 - top_fraction)))
    sorted_scores = sorted(contested_scores)
    score_threshold = (
        sorted_scores[threshold_idx]
        if threshold_idx < len(sorted_scores)
        else sorted_scores[-1]
    )
    return {
        tid for tid, score in scores.items()
        if score >= score_threshold and score > 0
    }


def _compute_ccd_task_metadata(
    task: SeedTask,
    lane_assignments: dict[str, int],
    design_lanes: list[list] | None,
    total_task_count: int,
    shared_file_manifest: dict[str, list[str]],
    critical_task_ids: set[str],
) -> dict[str, Any]:
    """Compute CCD metadata fields for a single design result entry (CCD-401).

    Returns a dict to merge into ``design_results[task.task_id]``.
    Shared between adopted-design and fresh-design success paths.
    """
    return {
        "wave_index": task.wave_index,
        "lane_index": lane_assignments.get(task.task_id, 0),
        "lane_peer_count": (
            len(design_lanes[lane_assignments[task.task_id]]) - 1
            if design_lanes and task.task_id in lane_assignments
            else total_task_count - 1
        ),
        "shared_file_count": sum(
            1 for f in (task.target_files or [])
            if _normalize_target_path(f) in shared_file_manifest
        ),
        "critical_path": task.task_id in critical_task_ids,
    }


def _detect_cross_file_edges(
    target_files: list[str],
    manifest_registry: Any,
    flatten_fn: Any,
) -> bool:
    """Check whether any target files have call edges to each other (C1 extract).

    Delegates to ``startd8.complexity.signals.detect_cross_file_edges``.

    Args:
        target_files: List of relative file paths (must have len > 1).
        manifest_registry: ManifestRegistry with call_graph() method.
        flatten_fn: The ``_flatten_elements`` helper from manifest_registry.

    Returns:
        ``True`` if any element in one target file calls an element in another.
    """
    from startd8.complexity.signals import (
        detect_cross_file_edges as _shared_detect,
    )

    return _shared_detect(target_files, manifest_registry, flatten_fn)


def _extract_complexity_signals(
    chunk: Any,
    manifest_registry: Any,
) -> "TaskComplexitySignals":
    """Extract complexity signals from chunk metadata and manifest registry.

    Reads from existing enrichment data (``_call_graph_callers``,
    ``_edit_mode``, ``estimated_loc``) and queries the registry for
    ``has_dynamic_dispatch``, ``is_closure``, ``unresolved_calls``,
    ``mro_depth``.

    Args:
        chunk: A ``DevelopmentChunk``-like object with ``metadata`` dict
            and ``file_targets`` list.
        manifest_registry: A ``ManifestRegistry`` instance, or ``None``
            when manifest data is unavailable.

    Returns:
        A ``TaskComplexitySignals`` with all fields populated from available
        data, falling back to safe defaults on any extraction failure.

    Never raises — all lookups wrapped in try/except (REQ-CMR-010).
    """
    from startd8.contractors.artisan_phases.development import TaskComplexitySignals

    meta = getattr(chunk, "metadata", {}) or {}
    _chunk_id = getattr(chunk, "chunk_id", "?")

    # --- Signals from chunk metadata (populated by earlier enrichment) ---
    blast_radius = 0
    caller_count = 0
    has_cross_file_edges = False
    manifest_coverage = "none"
    cg_callers = []

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
        logger.debug("CMR: call graph caller extraction failed for %s: %s", _chunk_id, exc)

    # Edit mode from classification (normalized at extraction boundary)
    edit_mode = "unknown"
    try:
        edit_mode_dict = meta.get("_edit_mode")
        if edit_mode_dict and isinstance(edit_mode_dict, dict):
            edit_mode = str(edit_mode_dict.get("mode", "unknown")).strip().lower()
        elif isinstance(edit_mode_dict, str):
            edit_mode = edit_mode_dict.strip().lower()
    except (TypeError, AttributeError) as exc:
        logger.debug("CMR: edit mode extraction failed for %s: %s", _chunk_id, exc)

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
        # Single import of _flatten_elements for reuse (R1)
        try:
            from startd8.utils.manifest_registry import _flatten_elements
        except ImportError:
            logger.debug("CMR: manifest_registry import failed for %s", _chunk_id)
            _flatten_elements = None  # type: ignore[assignment]

        if _flatten_elements is not None:
            try:
                for tf in target_files:
                    manifest = manifest_registry.get(tf)
                    if manifest is None:
                        continue
                    manifests_found += 1
                    try:
                        elements = _flatten_elements(manifest.elements)
                    except (TypeError, AttributeError) as exc:
                        logger.debug("CMR: element flattening failed for %s in %s: %s", tf, _chunk_id, exc)
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
                            logger.debug("CMR: call graph inspection failed for element in %s: %s", _chunk_id, exc)

                        # Closure detection
                        if getattr(elem, "is_closure", False):
                            is_closure = True

                        # MRO depth (Phase 5)
                        try:
                            inspect_info = getattr(elem, "inspect_info", None)
                            if inspect_info is not None:
                                depth = getattr(inspect_info, "mro_depth", 0) or 0
                                mro_depth = max(mro_depth, depth)
                        except (TypeError, AttributeError) as exc:
                            logger.debug("CMR: MRO depth extraction failed for element in %s: %s", _chunk_id, exc)

                # Cross-file call edges (C1: extracted helper)
                if len(target_files) > 1:
                    has_cross_file_edges = _detect_cross_file_edges(
                        target_files, manifest_registry, _flatten_elements,
                    )
            except Exception:
                logger.debug("CMR: manifest signal extraction failed for %s", _chunk_id, exc_info=True)

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


def _classify_complexity_tier(
    signals: "TaskComplexitySignals",
    config: "HandlerConfig",
) -> "TaskComplexityTier":
    """Classify a task into a complexity tier (REQ-CMR-011).

    Delegates to the shared ``startd8.complexity`` module and maps the
    4-tier result back to the Artisan 3-tier enum.

    Args:
        signals: Complexity signals extracted from chunk metadata and
            manifest registry.
        config: Handler configuration with tier threshold fields.

    Returns:
        The classified ``TaskComplexityTier``.
    """
    from startd8.complexity import (
        ComplexityRoutingConfig,
        ComplexityTier,
        TaskComplexitySignals as SharedSignals,
        classify_tier,
    )
    from startd8.contractors.artisan_phases.development import TaskComplexityTier

    # Convert Artisan signals → shared signals via dict round-trip
    shared_signals = SharedSignals(**signals.to_dict())
    shared_config = ComplexityRoutingConfig.from_handler_config(config)

    shared_tier, _reason = classify_tier(shared_signals, shared_config)

    # Map shared 4-tier → Artisan 3-tier
    _tier_map = {
        ComplexityTier.TRIVIAL: TaskComplexityTier.TIER_1,
        ComplexityTier.SIMPLE: TaskComplexityTier.TIER_1,
        ComplexityTier.MODERATE: TaskComplexityTier.TIER_2,
        ComplexityTier.COMPLEX: TaskComplexityTier.TIER_3,
    }
    return _tier_map[shared_tier]


def _set_default_complexity_metadata(
    chunk: Any,
    *,
    force: bool,
) -> None:
    """Set Tier 2 fallback metadata in one place."""
    from startd8.contractors.artisan_phases.development import (
        TaskComplexitySignals,
        TaskComplexityTier,
    )

    if force:
        chunk.metadata["_complexity_tier"] = TaskComplexityTier.TIER_2.value
        chunk.metadata["_complexity_signals"] = TaskComplexitySignals().to_dict()
        return

    chunk.metadata.setdefault("_complexity_tier", TaskComplexityTier.TIER_2.value)
    chunk.metadata.setdefault("_complexity_signals", TaskComplexitySignals().to_dict())
