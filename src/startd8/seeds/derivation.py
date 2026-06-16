"""
Seed derivation logic — task derivation, calibration, architectural context.

Extracted from ``PlanIngestionWorkflow`` class methods and module-level
helpers in ``plan_ingestion_workflow.py``.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..languages.registry import LanguageRegistry
from ..logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "DEPTH_TIERS",
    "estimate_story_points",
    "is_trivial_test_init",
    "extract_refine_suggestions_for_seed",
    "infer_artifact_types_from_files",
    "infer_service_metadata",
    "derive_target_files_from_artifact_ids",
    "derive_tasks_from_features",
    "split_oversized_tasks",
    "filter_trivial_test_init_tasks",
    "derive_architectural_context",
    "derive_design_calibration",
    "_file_type_priority",
    "_extract_service_dir",
    "_inject_build_order_dependencies",
]

_SAFE_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

DEPTH_TIERS: Dict[str, Dict[str, Any]] = {
    "brief": {
        "sections": ["Overview", "Architecture", "Testing Strategy"],
        "max_tokens": 4096,
        "guidance": (
            "Concise design sketch. Focus on the interface contract and "
            "key test cases. This is a small feature — avoid over-engineering."
        ),
    },
    "standard": {
        "sections": [
            "Overview",
            "Architecture",
            "Data Model",
            "Error Handling",
            "Testing Strategy",
        ],
        "max_tokens": 8192,
        "guidance": (
            "Standard design doc. Include data model and error handling "
            "but keep depth proportional to the feature's scope."
        ),
    },
    "comprehensive": {
        "sections": [
            "Overview",
            "Architecture",
            "Data Model",
            "API Contracts",
            "Error Handling",
            "Security Considerations",
            "Testing Strategy",
        ],
        "max_tokens": 16384,
        "guidance": (
            "Comprehensive design. All sections are warranted for this "
            "complex feature — address security and API contracts thoroughly."
        ),
    },
}


def _classify_complexity(loc: int) -> str:
    """Classify task complexity from estimated LOC."""
    if loc <= 50:
        return "low"
    if loc <= 150:
        return "medium"
    return "high"


def estimate_story_points(estimated_loc: int) -> int:
    """Map estimated LOC to story points."""
    if estimated_loc <= 20:
        return 1
    if estimated_loc <= 50:
        return 2
    if estimated_loc <= 100:
        return 3
    if estimated_loc <= 200:
        return 5
    return 8


def is_trivial_test_init(file_path: str) -> bool:
    """Return True if *file_path* is a ``__init__.py`` inside a test directory."""
    if not file_path.endswith("__init__.py"):
        return False
    parts = file_path.replace("\\", "/").split("/")
    return any(p in ("tests", "test") for p in parts[:-1])


def extract_refine_suggestions_for_seed(
    review_output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract accepted triage suggestions for seed injection."""
    triage = review_output.get("triage")
    if not triage or not isinstance(triage, dict):
        return []

    decisions = triage.get("decisions", [])
    if not decisions:
        accepted = triage.get("accepted", 0)
        if accepted == 0:
            return []
        return [
            {
                "source": "triage_summary",
                "triage_accepted_count": accepted,
                "triage_rejected_count": triage.get("rejected", 0),
                "substantially_addressed_areas": triage.get(
                    "substantially_addressed_areas", [],
                ),
                "areas_needing_review": triage.get("areas_needing_review", []),
            }
        ]

    return [
        {
            "id": d.get("id", ""),
            "decision": d.get("decision", ""),
            "rationale": d.get("rationale", ""),
            "area": d.get("area", ""),
            "severity": d.get("severity", ""),
        }
        for d in decisions
        if d.get("decision") == "ACCEPT"
    ]


def _artifact_type_from_id(artifact_id: str) -> Optional[str]:
    """Derive artifact type from artifact ID suffix when possible."""
    aid = artifact_id.strip().lower()
    explicit_suffix_map = {
        "-dashboard": "dashboard",
        "_dashboard": "dashboard",
        "-loki-rules": "loki_rule",
        "_loki_rules": "loki_rule",
        "-notification": "notification_policy",
        "_notification": "notification_policy",
        "-prometheus-rules": "prometheus_rule",
        "_prometheus_rules": "prometheus_rule",
        "-runbook": "runbook",
        "_runbook": "runbook",
        "-service-monitor": "service_monitor",
        "_service_monitor": "service_monitor",
        "-slo": "slo_definition",
        "_slo": "slo_definition",
    }
    for suffix, artifact_type in explicit_suffix_map.items():
        if aid.endswith(suffix):
            return artifact_type
    return None


