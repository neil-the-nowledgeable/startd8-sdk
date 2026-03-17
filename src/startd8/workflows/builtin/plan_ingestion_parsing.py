"""Plan ingestion parsing helpers — deterministic fallback parsers and utilities.

Extracted from plan_ingestion_workflow.py (AC-R2) to reduce file size.
All symbols are re-exported from plan_ingestion_workflow.py for backward compatibility.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ...logging_config import get_logger
from ...utils.code_extraction import extract_code_from_response
from .plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
)

logger = get_logger(__name__)


def _extract_json_from_response(response: str) -> dict:
    """Extract JSON from an LLM response, handling code fences."""
    text = extract_code_from_response(response, language="json")
    return json.loads(text)


def _extract_imports_from_existing(
    file_path: str,
    project_root: Optional[Path],
) -> list:
    """Extract import specs from an existing file on disk.

    Parses the file's AST to discover ``import`` and ``from ... import``
    statements.  Returns a list of ``ForwardImportSpec``-compatible dicts
    (Pydantic will coerce them on assignment).  Returns an empty list if
    the file does not exist, is not Python, or cannot be parsed.

    This ensures the element classifier has import context for files that
    already exist (run-038: empty imports caused the classifier to miss
    external API signals, leading to SIMPLE classification and cascading
    circuit breaker failures).
    """
    if project_root is None:
        return []
    full_path = project_root / file_path
    if not full_path.is_file() or full_path.suffix not in (".py", ".pyi"):
        return []
    try:
        source = full_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    from startd8.forward_manifest import ForwardImportSpec

    specs: list = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                specs.append(ForwardImportSpec(
                    kind="import",
                    module=alias.name,
                    alias=alias.asname,
                ))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            specs.append(ForwardImportSpec(
                kind="from",
                module=node.module,
                names=[a.name for a in node.names],
            ))
    return specs


def _as_bool(raw: Any, default: bool) -> bool:
    """Parse truthy/falsy user config values with a default."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _safe_int(val: Any, default: int) -> int:
    """Parse a value to int, tolerating float strings from LLM output."""
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


_HEURISTIC_FALLBACK_DESCRIPTION = "Fallback parsed feature from plan text"

# File extensions that indicate a real file path (not a Python dotted expression)
_FILE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".h",
    ".html", ".css", ".yaml", ".yml", ".json", ".toml", ".md", ".txt",
    ".sh", ".in", ".cfg", ".ini", ".xml", ".proto", ".sql",
})


