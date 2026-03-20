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

    # REQ-PLI-NODE-104: Detect Node.js frameworks from plan text
    _primary_lang_str = lang_id
    if _primary_lang_str == "nodejs":
        detected_frameworks: list[str] = []
        scan_text = " ".join(
            getattr(f, "description", "") + " " + " ".join(getattr(f, "api_signatures", []))
            for f in features
        ).lower()

        _NODEJS_FRAMEWORK_SIGNALS = {
            "express": ["express", "app.get(", "app.use(", "app.post(", "middleware", "router"],
            "grpc": ["grpc", "protobuf", ".proto", "@grpc/", "grpc-js", "proto-loader"],
            "react": ["react", "jsx", "usestate", "useeffect", "component", "next.js", "nextjs"],
            "nestjs": ["nestjs", "@nestjs/", "controller", "@injectable", "@module"],
            "fastify": ["fastify"],
            "koa": ["koa"],
        }

        for framework, keywords in _NODEJS_FRAMEWORK_SIGNALS.items():
            if any(kw in scan_text for kw in keywords):
                detected_frameworks.append(framework)

        if detected_frameworks:
            metadata["detected_frameworks"] = detected_frameworks
            logger.info(
                "Node.js framework detection: %s",
                ", ".join(detected_frameworks),
            )

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

    if not tasks and features:
        logger.warning(
            "Zero tasks derived from %d features — all features may have been "
            "filtered. Downstream seed will contain no work items.",
            len(features),
        )

    return tasks


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