def _artifact_target_from_id(
    artifact_id: str, artifact_type: str
) -> Optional[str]:
    """Extract target slug from artifact id using known type suffix patterns."""
    aid = artifact_id.strip()
    type_patterns = {
        "dashboard": ["-dashboard", "_dashboard"],
        "loki_rule": ["-loki-rules", "_loki_rules"],
        "notification_policy": ["-notification", "_notification"],
        "prometheus_rule": ["-prometheus-rules", "_prometheus_rules"],
        "runbook": ["-runbook", "_runbook"],
        "service_monitor": ["-service-monitor", "_service_monitor"],
        "slo_definition": ["-slo", "_slo"],
    }
    for suffix in type_patterns.get(artifact_type, []):
        if aid.lower().endswith(suffix):
            raw_target = aid[: -len(suffix)]
            target = raw_target.replace("_", "-").strip("-_")
            return target or None
    return None


def infer_artifact_types_from_files(files: List[str]) -> List[str]:
    """Infer artifact types from target file names."""
    types: list[str] = []
    seen: set[str] = set()
    for f in files:
        path_lower = f.lower()
        name = path_lower.rsplit("/", 1)[-1] if "/" in path_lower else path_lower
        inferred: Optional[str] = None
        if name.startswith("dockerfile") or name.endswith(".dockerfile"):
            inferred = "dockerfile"
        elif name in (
            "requirements.txt", "requirements.in", "go.mod", "go.sum",
            "package.json", "package-lock.json", "pyproject.toml",
            "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock",
            "yarn.lock", "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock",
            "pom.xml",
        ):
            inferred = "dependency_manifest"
        elif name.endswith(".csproj"):
            inferred = "dependency_manifest"
        elif name.endswith(".proto"):
            inferred = "proto_contract"
        elif any(
            name.endswith(ext)
            for ext in (".py", ".go", ".js", ".ts", ".rs", ".java", ".rb", ".cs")
        ):
            inferred = "source_module"
        if inferred and inferred not in seen:
            types.append(inferred)
            seen.add(inferred)
    return types