def _extract_file_paths_from_block(block: str) -> List[str]:
    """Extract file paths from a plan feature block, filtering Python expressions.

    The backtick regex ``[A-Za-z0-9_./-]+\\.[A-Za-z0-9_]+`` matches both
    file paths (``src/emailservice/logger.py``) and Python dotted expressions
    (``logging.INFO``, ``typing.Any``).  This function filters using:

    1. Must end with a known file extension, OR contain ``/`` (directory separator)
    2. Reject entries matching common Python patterns (stdlib modules, uppercase
       constants, ``self.`` / ``request.`` / ``record.`` prefixes)
    """
    raw = re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)`", block)
    result: List[str] = []
    for candidate in raw:
        # Check for known file extension
        _, ext = os.path.splitext(candidate)
        if ext.lower() in _FILE_EXTENSIONS:
            result.append(candidate)
            continue
        # Has directory separator → likely a file path
        if "/" in candidate:
            result.append(candidate)
            continue
        # Everything else is likely a Python dotted expression — skip
    return result


def _heuristic_parse_plan(plan_text: str) -> ParsedPlan:
    """Deterministic fallback parser when LLM parse fails."""
    title_match = re.search(r"^\s*#\s+(.+)$", plan_text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Plan"

    goal_lines: List[str] = []
    in_goals = False
    for line in plan_text.splitlines():
        if re.match(r"^\s*##\s+goals?\s*$", line, flags=re.IGNORECASE):
            in_goals = True
            continue
        if in_goals and re.match(r"^\s*##\s+", line):
            in_goals = False
        if in_goals:
            m = re.match(r"^\s*[-*]\s+(.+)$", line)
            if m:
                goal_lines.append(m.group(1).strip())

    # Two-pass approach: first collect all feature IDs so deps can be filtered
    # during construction (avoids creating ParsedFeature objects with phantom deps).
    known_fids: set = set()
    feature_header_re = re.compile(
        r"^\s*###\s+([A-Za-z]+-\d+)\s*:\s*(.+)$", flags=re.MULTILINE
    )
    for m in feature_header_re.finditer(plan_text):
        known_fids.add(m.group(1).upper())

    features: List[ParsedFeature] = []
    for idx, m in enumerate(
        feature_header_re.finditer(plan_text),
        start=1,
    ):
        fid = m.group(1).upper()
        name = m.group(2).strip()
        start_pos = m.end()
        next_match = re.search(r"^\s*###\s+", plan_text[start_pos:], flags=re.MULTILINE)
        end_pos = start_pos + (next_match.start() if next_match else len(plan_text[start_pos:]))
        block = plan_text[start_pos:end_pos]
        files = sorted(
            set(_extract_file_paths_from_block(block))
        )
        deps = sorted(set(re.findall(r"\b([A-Z]{1,4}-\d+)\b", block)))
        deps = [d.upper() for d in deps if d.upper() != fid and d.upper() in known_fids]
        features.append(
            ParsedFeature(
                feature_id=fid,
                name=name,
                description=block.strip()[:1000] if block.strip() else name,
                target_files=files,
                dependencies=deps,
                estimated_loc=120,
                labels=[],
            )
        )

    if not features:
        features = [
            ParsedFeature(
                feature_id="F-001",
                name=title,
                description=_HEURISTIC_FALLBACK_DESCRIPTION,
                target_files=[],
                dependencies=[],
                estimated_loc=120,
                labels=[],
            )
        ]

    mentioned_files = sorted(
        set(
            re.findall(
                r"(?:^|[\s(])([A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)(?:$|[\s),])",
                plan_text,
            )
        )
    )
    dep_graph = {f.feature_id: list(f.dependencies) for f in features if f.dependencies}
    return ParsedPlan(
        title=title,
        goals=goal_lines,
        features=features,
        dependency_graph=dep_graph,
        mentioned_files=mentioned_files,
        raw_text=plan_text,
    )


def _heuristic_assess_complexity(
    parsed_plan: ParsedPlan,
    *,
    threshold: int,
    force_route: Optional[str],
    manifest_registry: Any = None,
) -> ComplexityScore:
    """Deterministic fallback complexity assessment.

    When manifest_registry is available (Phase 4 PI-1 through PI-3):
    - PI-1: api_surface uses manifest public_element_count instead of feature_count * 8
    - PI-2: cross_file_deps uses manifest dependency_graph for transitive deps
    - PI-3: modification_type classification via fqn_exists (ImplementPhaseHandler._classify_edit_mode, REQ-EMM-001/002)
    """
    feature_count = len(parsed_plan.features)
    mentioned_files = {tf for f in parsed_plan.features for tf in f.target_files}
    # M-1: Include plan-prose mentioned files when available
    plan_mentioned = getattr(parsed_plan, "mentioned_files", None)
    if plan_mentioned:
        mentioned_files = mentioned_files | set(plan_mentioned)

    # PI-2: Use manifest dependency graph when available
    if manifest_registry is not None:
        try:
            dep_graph = manifest_registry.dependency_graph()
            # Count unique cross-file dependencies from mentioned files
            total_edges = sum(
                len(dep_graph.get(mf, set()))
                for mf in mentioned_files
            )
            # H-1: Normalize to average deps per file so manifest scale
            # is comparable to the feature-based fallback scale.
            cross_file_deps = total_edges // max(1, len(mentioned_files))
            logger.debug(
                "PI-2: manifest dependency graph used — %d files, %d edges, avg %d",
                len(mentioned_files),
                total_edges,
                cross_file_deps,
            )
        except Exception:
            cross_file_deps = sum(len(f.dependencies) for f in parsed_plan.features)
    else:
        cross_file_deps = sum(len(f.dependencies) for f in parsed_plan.features)

    # PI-1: Use manifest public_element_count when available
    if manifest_registry is not None:
        try:
            api_surface = min(
                100,
                max(10, sum(
                    manifest_registry.public_element_count(mf)
                    for mf in mentioned_files
                )),
            )
            logger.debug(
                "PI-1: manifest element count used — api_surface=%d",
                api_surface,
            )
        except Exception:
            api_surface = min(100, max(10, feature_count * 8))
    else:
        api_surface = min(100, max(10, feature_count * 8))

    if manifest_registry is None:
        logger.info(
            "manifest.fallback",
            extra={"surface": "plan_ingestion", "reason": "registry_unavailable"},
        )
    test_complexity = min(100, max(10, feature_count * 6))
    integration_depth = min(100, max(10, cross_file_deps * 10))
    domain_novelty = 40
    ambiguity = 45

    # Phase 6: CG-PI-1 — call graph impact dimension
    call_graph_impact = 0
    if manifest_registry is not None:
        try:
            mentioned_fqns: list[str] = []
            for f in parsed_plan.features:
                for tf in f.target_files:
                    manifest = manifest_registry.get(tf)
                    if manifest is not None:
                        from startd8.utils.manifest_registry import _flatten_elements
                        for elem in _flatten_elements(manifest.elements):
                            if elem.fqn:
                                mentioned_fqns.append(elem.fqn)
            if mentioned_fqns:
                _max_fqn, max_count = manifest_registry.max_blast_radius(mentioned_fqns)
                # Normalize to 0-100 scale
                call_graph_impact = min(100, max(0, max_count * 5))
                logger.debug(
                    "CG-PI-1: max blast radius = %d (fqn=%s), score=%d",
                    max_count, _max_fqn, call_graph_impact,
                )
        except Exception:
            logger.debug("CG-PI-1: blast radius computation failed", exc_info=True)

    # Normalize feature_count to 0-100 scale for composite parity with
    # the LLM assess path (which scores all 7 dimensions on 0-100).
    # Scale: 1-3 features → low, 10 → mid, 20+ → high.
    feature_count_score = min(100, max(10, feature_count * 7))

    # Normalize cross_file_deps to 0-100 before composite (reused in return)
    cross_file_deps_norm = min(100, max(0, cross_file_deps * 10))

    # Composite: includes feature_count_score for parity with LLM path
    if call_graph_impact > 0:
        composite = int(
            (feature_count_score + cross_file_deps_norm + api_surface
             + test_complexity + integration_depth + domain_novelty
             + ambiguity + call_graph_impact) / 8
        )
    else:
        composite = int(
            (feature_count_score + cross_file_deps_norm + api_surface
             + test_complexity + integration_depth + domain_novelty
             + ambiguity) / 7
        )

    if force_route:
        route = ContractorRoute(force_route)
    else:
        route = ContractorRoute.PRIME if composite <= threshold else ContractorRoute.ARTISAN

    # Phase 6: CG-PI-2,3,4 — feature-level annotations
    if manifest_registry is not None:
        try:
            dead_set = set(manifest_registry.dead_candidates())
        except Exception:
            dead_set = set()
        _blast_threshold = 20  # CG-PI-3 threshold

        for feature in parsed_plan.features:
            try:
                feature_fqns: list[str] = []
                for tf in feature.target_files:
                    fmanifest = manifest_registry.get(tf)
                    if fmanifest is not None:
                        from startd8.utils.manifest_registry import _flatten_elements
                        for elem in _flatten_elements(fmanifest.elements):
                            if elem.fqn:
                                feature_fqns.append(elem.fqn)

                # CG-PI-2: affected_callers
                all_callers: set[str] = set()
                for fqn in feature_fqns:
                    all_callers.update(manifest_registry.callers_of(fqn))
                feature.affected_callers = sorted(all_callers)

                # CG-PI-3: high_impact
                if feature_fqns:
                    _fqn, _count = manifest_registry.max_blast_radius(feature_fqns)
                    if _count > _blast_threshold:
                        feature.high_impact = True
                        logger.warning(
                            "CG-PI-3: feature %s has high blast radius (%d > %d, fqn=%s)",
                            feature.feature_id, _count, _blast_threshold, _fqn,
                        )

                # CG-PI-4: targets_dead_code
                if feature_fqns and all(fqn in dead_set for fqn in feature_fqns):
                    feature.targets_dead_code = True
                    logger.info(
                        "CG-PI-4: feature %s targets dead code only",
                        feature.feature_id,
                    )
            except Exception:
                logger.debug(
                    "CG-PI: feature annotation failed for %s",
                    feature.feature_id, exc_info=True,
                )

    return ComplexityScore(
        feature_count=feature_count_score,
        cross_file_deps=cross_file_deps_norm,
        api_surface=api_surface,
        test_complexity=test_complexity,
        integration_depth=integration_depth,
        domain_novelty=domain_novelty,
        ambiguity=ambiguity,
        call_graph_impact=call_graph_impact,
        composite=composite,
        reasoning="Heuristic fallback complexity used after assess failure",
        route=route,
    )


def _heuristic_transform_content(parsed_plan: ParsedPlan, route: ContractorRoute) -> str:
    """Deterministic fallback transform output."""
    import yaml

    if route == ContractorRoute.PRIME:
        tasks = []
        fid_to_tid = {
            f.feature_id: f"PI-{idx:03d}"
            for idx, f in enumerate(parsed_plan.features, start=1)
        }
        for idx, f in enumerate(parsed_plan.features, start=1):
            deps = [
                fid_to_tid[dep]
                for dep in f.dependencies
                if dep in fid_to_tid
            ]
            tasks.append(
                {
                    "task_id": f"PI-{idx:03d}",
                    "title": f.name,
                    "task_type": "task",
                    "priority": "medium",
                    "story_points": 3,
                    "labels": list(f.labels) or ["implementation"],
                    "depends_on": deps,
                    "config": {
                        "task_description": f.description or f.name,
                        "context": {"feature_id": f.feature_id, "target_files": list(f.target_files)},
                    },
                }
            )
        return yaml.safe_dump({"tasks": tasks}, sort_keys=False)

    lines = [f"# {parsed_plan.title}", "", "## Overview"]
    if parsed_plan.goals:
        lines.extend([f"- {g}" for g in parsed_plan.goals])
    else:
        lines.append("Generated via heuristic fallback transform.")
    lines.extend(["", "## Phase Breakdown"])
    for f in parsed_plan.features:
        lines.extend([f"### {f.feature_id}: {f.name}", f.description or f.name, ""])
    return "\n".join(lines).strip() + "\n"


def _parse_context_files(
    raw: Union[str, list, None],
) -> Optional[List[str]]:
    """Parse context_files from config — handles str (comma-separated), list, or None."""
    if not raw:
        return None
    if isinstance(raw, str):
        return [f.strip() for f in raw.split(",") if f.strip()]
    return list(raw)


def _parse_file_list(raw: Union[str, list, None]) -> List[str]:
    """Parse an optional file list from string or list input."""
    parsed = _parse_context_files(raw)
    return parsed or []


def _safe_json_load(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON from path if possible; return None on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