def infer_service_metadata(
    features: list,
    onboarding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Infer service-level metadata from features and onboarding data.

    For Go projects, also derives module_path, service_name, and go_version.
    """
    _ext_map = LanguageRegistry.get_extension_map()

    protocols: list[str] = []
    all_runtime_deps: list[str] = []
    all_api_sigs: list[str] = []
    all_negative_scope: list[str] = []
    languages: list[str] = []
    for f in features:
        if not hasattr(f, "protocol"):
            logger.warning(
                "infer_service_metadata: skipping non-feature object %s",
                type(f).__name__,
            )
            continue
        if f.protocol:
            protocols.append(f.protocol)
        all_runtime_deps.extend(getattr(f, "runtime_dependencies", []))
        all_api_sigs.extend(getattr(f, "api_signatures", []))
        all_negative_scope.extend(getattr(f, "negative_scope", []))
        for tf in getattr(f, "target_files", []):
            ext = tf.rsplit(".", 1)[-1].lower() if "." in tf else ""
            lang = _ext_map.get("." + ext) if ext else None
            if lang and lang not in languages:
                languages.append(lang)

    transport = ""
    if protocols:
        transport = Counter(protocols).most_common(1)[0][0]
    elif onboarding:
        transport = onboarding.get("transport_protocol", "") or ""

    runtime_deps = sorted(set(all_runtime_deps))
    api_sigs = list(dict.fromkeys(all_api_sigs))
    negative_scope = list(dict.fromkeys(all_negative_scope))

    metadata: Dict[str, Any] = {}
    if transport:
        metadata["transport_protocol"] = transport
    if runtime_deps:
        metadata["runtime_dependencies"] = runtime_deps
    if languages:
        metadata["primary_language"] = (
            languages[0] if len(languages) == 1 else languages
        )
    if api_sigs:
        metadata["api_signatures"] = api_sigs
    if negative_scope:
        metadata["negative_scope"] = negative_scope

    # Language-specific metadata derivation (REQ-LA-201)
    primary_lang = metadata.get("primary_language", "")
    lang_id = primary_lang if isinstance(primary_lang, str) else (
        primary_lang[0] if primary_lang else ""
    )
    profile = LanguageRegistry.get(lang_id)
    if profile is not None and hasattr(profile, "derive_service_metadata"):
        lang_metadata = profile.derive_service_metadata(
            features,
            onboarding=onboarding,
            api_signatures=api_sigs,
            runtime_dependencies=runtime_deps,
        )
        metadata.update(lang_metadata)

    return metadata


def derive_target_files_from_artifact_ids(
    artifact_ids: List[str],
    output_path_conventions: Dict[str, Any],
) -> List[str]:
    """Derive target file paths from artifact IDs and output templates."""
    targets: List[str] = []
    for artifact_id in artifact_ids:
        artifact_type = _artifact_type_from_id(artifact_id)
        if not artifact_type:
            continue
        template_entry = output_path_conventions.get(artifact_type)
        if not isinstance(template_entry, dict):
            continue
        output_template = template_entry.get("output_path")
        if not isinstance(output_template, str) or "{target}" not in output_template:
            continue
        target_slug = _artifact_target_from_id(artifact_id, artifact_type)
        if not target_slug:
            continue
        targets.append(output_template.replace("{target}", target_slug))
    return sorted(set(targets))


def _file_type_priority(file_path: str) -> int:
    """Return build-order priority for a file path (lower = earlier).

    Used to add implicit ordering edges when explicit dependencies
    don't capture language-specific build order.

    Priority tiers:
        0 — Protocol/IDL definitions (needed by all services)
        1 — Shared configuration files
        2 — Source code
        3 — Test files
        4 — Build/dependency manifest files
        5 — Wrapper/tooling files (default)
        6 — Deployment files (Dockerfiles, deploy YAMLs)
        7 — Data files
    """
    name = Path(file_path).name.lower()
    suffix = Path(file_path).suffix.lower()

    # Priority 0: Protocol/IDL definitions (needed by all services)
    if suffix == ".proto":
        return 0

    # Priority 1: Shared configuration
    if name in (
        "application.yml", "application.yaml", "application.properties",
        "appsettings.json", "appsettings.development.json",
    ):
        return 1

    # Priority 3: Test files (check BEFORE generic source so test files
    # don't match the source tier)
    if (
        "_test" in name
        or "test_" in name
        or name.endswith("_test.go")
        or (name.startswith("test") and name[4:5] in ("_", "."))
    ):
        return 3

    # Priority 2: Source code
    if suffix in (".go", ".java", ".cs", ".py", ".js", ".ts", ".tsx"):
        return 2

    # Priority 4: Build/dependency files
    if name in (
        "go.mod", "go.sum", "build.gradle", "settings.gradle",
        "pom.xml", "package.json", "requirements.txt", "pyproject.toml",
    ) or suffix in (".csproj", ".sln", ".gradle"):
        return 4

    # Priority 6: Deployment files
    if name.startswith("dockerfile") or name == "dockerfile":
        return 6
    if suffix in (".yaml", ".yml") and "deploy" in name:
        return 6

    # Priority 5: Wrapper/tooling files
    if "wrapper" in name or suffix == ".properties":
        return 5

    # Priority 7: Data files
    if suffix in (".json", ".xml", ".csv"):
        return 7

    # Default: middle priority
    return 5


def _extract_service_dir(file_path: str) -> str:
    """Extract the service directory from a file path.

    Returns the first path component after ``src/`` if present,
    otherwise the first path component. Returns ``""`` for
    top-level files with no directory component.
    """
    parts = file_path.replace("\\", "/").split("/")
    # Look for src/ prefix and use the component after it
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts) - 1:
            return parts[i + 1]
    # Fallback: first directory component (if any)
    if len(parts) >= 2:
        return parts[0]
    return ""


def _break_task_dependency_cycles(
    tasks: List[Dict[str, Any]],
) -> List[tuple]:
    """Detect and break cycles in a task dependency list.

    Builds an adjacency graph from ``depends_on``, runs iterative DFS
    to find back-edges, removes them, and mutates tasks in place.
    Returns the list of broken ``(src_task_id, dst_task_id)`` edges.
    """
    WHITE, GRAY, BLACK = 0, 1, 2

    # Build adjacency as task_id -> list[task_id]
    adj: Dict[str, List[str]] = {}
    for t in tasks:
        tid = t["task_id"]
        adj[tid] = list(t.get("depends_on", []))

    # Ensure all dependency targets are in colour map
    color: Dict[str, int] = {n: WHITE for n in adj}
    for deps in adj.values():
        for d in deps:
            if d not in color:
                color[d] = WHITE

    broken: List[tuple] = []
    for start in list(adj):
        if color[start] != WHITE:
            continue
        stack = [(start, 0)]
        while stack:
            node, idx = stack.pop()
            children = adj.get(node, [])
            if idx == 0:
                color[node] = GRAY
            if idx < len(children):
                stack.append((node, idx + 1))
                child = children[idx]
                if color.get(child, WHITE) == GRAY:
                    broken.append((node, child))
                    children.remove(child)
                    stack[-1] = (node, idx)
                elif color.get(child, WHITE) == WHITE:
                    stack.append((child, 0))
            else:
                color[node] = BLACK

    # Propagate removals back to task dicts
    if broken:
        for t in tasks:
            t["depends_on"] = list(adj.get(t["task_id"], []))

    return broken


def _inject_build_order_dependencies(
    tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Add implicit build-order dependencies between tasks (REQ-PLI-601).

    When two tasks in the same service directory have no explicit dependency
    relationship, this function adds an implicit ``depends_on`` edge from
    higher-priority (later in build order) to lower-priority (earlier in
    build order) tasks.

    Rules:
    - Group tasks by service directory (via :func:`_extract_service_dir`).
    - Within each group, for tasks with no existing ordering relationship,
      add an edge from the higher-priority task to the lower-priority task.
    - Do NOT add edges across different service directories.
    - Do NOT override explicit ``depends_on`` — only add new edges.
    - Run :func:`_break_task_dependency_cycles` after injection to catch
      any cycles introduced.
    """
    if len(tasks) <= 1:
        return tasks

    # Build transitive closure of existing dependencies so we don't
    # add edges that create redundant paths or contradict existing ordering.
    existing_deps: Dict[str, set] = {}
    for t in tasks:
        existing_deps[t["task_id"]] = set(t.get("depends_on", []))

    def _transitive_deps(
        tid: str, cache: Dict[str, set], visiting: Optional[set] = None,
    ) -> set:
        if tid in cache:
            return cache[tid]
        # Guard against cycles in pre-existing deps (broken later by
        # _break_task_dependency_cycles, but we run before that).
        if visiting is None:
            visiting = set()
        if tid in visiting:
            return set()
        visiting.add(tid)
        result: set = set()
        for dep in existing_deps.get(tid, set()):
            result.add(dep)
            result.update(_transitive_deps(dep, cache, visiting))
        cache[tid] = result
        return result

    trans_cache: Dict[str, set] = {}
    for t in tasks:
        _transitive_deps(t["task_id"], trans_cache)

    # Group tasks by service directory
    service_groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        ctx = t.get("config", {}).get("context", {})
        target_files = ctx.get("target_files", [])
        if not target_files:
            continue
        svc_dir = _extract_service_dir(target_files[0])
        if not svc_dir:
            continue
        service_groups.setdefault(svc_dir, []).append(t)

    # Within each service group, add implicit ordering edges
    edges_added = 0
    for _svc_dir, group in service_groups.items():
        if len(group) <= 1:
            continue

        # Compute priority for each task (use minimum priority across
        # target files — a task is "ready" as early as its earliest file)
        task_priorities: List[tuple] = []
        for t in group:
            ctx = t.get("config", {}).get("context", {})
            target_files = ctx.get("target_files", [])
            prio = min(
                (_file_type_priority(f) for f in target_files),
                default=5,
            )
            task_priorities.append((prio, t))

        # Sort by priority (lowest = earliest in build order)
        task_priorities.sort(key=lambda x: x[0])

        # For each pair where later-build-order depends on earlier,
        # add an edge if no existing relationship
        for i, (prio_i, task_i) in enumerate(task_priorities):
            tid_i = task_i["task_id"]
            for j in range(i + 1, len(task_priorities)):
                prio_j, task_j = task_priorities[j]
                tid_j = task_j["task_id"]

                if prio_i == prio_j:
                    # Same priority tier — no implicit ordering
                    continue

                # task_j has higher priority number (later in build order)
                # so it should depend on task_i (earlier in build order)
                # Skip if there's already a relationship in either direction
                if tid_i in trans_cache.get(tid_j, set()):
                    continue  # already depends (directly or transitively)
                if tid_j in trans_cache.get(tid_i, set()):
                    continue  # reverse dependency exists — don't contradict

                deps_j = task_j.get("depends_on", [])
                if tid_i not in deps_j:
                    deps_j.append(tid_i)
                    task_j["depends_on"] = deps_j
                    edges_added += 1

    if edges_added:
        logger.info(
            "REQ-PLI-601: injected %d implicit build-order dependency edge(s)",
            edges_added,
        )
        # Run cycle detection to catch any introduced cycles
        broken = _break_task_dependency_cycles(tasks)
        if broken:
            logger.warning(
                "REQ-PLI-601: broke %d cycle(s) introduced by build-order "
                "injection: %s",
                len(broken),
                ", ".join(f"{a}->{b}" for a, b in broken),
            )

    return tasks


# ---------------------------------------------------------------------------
# REQ-QPA-300/301: Security enrichment for seed derivation
# ---------------------------------------------------------------------------

# Additional keywords that indicate security-sensitive features but may
# not trigger detect_database_type (which looks for specific DB names).
_SECURITY_KEYWORDS = frozenset({
    "credential", "secret", "connection string", "api key", "auth token",
    "password", "connection pool", "data store",
})


def _detect_database_for_enrichment(text: str) -> Optional[str]:
    """Detect database type from text using query_prime decomposer.

    Returns the database type value string (e.g. "postgresql") or None.
    Uses a lazy import to avoid hard dependency on query_prime.
    """
    try:
        from startd8.query_prime.decomposer import detect_database_type
        db = detect_database_type(text)
        return db.value if db is not None else None
    except ImportError:
        return None


def _has_security_keywords(text: str) -> bool:
    """Check if text contains security-sensitive keywords (REQ-QPA-300)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _SECURITY_KEYWORDS)


def derive_tasks_from_features(
    features: list,
    dependency_graph: Dict[str, List[str]],
    *,
    requirement_to_feature: Optional[Dict[str, List[str]]] = None,
    artifact_to_feature: Optional[Dict[str, List[str]]] = None,
    requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
    output_path_conventions: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Convert ParsedFeatures into task dicts matching prime-route schema."""
    # --- Stage 1: Build feature-ID → task-ID mapping ---
    fid_to_tid: Dict[str, str] = {}
    for idx, feat in enumerate(features, start=1):
        fid_to_tid[feat.feature_id] = f"PI-{idx:03d}"

    # --- Stage 2: Invert requirement/artifact mappings to per-feature ---
    feature_to_requirements: Dict[str, List[str]] = {}
    for rid, fids in (requirement_to_feature or {}).items():
        if not isinstance(rid, str) or not isinstance(fids, list):
            continue
        for fid in fids:
            if isinstance(fid, str):
                feature_to_requirements.setdefault(fid, []).append(rid)
    for fid in feature_to_requirements:
        feature_to_requirements[fid] = sorted(set(feature_to_requirements[fid]))

    feature_to_artifacts: Dict[str, List[str]] = {}
    for aid, fids in (artifact_to_feature or {}).items():
        if not isinstance(aid, str) or not isinstance(fids, list):
            continue
        for fid in fids:
            if isinstance(fid, str):
                feature_to_artifacts.setdefault(fid, []).append(aid)
    for fid in feature_to_artifacts:
        feature_to_artifacts[fid] = sorted(set(feature_to_artifacts[fid]))

    # --- Stage 3: Build task dicts from features ---
    tasks: List[Dict[str, Any]] = []
    for idx, feat in enumerate(features, start=1):
        tid = fid_to_tid[feat.feature_id]
        sp = estimate_story_points(feat.estimated_loc)

        deps = []
        for dep_fid in feat.dependencies:
            dep_tid = fid_to_tid.get(dep_fid)
            if dep_tid:
                deps.append(dep_tid)
        for dep_fid in dependency_graph.get(feat.feature_id, []):
            dep_tid = fid_to_tid.get(dep_fid)
            if dep_tid and dep_tid not in deps:
                deps.append(dep_tid)

        dependent_count = sum(
            1
            for f in features
            if feat.feature_id in dependency_graph.get(f.feature_id, [])
            or feat.feature_id in f.dependencies
        )
        if dependent_count >= 2:
            priority = "high"
        elif dependent_count == 1:
            priority = "medium"
        else:
            priority = "low"

        mapped_artifacts = feature_to_artifacts.get(feat.feature_id, [])
        resolved_target_files = list(feat.target_files)
        if (
            not resolved_target_files
            and mapped_artifacts
            and isinstance(output_path_conventions, dict)
        ):
            resolved_target_files = derive_target_files_from_artifact_ids(
                mapped_artifacts, output_path_conventions,
            )

        pre_filter_count = len(resolved_target_files)
        resolved_target_files = [
            f for f in resolved_target_files if not is_trivial_test_init(f)
        ]
        if not resolved_target_files and pre_filter_count > 0:
            logger.info(
                "Skipping feature %s (%s): all target files are trivial test __init__.py",
                feat.feature_id, feat.name,
            )
            continue

        ordered_files = sorted(
            resolved_target_files,
            key=lambda f: (0 if f.endswith("__init__.py") else 1, f),
        )

        ctx: Dict[str, Any] = {
            "feature_id": feat.feature_id,
            "target_files": ordered_files,
            "estimated_loc": feat.estimated_loc,
        }
        if feat.design_doc_sections:
            ctx["design_doc_sections"] = list(feat.design_doc_sections)
        if feat.artifact_types_addressed:
            ctx["artifact_types_addressed"] = list(feat.artifact_types_addressed)
        elif ordered_files:
            inferred = infer_artifact_types_from_files(ordered_files)
            if inferred:
                ctx["artifact_types_addressed"] = inferred

        mapped_requirements = feature_to_requirements.get(feat.feature_id, [])
        if mapped_requirements:
            ctx["requirement_ids"] = mapped_requirements
            acceptance_obligations: List[str] = []
            source_references: List[str] = []
            for rid in mapped_requirements:
                hint = (requirement_hints or {}).get(rid, {})
                anchors = hint.get("acceptance_anchors", [])
                if isinstance(anchors, list):
                    acceptance_obligations.extend(
                        a for a in anchors if isinstance(a, str)
                    )
                refs = hint.get("source_references", [])
                if isinstance(refs, list):
                    source_references.extend(
                        r for r in refs if isinstance(r, str)
                    )
            if acceptance_obligations:
                ctx["acceptance_obligations"] = sorted(set(acceptance_obligations))
            if source_references:
                ctx["source_references"] = sorted(set(source_references))
            rationale: List[str] = [
                "feature selected via requirement identifier match"
            ]
            if mapped_artifacts:
                rationale.append(
                    "feature also mapped to coverage gaps: "
                    + ", ".join(mapped_artifacts)
                )
            ctx["mapping_rationale"] = rationale

        _req_parts: List[str] = []
        if feat.description:
            _req_parts.append(feat.description)
        if ctx.get("acceptance_obligations"):
            _req_parts.append(
                "Acceptance criteria:\n"
                + "\n".join(f"- {a}" for a in ctx["acceptance_obligations"])
            )
        if ctx.get("source_references"):
            _req_parts.append(
                "Source references:\n"
                + "\n".join(f"- {r}" for r in ctx["source_references"])
            )
        _requirements_text = "\n\n".join(_req_parts)
        if len(_requirements_text) > 2000:
            _requirements_text = _requirements_text[:2000] + " [truncated]"
        if _requirements_text == feat.description:
            _requirements_text = ""

        # REQ-QPA-300/301: Auto-tag security_sensitive from description
        # keywords. Uses detect_database_type from query_prime decomposer
        # to match both description text and target file names.
        if not ctx.get("security_sensitive"):
            _enrich_text = (feat.description or "") + " " + " ".join(ordered_files)
            _detected_db = _detect_database_for_enrichment(_enrich_text)
            if _detected_db is not None:
                ctx["security_sensitive"] = True
                ctx["detected_database"] = _detected_db
            elif _has_security_keywords(feat.description or ""):
                ctx["security_sensitive"] = True

        tasks.append({
            "task_id": tid,
            "title": feat.name,
            "task_type": "task",
            "story_points": sp,
            "priority": priority,
            "labels": list(feat.labels),
            "depends_on": deps,
            "config": {
                "task_description": feat.description,
                "requirements_text": _requirements_text,
                "context": ctx,
            },
        })

    # --- Stage 4: Clean up dangling dependency references ---
    emitted_ids = {t["task_id"] for t in tasks}
    for t in tasks:
        original_deps = t.get("depends_on", [])
        cleaned_deps = [d for d in original_deps if d in emitted_ids]
        if len(cleaned_deps) < len(original_deps):
            dangling = set(original_deps) - emitted_ids
            logger.warning(
                "Task %s: removed %d dangling dependency reference(s): %s",
                t["task_id"], len(dangling), sorted(dangling),
            )
            t["depends_on"] = cleaned_deps

    # --- Stage 5: Post-filters (split oversized, remove trivial inits) ---
    tasks = split_oversized_tasks(tasks, max_files=1)

    for t in tasks:
        tid = t.get("task_id", "")
        if not _SAFE_TASK_ID_PATTERN.match(tid):
            logger.warning(
                "Task ID %r does not match safe pattern", tid,
            )

    tasks = filter_trivial_test_init_tasks(tasks)

    # --- Stage 6: Cross-language build-order dependency injection (REQ-PLI-601) ---
    tasks = _inject_build_order_dependencies(tasks)

    if not tasks and features:
        logger.warning(
            "Zero tasks derived from %d features — all features may have been "
            "filtered. Downstream seed will contain no work items.",
            len(features),
        )

    # --- Stage 7: Final acyclicity safety net ---
    # Catches cycles that survived PARSE-phase graph breaking (e.g. when
    # feature.dependencies wasn't synced with dep_graph mutations).
    if len(tasks) > 1:
        final_broken = _break_task_dependency_cycles(tasks)
        if final_broken:
            logger.warning(
                "Final acyclicity gate broke %d cycle(s): %s",
                len(final_broken),
                ", ".join(f"{a}->{b}" for a, b in final_broken),
            )

    return tasks


def _infer_file_role(file_path: str) -> str:
    """A FILE ROLE CONSTRAINT string for an auto-split sub-task description, or "".

    When a multi-file task is split into single-file sub-tasks, the parent description can mislead
    the LLM about a non-source file's content. This appends a role constraint guiding it to the
    correct content for the target file type (interface-only, Dockerfile, project/build config,
    proto). (Restored into the seeds split path — it was dropped when split_oversized_tasks was
    extracted here, orphaning the original helper.)
    """
    name = file_path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if name.endswith(".cs") and stem.startswith("I") and len(stem) > 1 and stem[1].isupper():
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is an INTERFACE file. "
            f"Generate ONLY the `{stem}` interface definition with method signatures. "
            f"Do NOT include any implementation classes."
        )
    if name.endswith(".java") and stem.endswith("Interface"):
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is an INTERFACE file. "
            f"Generate ONLY the interface definition with method signatures. "
            f"Do NOT include any implementation classes."
        )
    if stem.lower().startswith("dockerfile") or name.lower() == "dockerfile":
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is a Dockerfile. "
            f"Generate ONLY Docker build instructions."
        )
    if name.endswith((".csproj", ".sln")):
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is a project configuration file. "
            f"Generate ONLY the project/solution XML or format — no source code."
        )
    if name in ("build.gradle", "build.gradle.kts", "settings.gradle", "pom.xml"):
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is a build configuration file. "
            f"Generate ONLY build configuration — no source code."
        )
    if name.endswith(".proto"):
        return (
            f"\n**FILE ROLE CONSTRAINT**: `{name}` is a Protocol Buffer definition. "
            f"Generate ONLY protobuf service/message definitions."
        )
    return ""


def split_oversized_tasks(
    tasks: List[Dict[str, Any]],
    max_files: int = 1,
) -> List[Dict[str, Any]]:
    """Gate 2a: Split tasks with more than *max_files* target files."""
    result: List[Dict[str, Any]] = []

    for task in tasks:
        ctx = task.get("config", {}).get("context", {})
        target_files = ctx.get("target_files", [])

        if len(target_files) <= max_files:
            result.append(task)
            continue

        parent_id = task["task_id"]
        parent_deps = list(task.get("depends_on", []))
        parent_desc = task.get("config", {}).get("task_description", "")
        estimated_loc = ctx.get("estimated_loc", 0)
        loc_per_file = max(estimated_loc // len(target_files), 10)

        logger.info(
            "Gate 2a: splitting task %s (%d files > max %d) into %d sub-tasks",
            parent_id, len(target_files), max_files, len(target_files),
        )

        init_files = [f for f in target_files if f.endswith("__init__.py")]
        non_init_files = [f for f in target_files if not f.endswith("__init__.py")]
        ordered = init_files + non_init_files

        init_sub_id = None
        for idx, target_file in enumerate(ordered):
            # a-z for first 26 sub-tasks, then numeric suffix for overflow
            suffix = chr(ord("a") + idx) if idx < 26 else f"-{idx + 1:02d}"
            sub_id = f"{parent_id}{suffix}"

            sub_deps = list(parent_deps)
            if init_sub_id and sub_id != init_sub_id:
                sub_deps.append(init_sub_id)

            if target_file.endswith("__init__.py"):
                init_sub_id = sub_id

            sub_ctx: Dict[str, Any] = {
                "feature_id": ctx.get("feature_id", ""),
                "target_files": [target_file],
                "estimated_loc": loc_per_file,
                "_split_from": parent_id,
                "_split_index": idx,
            }
            for key in (
                "design_doc_sections", "artifact_types_addressed",
                "requirement_ids", "acceptance_obligations",
                "source_references", "mapping_rationale",
            ):
                if key in ctx:
                    sub_ctx[key] = ctx[key]

            file_name = target_file.rsplit("/", 1)[-1]
            sub_title = f"{task['title']} — {file_name}"

            result.append({
                "task_id": sub_id,
                "title": sub_title,
                "task_type": task.get("task_type", "task"),
                "story_points": estimate_story_points(loc_per_file),
                "priority": task.get("priority", "medium"),
                "labels": list(task.get("labels", [])),
                "depends_on": sub_deps,
                "config": {
                    "task_description": (
                        f"{parent_desc}\n\n"
                        f"[Auto-split from {parent_id}: implement "
                        f"`{target_file}` only.]"
                        f"{_infer_file_role(target_file)}"
                    ),
                    "requirements_text": task.get("config", {}).get(
                        "requirements_text", ""
                    ),
                    "context": sub_ctx,
                },
            })

    return result


def filter_trivial_test_init_tasks(
    tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Gate 2b: Remove tasks whose sole target file is a test ``__init__.py``."""
    filtered_ids: set[str] = set()
    result: List[Dict[str, Any]] = []
    for task in tasks:
        tf = task.get("config", {}).get("context", {}).get("target_files", [])
        if len(tf) == 1 and is_trivial_test_init(tf[0]):
            filtered_ids.add(task["task_id"])
            logger.info(
                "Gate 2b: filtering trivial test init task %s (%s)",
                task["task_id"], tf[0],
            )
        else:
            result.append(task)
    if filtered_ids:
        for task in result:
            task["depends_on"] = [
                d for d in task.get("depends_on", []) if d not in filtered_ids
            ]
    return result


def derive_architectural_context(
    parsed_plan: Any,
    manifest_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Combine manifest data with deterministic cross-feature analysis."""
    ctx: Dict[str, Any] = {
        "project_goals": list(parsed_plan.goals),
        "objectives": manifest_context.get("objectives", []),
        "constraints": manifest_context.get("constraints", []),
        "preferences": manifest_context.get("preferences", []),
        "focus_areas": manifest_context.get("focus_areas", []),
    }

    file_counter: Counter[str] = Counter()
    file_features: Dict[str, List[str]] = {}
    for feat in parsed_plan.features:
        for tf in feat.target_files:
            file_counter[tf] += 1
            file_features.setdefault(tf, []).append(feat.feature_id)
    ctx["shared_modules"] = [
        {"path": path, "features": file_features[path]}
        for path, count in file_counter.items()
        if count >= 2
    ]

    dir_counter: Counter[str] = Counter()
    for feat in parsed_plan.features:
        for tf in feat.target_files:
            parent = str(Path(tf).parent)
            if parent != ".":
                dir_counter[parent] += 1
    ctx["import_conventions"] = [d for d, _ in dir_counter.most_common(5)]

    concepts: list[str] = []
    for goal in parsed_plan.goals:
        for m in re.findall(r"\(([^)]+)\)", goal):
            concepts.extend(t.strip() for t in m.split(",") if t.strip())
        concepts.extend(
            re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", goal)
        )
    ctx["domain_concepts"] = list(dict.fromkeys(concepts))[:20]

    dep_graph = parsed_plan.dependency_graph
    depended_upon: set[str] = set()
    for deps in dep_graph.values():
        depended_upon.update(deps)
    has_deps: set[str] = set(dep_graph.keys())
    root_ids = [
        fid for fid in depended_upon
        if fid not in has_deps or not dep_graph.get(fid)
    ]

    clusters: list[Dict[str, Any]] = []
    for root_id in root_ids[:10]:
        dependents: list[str] = []
        for fid, deps in dep_graph.items():
            if root_id in deps:
                dependents.append(fid)
        if dependents:
            clusters.append({"root": root_id, "dependents": dependents})
    ctx["dependency_clusters"] = clusters

    return ctx


def derive_design_calibration(
    tasks: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Derive per-task design depth calibration."""
    estimator = None
    try:
        from contextcore.agent.size_estimation import SizeEstimator
        estimator = SizeEstimator()
    except ImportError:
        logger.debug("SizeEstimator unavailable — using LOC-based complexity")

    calibration: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        ctx = task.get("config", {}).get("context", {})
        loc = ctx.get("estimated_loc", 100)
        desc = task.get("config", {}).get("task_description", "")

        if estimator:
            try:
                estimate = estimator.estimate(
                    task=desc,
                    inputs={"context_files": ctx.get("target_files", [])},
                )
                complexity = estimate.complexity
            except Exception:
                logger.debug(
                    "SizeEstimator failed for task %s — falling back to LOC",
                    task.get("task_id", "?"),
                    exc_info=True,
                )
                complexity = _classify_complexity(loc)
        else:
            complexity = _classify_complexity(loc)

        tier_name = {
            "low": "brief",
            "medium": "standard",
            "high": "comprehensive",
        }.get(complexity, "standard")
        tier = DEPTH_TIERS[tier_name]

        implement_tokens = {
            "brief": 16384,
            "standard": 32768,
            "comprehensive": 49152,
        }.get(tier_name, 32768)

        enrichment = task.get("_enrichment", {})
        domain = enrichment.get("domain")
        if not domain:
            target_files = ctx.get("target_files", [])
            if target_files:
                ext = (
                    target_files[0].rsplit(".", 1)[-1].lower()
                    if "." in target_files[0]
                    else ""
                )
                if ext in ("toml", "yaml", "yml", "json", "ini", "cfg"):
                    domain = f"config-{ext.replace('yml', 'yaml')}"
                elif ext == "py":
                    if any(
                        os.path.basename(tf).startswith("test_")
                        or os.path.basename(tf).endswith("_test.py")
                        or "/tests/" in tf
                        or "/test/" in tf
                        for tf in target_files
                    ):
                        domain = "python-test"
                    else:
                        domain = "python-single-module"
                elif ext and ext not in ("py",):
                    domain = "non-python"
            if not domain:
                domain = "unknown"
        domain_token_multipliers = {
            "config-toml": 0.5, "config-yaml": 0.5, "config-json": 0.5,
            "config-ini": 0.5, "config-cfg": 0.5,
            "non-python": 0.6, "python-test": 0.8,
            "python-single-module": 1.0, "python-package-module": 1.0,
            "unknown": 1.0,
        }
        domain_multiplier = domain_token_multipliers.get(domain, 1.0)
        if domain_multiplier != 1.0:
            implement_tokens = int(implement_tokens * domain_multiplier)

        calibration[task["task_id"]] = {
            "depth_tier": tier_name,
            "sections": tier["sections"],
            "max_output_tokens": tier["max_tokens"],
            "implement_max_output_tokens": implement_tokens,
            "depth_guidance": tier["guidance"],
            "complexity": complexity,
        }
    return calibration
