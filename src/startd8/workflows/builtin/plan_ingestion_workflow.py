"""
PlanIngestionWorkflow — Parse a generic plan, assess complexity,
transform into SDK-native format, refine via architectural review,
and emit the plan doc + review-config.json.

Pipeline:  parse → assess → transform → refine → emit
"""

from __future__ import annotations

import json
import os
import re
import time
from hashlib import sha256
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace as _dataclass_replace
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

import yaml

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    AgentCount,
    StepResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)
from ...agents import BaseAgent
from ...agents.pool import TimeoutConfig
from ...model_catalog import Models
from ...utils.agent_resolution import resolve_agent_spec
from ...utils.code_extraction import extract_code_from_response
from ...utils.file_operations import atomic_write, atomic_write_json
from ...utils.retry import RetryConfig
from ...utils.token_usage import token_usage_input, token_usage_output, token_usage_cost

from .plan_ingestion_models import (
    ArtisanContextSeed,
    ComplexityScore,
    ContractorRoute,
    IngestionPhase,
    IngestionState,
    ParsedFeature,
    ParsedPlan,
)
from ...contractors.artisan_contractor import _SAFE_TASK_ID_PATTERN, _NoOpSpan, _NoOpTracer
from ...logging_config import get_logger

# OTel graceful degradation (follows artisan_contractor.py pattern)
try:
    from opentelemetry import trace as _trace
    from opentelemetry.trace import StatusCode as _StatusCode
    _HAS_OTEL = True
    _tracer = _trace.get_tracer("startd8.plan_ingestion")
except ImportError:
    _HAS_OTEL = False
    _tracer = _NoOpTracer()
    _StatusCode = None

logger = get_logger(__name__)

# File-extension → language mapping for service metadata inference
_EXT_TO_LANGUAGE: Dict[str, str] = {
    "py": "python", "go": "go", "js": "javascript",
    "ts": "typescript", "rs": "rust", "java": "java",
    "rb": "ruby", "cs": "csharp",
}

# JSON Schema for ArtisanContextSeed (Item 6 — validation before write)
_ARTISAN_SEED_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["version", "tasks", "artifacts", "ingestion_metrics"],
    "properties": {
        "version": {"type": "string"},
        "schema_version": {"type": "string"},
        "source_checksum": {"type": ["string", "null"]},
        "generated_at": {"type": "string"},
        "generator": {"type": "string"},
        "plan": {"type": ["object", "null"]},
        "complexity": {"type": ["object", "null"]},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["task_id", "title", "config"],
                "properties": {
                    "task_id": {"type": "string"},
                    "title": {"type": "string"},
                    "config": {"type": "object"},
                },
            },
        },
        "artifacts": {"type": "object"},
        "ingestion_metrics": {"type": "object"},
        "onboarding": {"type": ["object", "null"]},
        "architectural_context": {"type": ["object", "null"]},
        "design_calibration": {"type": ["object", "null"]},
        "context_files": {"type": ["array", "null"]},
        "service_metadata": {"type": ["object", "null"]},
        "wave_metadata": {"type": ["object", "null"]},
        "lane_assignments": {"type": ["object", "null"]},
        "project_metadata": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}


def _sha256_file_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    hasher = sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_context_seed(data: Dict[str, Any]) -> bool:
    """Validate context seed against JSON schema before write (Item 6).

    Uses jsonschema if installed; no-op otherwise.
    Returns True if valid (or jsonschema not installed), False if validation failed.
    """
    try:
        import jsonschema

        jsonschema.validate(data, _ARTISAN_SEED_SCHEMA)
        logger.debug("Context seed validated against schema")
        return True
    except ImportError:
        return True  # Graceful fallback — jsonschema not installed
    except Exception as e:
        logger.warning(
            "Context seed schema validation failed: %s — writing anyway",
            str(e),
        )
        return False




def _validate_seed_field_coverage(seed_dict: Dict[str, Any]) -> List[str]:
    """Advisory validation: check field coverage for seed quality (Task 12).

    Distinct from _validate_context_seed() which validates JSON schema.
    This checks whether important optional fields are populated to ensure
    downstream phases have sufficient context.

    Returns:
        List of advisory warning strings (empty = all fields well-populated).
    """
    warnings: List[str] = []

    # Check tasks have sufficient detail
    tasks = seed_dict.get("tasks", [])
    if not tasks:
        warnings.append("seed has no tasks")
        return warnings

    tasks_missing_targets = sum(
        1 for t in tasks if not t.get("config", {}).get("context", {}).get("target_files")
    )
    if tasks_missing_targets > 0:
        warnings.append(
            f"{tasks_missing_targets}/{len(tasks)} task(s) missing target_files"
        )

    tasks_missing_description = sum(
        1 for t in tasks if not t.get("config", {}).get("task_description")
    )
    if tasks_missing_description > 0:
        warnings.append(
            f"{tasks_missing_description}/{len(tasks)} task(s) missing description"
        )

    # Check optional enrichment fields
    if not seed_dict.get("architectural_context"):
        warnings.append("no architectural_context — design phase may lack shared context")

    if not seed_dict.get("design_calibration"):
        warnings.append("no design_calibration — design depth tiers unavailable")

    if not seed_dict.get("service_metadata"):
        warnings.append("no service_metadata — protocol fidelity validators will be skipped")

    if not seed_dict.get("onboarding"):
        warnings.append("no onboarding metadata — parameter sources unavailable")

    if not seed_dict.get("context_files"):
        warnings.append("no context_files — provenance tracking limited")

    if not seed_dict.get("project_metadata"):
        warnings.append(
            "no project_metadata — criticality/SLO-aware generation unavailable"
        )

    return warnings


def _log_seed_coverage(seed_dict: Dict[str, Any], label: str = "") -> None:
    """Run advisory field-coverage check and log any warnings."""
    warnings = _validate_seed_field_coverage(seed_dict)
    if warnings:
        tag = f" [{label}]" if label else ""
        logger.warning(
            "Seed field-coverage advisory%s (%d warning(s)): %s",
            tag, len(warnings), "; ".join(warnings),
        )


def _ensure_onboarding_in_context_files(
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
            context_files_list.append({
                "path": str(ob_path),
                "checksum": _sha256_file_hex(ob_path),
            })
            logger.info("REQ-PI-014: added onboarding-metadata.json to context_files")


# ---------------------------------------------------------------------------
# LLM prompt templates
# ---------------------------------------------------------------------------

_PARSE_PROMPT = """\
You are an expert software architect. Analyze the following implementation plan \
and extract structured information.

<plan>
{plan_text}
</plan>

Return a JSON object (no markdown fences) with exactly these keys:
{{
  "title": "string — plan title",
  "goals": ["string — each high-level goal"],
  "features": [
    {{
      "feature_id": "F-001",
      "name": "short name",
      "description": "what this feature does",
      "target_files": ["path/to/file.py"],
      "dependencies": ["F-002"],
      "estimated_loc": 100,
      "labels": ["label"],
      "design_doc_sections": ["optional task-specific design hints e.g. Parameter validation", "Error handling"],
      "artifact_types_addressed": ["optional artifact types e.g. servicemonitor", "prometheus_rule"],
      "api_signatures": ["Class MyClass(BaseClass)", "def my_function(arg: str) -> bool", "Method serve(request, context)"],
      "protocol": "grpc or http or cli or library or none",
      "runtime_dependencies": ["grpcio==1.60.0", "flask>=3.0"],
      "negative_scope": ["things explicitly excluded from this feature"]
    }}
  ],
  "mentioned_files": ["every file path mentioned in the plan"],
  "dependency_graph": {{"F-001": ["F-002"]}}
}}

## target_files guidance

Each feature becomes ONE implementation task sent to a code-generation LLM.
Multi-file tasks reliably fail — the LLM drops files or produces partial output.

Rules for target_files:
1. ALWAYS assign exactly ONE file per feature. If a change spans multiple
   files, create separate features with dependencies between them.
2. Do NOT create features targeting test `__init__.py` files
   (e.g. `tests/__init__.py`, `tests/unit/__init__.py`). Python 3 + pytest
   do not require them — they are wasted implementation slots.

design_doc_sections: optional list of content hints to emphasize in the design doc (e.g. parameter validation, error handling). Omit or empty if not applicable.
artifact_types_addressed: optional list of artifact types this feature generates (e.g. servicemonitor, prometheus_rule, dashboard). Omit or empty if not applicable.
api_signatures: list of class, function, and method signatures defined or implemented by this feature. Extract these from "Implementation contract", "API", "Interface", or signature sections in the plan. Use the format "Class ClassName(BaseClass)", "def function_name(param: type) -> return_type", or "Method name(params)". Include ALL signatures mentioned for the feature.
protocol: transport protocol — one of "grpc", "http", "cli", "library", or "none". Infer from the plan (e.g. gRPC service → "grpc", Flask/REST → "http", CLI tool → "cli", utility module → "library").
runtime_dependencies: list of third-party packages with version constraints mentioned in the plan for this feature (e.g. "grpcio==1.60.0", "flask>=3.0"). Only include explicit dependencies, not stdlib.
negative_scope: list of things explicitly excluded or out-of-scope for this feature, if mentioned in the plan.

Be thorough. Extract every feature, file reference, and dependency.
"""

_ASSESS_PROMPT = """\
You are a complexity assessor for software plans.

<plan_summary>
Title: {title}
Goals: {goals}
Feature count: {feature_count}
Features: {feature_summary}
Files mentioned: {file_count}
</plan_summary>

Score the plan on these 7 dimensions (each 0–100):
1. feature_count — number and granularity of features
2. cross_file_deps — how many features touch multiple files
3. api_surface — breadth of public API changes
4. test_complexity — difficulty of testing
5. integration_depth — how deeply it integrates with existing code
6. domain_novelty — how novel the domain concepts are
7. ambiguity — how ambiguous or under-specified the plan is

Then compute a composite score (weighted average, 0–100).

Routing rule: composite ≤ {threshold} → "prime", else → "artisan".

Return JSON (no markdown fences):
{{
  "feature_count": 0,
  "cross_file_deps": 0,
  "api_surface": 0,
  "test_complexity": 0,
  "integration_depth": 0,
  "domain_novelty": 0,
  "ambiguity": 0,
  "composite": 0,
  "reasoning": "one paragraph explaining the score and routing decision",
  "route": "prime or artisan"
}}
"""

_TRANSFORM_PRIME_PROMPT = """\
You are a task YAML generator for the PrimeContractor workflow.

Convert the following parsed plan into a task YAML file matching this schema:

```yaml
project:
  id: <project-id>
  name: <project-name>
  sprint_id: <sprint-id>

tasks:
  - task_id: <ID>
    title: "short title"
    task_type: task
    story_points: <1-8>
    priority: <high|medium|low>
    labels: [label1, label2]
    depends_on: [<other-task-id>]
    config:
      task_description: |
        Detailed implementation instructions...
      context:
        existing_code: ""
```

<plan>
Title: {title}
Goals: {goals}
Features:
{features}
Dependency graph: {dependency_graph}
</plan>

Generate valid YAML. Use task IDs like PI-001, PI-002, etc.
Include dependency edges from the dependency graph.
Each task should have a thorough task_description.
"""

_TRANSFORM_ARTISAN_PROMPT = """\
You are a plan document generator for the ArtisanContractor workflow.

Convert the following parsed plan into a structured markdown plan document.

The document must have these sections:
1. **Overview** — title, goals, scope
2. **Data Models** — key data structures
3. **Architecture** — component diagram, file layout
4. **Phase Breakdown** — implementation phases with deliverables
5. **Cost Model** — estimated token usage per phase
6. **Risk Register** — risks and mitigations
7. **Verification** — test strategy, acceptance criteria
8. **Dependencies** — external deps, inter-feature deps

<plan>
Title: {title}
Goals: {goals}
Features:
{features}
Mentioned files: {mentioned_files}
Dependency graph: {dependency_graph}
</plan>

Generate a complete, well-structured markdown document.
Use ## for top-level sections, ### for subsections.
"""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INPUT_TRUNCATION = 200   # Max chars of prompt stored in StepResult.input
_OUTPUT_TRUNCATION = 500  # Max chars of response stored in StepResult.output
_REQ_ID_PATTERN = re.compile(r"\b(?:REQ|FR|NFR|R)[-_]?\d+\b", re.IGNORECASE)

# Depth tier calibration — channel adaptation pattern
# (brief/standard/comprehensive map to feature complexity)
# Design docs can hit limits with multiple sections + code blocks + reviewer iterations.
# Claude 4.5 supports up to 64K output; these values avoid truncation (stop_reason=max_tokens).
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
            "Overview", "Architecture", "Data Model",
            "Error Handling", "Testing Strategy",
        ],
        "max_tokens": 8192,
        "guidance": (
            "Standard design doc. Include data model and error handling "
            "but keep depth proportional to the feature's scope."
        ),
    },
    "comprehensive": {
        "sections": [
            "Overview", "Architecture", "Data Model",
            "API Contracts", "Error Handling",
            "Security Considerations", "Testing Strategy",
        ],
        "max_tokens": 16384,
        "guidance": (
            "Comprehensive design. All sections are warranted for this "
            "complex feature — address security and API contracts thoroughly."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json_from_response(response: str) -> dict:
    """Extract JSON from an LLM response, handling code fences."""
    text = extract_code_from_response(response, language="json")
    return json.loads(text)


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
            set(
                re.findall(
                    r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)`",
                    block,
                )
            )
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


def _checksum_file(path: Path) -> Optional[str]:
    """Return SHA-256 checksum for file content, or None if unreadable."""
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _resolve_path(path_str: str, base_dir: Path) -> Path:
    """Resolve absolute or relative path against base directory."""
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def _normalize_artifact_type(raw: str) -> str:
    """Normalize artifact type labels to underscore format."""
    return raw.strip().lower().replace("-", "_")


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
    # Unrecognized pattern — return None rather than guessing from
    # arbitrary ID structure (e.g., "api-gateway-v2" → "gateway_v2" is wrong).
    return None


def _artifact_target_from_id(artifact_id: str, artifact_type: str) -> Optional[str]:
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


def _infer_artifact_types_from_files(files: List[str]) -> List[str]:
    """Infer artifact types from target file names (Mottainai Phase 2.2).

    Returns a deduplicated list of artifact type strings.  Only applies
    deterministic, zero-cost heuristics — no LLM involved.
    """
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
        elif any(name.endswith(ext) for ext in (
            ".py", ".go", ".js", ".ts", ".rs", ".java", ".rb", ".cs",
        )):
            inferred = "source_module"
        if inferred and inferred not in seen:
            types.append(inferred)
            seen.add(inferred)
    return types


def _infer_service_metadata(
    features: List[ParsedFeature],
    onboarding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Infer service-level metadata from features and onboarding data.

    Extracts transport protocol, runtime dependencies, and API surface
    from ParsedFeature fields. Falls back to onboarding metadata if present.

    Returns:
        Dict with keys: transport_protocol, runtime_dependencies,
        primary_language, api_signatures, negative_scope.
    """
    protocols: list[str] = []
    all_runtime_deps: list[str] = []
    all_api_sigs: list[str] = []
    all_negative_scope: list[str] = []
    languages: list[str] = []

    for f in features:
        if f.protocol:
            protocols.append(f.protocol)
        all_runtime_deps.extend(f.runtime_dependencies)
        all_api_sigs.extend(f.api_signatures)
        all_negative_scope.extend(f.negative_scope)
        # Infer language from target files
        for tf in f.target_files:
            # Extract extension after last dot, or empty string if no dot
            ext = tf.rsplit(".", 1)[-1].lower() if "." in tf else ""
            lang = _EXT_TO_LANGUAGE.get(ext)
            if lang and lang not in languages:
                languages.append(lang)

    # Determine dominant protocol
    transport = ""
    if protocols:
        transport = Counter(protocols).most_common(1)[0][0]
    elif onboarding:
        transport = onboarding.get("transport_protocol", "") or ""

    # Deduplicate
    runtime_deps = sorted(set(all_runtime_deps))
    api_sigs = list(dict.fromkeys(all_api_sigs))  # preserve order, dedup
    negative_scope = list(dict.fromkeys(all_negative_scope))

    metadata: Dict[str, Any] = {}
    if transport:
        metadata["transport_protocol"] = transport
    if runtime_deps:
        metadata["runtime_dependencies"] = runtime_deps
    if languages:
        metadata["primary_language"] = languages[0] if len(languages) == 1 else languages
    if api_sigs:
        metadata["api_signatures"] = api_sigs
    if negative_scope:
        metadata["negative_scope"] = negative_scope

    return metadata


def _derive_target_files_from_artifact_ids(
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


def _extract_requirement_ids(requirements_text: str) -> List[str]:
    """Extract likely requirement IDs from requirements corpus."""
    found = [m.group(0).upper() for m in _REQ_ID_PATTERN.finditer(requirements_text)]
    if found:
        return sorted(set(found))

    # Synthetic IDs (REQ-LINE-*) never appear in feature text, guaranteeing
    # unmapped status and inflating quality gate metrics.  Return empty
    # list so coverage is computed only from real requirement IDs.
    return []


def _load_requirements_documents(requirements_files: List[str], base_dir: Path) -> Dict[str, str]:
    """Load requirement document content by resolved path."""
    docs: Dict[str, str] = {}
    for raw in requirements_files:
        resolved = _resolve_path(raw, base_dir)
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            docs[str(resolved)] = resolved.read_text(encoding="utf-8")
        except OSError:
            continue
    return docs


def _normalize_requirements_hints(
    onboarding: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build requirement-hint index keyed by requirement ID."""
    if not isinstance(onboarding, dict):
        return {}
    raw_hints = onboarding.get("requirements_hints")
    if not isinstance(raw_hints, list):
        return {}
    hints: Dict[str, Dict[str, Any]] = {}
    for item in raw_hints:
        if not isinstance(item, dict):
            continue
        rid = item.get("id")
        if not isinstance(rid, str) or not rid.strip():
            continue
        rid_norm = rid.strip().upper()
        hints[rid_norm] = item
    return hints


def _context_files_with_checksums(
    context_files: Optional[List[str]],
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build context_files list with optional checksums for seed/handoff.

    Args:
        context_files: List of file paths.
        base_dir: Base directory for resolving relative paths (default: cwd).

    Returns:
        List of {"path": str, "checksum": str | None} dicts.
    """
    if not context_files:
        return []
    import hashlib
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
        except (OSError, PermissionError):
            entry["checksum"] = None
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Emit result type
# ---------------------------------------------------------------------------


class EmitResult(NamedTuple):
    """Typed return value from ``_phase_emit``."""
    config_path: Path
    review_config: dict
    context_seed_path: Optional[Path]
    tracking_result: Optional[Dict[str, Any]]
    tasks: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class PlanIngestionWorkflow(WorkflowBase):
    """
    Automates the pipeline: parse a generic plan → LLM-assess complexity →
    transform into SDK-native format → auto-refine via architectural review →
    emit the plan doc + review config JSON.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="plan-ingestion",
            name="Plan Ingestion Workflow",
            description=(
                "Parse a generic implementation plan, assess its complexity, "
                "transform it into PrimeContractor task YAML or ArtisanContractor "
                "plan markdown, refine via architectural review rounds, and emit "
                "a review-config.json."
            ),
            version="1.0.0",
            capabilities=[
                "plan-transformation",
                "complexity-assessment",
                "document-generation",
            ],
            tags=["plan", "ingestion", "prime", "artisan"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="plan_path",
                    type="file",
                    required=True,
                    description="Path to the input plan markdown file",
                ),
                WorkflowInput(
                    name="output_dir",
                    type="string",
                    required=False,
                    default=".",
                    description="Directory to write output files",
                ),
                WorkflowInput(
                    name="assessor_agent",
                    type="agent_spec",
                    required=False,
                    description="Agent spec for parse + assess phases (default: balanced tier)",
                ),
                WorkflowInput(
                    name="transformer_agent",
                    type="agent_spec",
                    required=False,
                    description="Agent spec for transformation phase (default: balanced tier)",
                ),
                WorkflowInput(
                    name="review_rounds",
                    type="number",
                    required=False,
                    default=2,
                    description="Number of architectural review rounds (0 = skip refinement)",
                ),
                WorkflowInput(
                    name="skip_arc_review",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Skip the architectural review workflow in the REFINE phase",
                ),
                WorkflowInput(
                    name="review_quality_tier",
                    type="string",
                    required=False,
                    default="flagship",
                    description="Quality tier for review agents",
                ),
                WorkflowInput(
                    name="complexity_threshold",
                    type="number",
                    required=False,
                    default=40,
                    description="Complexity score threshold: ≤ threshold → Prime, > threshold → Artisan",
                ),
                WorkflowInput(
                    name="force_route",
                    type="string",
                    required=False,
                    description="Force routing to 'prime' or 'artisan' (bypasses assessment)",
                ),
                WorkflowInput(
                    name="context_files",
                    type="text",
                    required=False,
                    description="Comma-separated file paths for review context",
                ),
                WorkflowInput(
                    name="contextcore_export_dir",
                    type="string",
                    required=False,
                    description="Directory containing ContextCore export artifacts (onboarding-metadata.json, manifest, CRD)",
                ),
                WorkflowInput(
                    name="requirements_path",
                    type="file",
                    required=False,
                    description="Path to the primary requirements document used for traceability checks",
                ),
                WorkflowInput(
                    name="requirements_files",
                    type="text",
                    required=False,
                    description="Comma-separated requirements file paths for dual-document refine and coverage analysis",
                ),
                WorkflowInput(
                    name="min_export_coverage",
                    type="number",
                    required=False,
                    default=0,
                    description="Minimum export coverage percent required in preflight (0-100)",
                ),
                WorkflowInput(
                    name="low_quality_policy",
                    type="string",
                    required=False,
                    default="bias_artisan",
                    description="Action when translation quality is low: bias_artisan or fail",
                ),
                WorkflowInput(
                    name="min_requirements_coverage",
                    type="number",
                    required=False,
                    default=70,
                    description="Minimum requirement mapping coverage percent before low-quality policy applies",
                ),
                WorkflowInput(
                    name="min_artifact_mapping_coverage",
                    type="number",
                    required=False,
                    default=70,
                    description="Minimum artifact mapping completeness percent before low-quality policy applies",
                ),
                WorkflowInput(
                    name="max_contract_conflicts",
                    type="number",
                    required=False,
                    default=2,
                    description="Maximum allowed unresolved mapping conflicts before low-quality policy applies",
                ),
                WorkflowInput(
                    name="scope",
                    type="string",
                    required=False,
                    description="Review scope statement",
                ),
                WorkflowInput(
                    name="warn_cost_usd",
                    type="number",
                    required=False,
                    description="Cost warning threshold in USD",
                ),
                WorkflowInput(
                    name="max_cost_usd",
                    type="number",
                    required=False,
                    description="Cost hard limit in USD — workflow fails if exceeded",
                ),
                WorkflowInput(
                    name="project_root",
                    type="string",
                    required=False,
                    description="Target project root directory (used for .contextcore.yaml auto-discovery)",
                ),
                WorkflowInput(
                    name="contextcore_yaml",
                    type="file",
                    required=False,
                    description="Explicit path to .contextcore.yaml (overrides auto-discovery)",
                ),
                WorkflowInput(
                    name="llm_read_timeout_seconds",
                    type="number",
                    required=False,
                    default=300,
                    description="LLM HTTP read timeout in seconds",
                ),
                WorkflowInput(
                    name="llm_max_attempts",
                    type="number",
                    required=False,
                    default=1,
                    description="Maximum LLM call attempts (including initial request)",
                ),
                WorkflowInput(
                    name="enable_heuristic_parse_fallback",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Fallback to deterministic parse/assess/transform when LLM output is invalid",
                ),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        plan_path = config.get("plan_path")
        if plan_path:
            p = Path(str(plan_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"plan_path does not exist or is not a file: {p}")

        force_route = config.get("force_route")
        if force_route and force_route not in ("prime", "artisan"):
            errors.append(f"force_route must be 'prime' or 'artisan', got '{force_route}'")

        low_quality_policy = str(
            config.get("low_quality_policy", "bias_artisan")
        ).strip().lower()
        if low_quality_policy not in {"bias_artisan", "fail"}:
            errors.append(
                "low_quality_policy must be 'bias_artisan' or 'fail'"
            )

        for key in (
            "min_export_coverage",
            "min_requirements_coverage",
            "min_artifact_mapping_coverage",
        ):
            val = config.get(key)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                errors.append(f"{key} must be a number between 0 and 100")
                continue
            if fval < 0 or fval > 100:
                errors.append(f"{key} must be between 0 and 100")

        for path_key in ("requirements_path", "contextcore_export_dir"):
            raw = config.get(path_key)
            if not raw:
                continue
            p = Path(str(raw)).expanduser()
            if path_key == "requirements_path" and (not p.exists() or not p.is_file()):
                errors.append(f"{path_key} does not exist or is not a file: {p}")
            if path_key == "contextcore_export_dir" and (not p.exists() or not p.is_dir()):
                errors.append(f"{path_key} does not exist or is not a directory: {p}")

        timeout_raw = config.get("llm_read_timeout_seconds")
        if timeout_raw is not None:
            try:
                timeout_val = float(timeout_raw)
            except (TypeError, ValueError):
                errors.append("llm_read_timeout_seconds must be a positive number")
            else:
                if timeout_val <= 0:
                    errors.append("llm_read_timeout_seconds must be > 0")

        attempts_raw = config.get("llm_max_attempts")
        if attempts_raw is not None:
            try:
                attempts_val = int(float(attempts_raw))
            except (TypeError, ValueError):
                errors.append("llm_max_attempts must be an integer >= 1")
            else:
                if attempts_val < 1:
                    errors.append("llm_max_attempts must be >= 1")

        return errors

    # ------------------------------------------------------------------
    # Agent resolution
    # ------------------------------------------------------------------

    def _resolve_assessor_agent(
        self,
        config: Dict[str, Any],
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> BaseAgent:
        spec = config.get("assessor_agent") or Models.CLAUDE_SONNET_LATEST
        return resolve_agent_spec(
            str(spec),
            name="plan-assessor",
            timeout_config=timeout_config,
            retry_config=retry_config,
        )

    def _resolve_transformer_agent(
        self,
        config: Dict[str, Any],
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> BaseAgent:
        spec = config.get("transformer_agent") or Models.CLAUDE_SONNET_LATEST
        agent = resolve_agent_spec(
            str(spec),
            name="plan-transformer",
            timeout_config=timeout_config,
            retry_config=retry_config,
        )
        # Transform phase generates large YAML/markdown; bump token limit
        if hasattr(agent, "max_tokens") and agent.max_tokens < 64000:
            try:
                agent.max_tokens = 64000
            except (AttributeError, TypeError, ValueError) as exc:
                logger.debug(
                    "Could not set max_tokens on %s: %s",
                    type(agent).__name__, exc,
                )
        return agent

    # ------------------------------------------------------------------
    # Phase: PARSE
    # ------------------------------------------------------------------

    def _phase_parse(
        self, plan_text: str, agent: BaseAgent
    ) -> Tuple[Optional[ParsedPlan], StepResult]:
        t0 = time.time()
        prompt = _PARSE_PROMPT.format(plan_text=plan_text)

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.parse")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="parse",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Parse LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        try:
            data = _extract_json_from_response(response_text)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, StepResult(
                step_name="parse",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output=response_text[:_OUTPUT_TRUNCATION],
                time_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost=cost,
                error=f"Failed to parse JSON from LLM response: {exc}",
            )

        features = []
        for f in data.get("features", []):
            features.append(ParsedFeature(
                feature_id=f.get("feature_id", ""),
                name=f.get("name", ""),
                description=f.get("description", ""),
                target_files=f.get("target_files", []),
                dependencies=f.get("dependencies", []),
                estimated_loc=f.get("estimated_loc", 0),
                labels=f.get("labels", []),
                design_doc_sections=f.get("design_doc_sections", []),
                artifact_types_addressed=f.get("artifact_types_addressed", []),
                api_signatures=f.get("api_signatures", []),
                protocol=f.get("protocol", ""),
                runtime_dependencies=f.get("runtime_dependencies", []),
                negative_scope=f.get("negative_scope", []),
            ))

        parsed = ParsedPlan(
            title=data.get("title", "Untitled Plan"),
            goals=data.get("goals", []),
            features=features,
            dependency_graph=data.get("dependency_graph", {}),
            mentioned_files=data.get("mentioned_files", []),
            raw_text=plan_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        step = StepResult(
            step_name="parse",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=response_text[:_OUTPUT_TRUNCATION],
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        return parsed, step

    # ------------------------------------------------------------------
    # Phase: ASSESS
    # ------------------------------------------------------------------

    def _phase_assess(
        self,
        parsed_plan: ParsedPlan,
        agent: BaseAgent,
        threshold: int,
        force_route: Optional[str],
    ) -> Tuple[Optional[ComplexityScore], StepResult]:
        t0 = time.time()

        # Build feature summary for the ASSESS prompt.
        # Flag multi-file features so the complexity scorer can account
        # for split risk in its cross_file_deps dimension.
        _feat_lines = []
        multi_file_count = 0
        for f in parsed_plan.features:
            has_init = any(
                tf.endswith("__init__.py") for tf in f.target_files
            )
            suffix = ""
            if len(f.target_files) > 1:
                multi_file_count += 1
                suffix = " ⚠ MULTI-FILE"
                if has_init:
                    suffix += "+__init__.py"
            _feat_lines.append(
                f"  - {f.feature_id}: {f.name} "
                f"(files: {len(f.target_files)}, "
                f"deps: {len(f.dependencies)}){suffix}"
            )
        feature_summary = "\n".join(_feat_lines)
        if multi_file_count:
            feature_summary += (
                f"\n\n  NOTE: {multi_file_count} feature(s) target multiple "
                f"files. Multi-file tasks have higher implementation risk — "
                f"factor this into cross_file_deps scoring."
            )

        prompt = _ASSESS_PROMPT.format(
            title=parsed_plan.title,
            goals=", ".join(parsed_plan.goals),
            feature_count=len(parsed_plan.features),
            feature_summary=feature_summary,
            file_count=len(parsed_plan.mentioned_files),
            threshold=threshold,
        )

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.assess")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="assess",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Assess LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        try:
            data = _extract_json_from_response(response_text)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, StepResult(
                step_name="assess",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output=response_text[:_OUTPUT_TRUNCATION],
                time_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost=cost,
                error=f"Failed to parse assessment JSON: {exc}",
            )

        # Determine route from composite score (don't trust LLM's route suggestion)
        composite = _safe_int(data.get("composite"), 50)
        if force_route:
            route = ContractorRoute(force_route)
        else:
            route = ContractorRoute.PRIME if composite <= threshold else ContractorRoute.ARTISAN
            llm_route = data.get("route", "").lower()
            if llm_route and llm_route != route.value:
                logger.debug(
                    "LLM suggested route '%s' but composite %d with threshold %d → '%s'",
                    llm_route, composite, threshold, route.value,
                )

        score = ComplexityScore(
            feature_count=_safe_int(data.get("feature_count"), 0),
            cross_file_deps=_safe_int(data.get("cross_file_deps"), 0),
            api_surface=_safe_int(data.get("api_surface"), 0),
            test_complexity=_safe_int(data.get("test_complexity"), 0),
            integration_depth=_safe_int(data.get("integration_depth"), 0),
            domain_novelty=_safe_int(data.get("domain_novelty"), 0),
            ambiguity=_safe_int(data.get("ambiguity"), 0),
            composite=composite,
            reasoning=data.get("reasoning", ""),
            route=route,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        step = StepResult(
            step_name="assess",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=response_text[:_OUTPUT_TRUNCATION],
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        return score, step

    # ------------------------------------------------------------------
    # Phase: TRANSFORM
    # ------------------------------------------------------------------

    def _phase_transform(
        self,
        parsed_plan: ParsedPlan,
        route: ContractorRoute,
        agent: BaseAgent,
        output_dir: Path,
    ) -> Tuple[Optional[Path], StepResult]:
        t0 = time.time()

        features_text = "\n".join(
            f"  - {f.feature_id}: {f.name}\n"
            f"    Description: {f.description}\n"
            f"    Files: {', '.join(f.target_files)}\n"
            f"    Dependencies: {', '.join(f.dependencies)}\n"
            f"    Estimated LOC: {f.estimated_loc}"
            for f in parsed_plan.features
        )

        if route == ContractorRoute.PRIME:
            prompt = _TRANSFORM_PRIME_PROMPT.format(
                title=parsed_plan.title,
                goals=", ".join(parsed_plan.goals),
                features=features_text,
                dependency_graph=json.dumps(parsed_plan.dependency_graph),
            )
            out_filename = "plan-ingestion-tasks.yaml"
        else:
            prompt = _TRANSFORM_ARTISAN_PROMPT.format(
                title=parsed_plan.title,
                goals=", ".join(parsed_plan.goals),
                features=features_text,
                mentioned_files=", ".join(parsed_plan.mentioned_files),
                dependency_graph=json.dumps(parsed_plan.dependency_graph),
            )
            out_filename = "PLAN-ingested.md"

        _llm_ctx = _tracer.start_as_current_span("llm.plan_ingestion.transform")
        _llm_span = _llm_ctx.__enter__()
        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
            if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
                _llm_span.record_exception(exc)
                _llm_span.set_status(_StatusCode.ERROR, str(exc))
            _llm_ctx.__exit__(None, None, None)
            elapsed_ms = int((time.time() - t0) * 1000)
            return None, StepResult(
                step_name="transform",
                agent_name=agent.name,
                input=prompt[:_INPUT_TRUNCATION],
                output="",
                time_ms=elapsed_ms,
                error=f"Transform LLM call failed: {exc}",
            )
        elapsed_ms = int((time.time() - t0) * 1000)

        in_tok = token_usage_input(token_usage) if token_usage else 0
        out_tok = token_usage_output(token_usage) if token_usage else 0
        cost = token_usage_cost(token_usage) if token_usage else 0.0

        if _HAS_OTEL and not isinstance(_llm_span, _NoOpSpan):
            _llm_span.set_attribute("llm.response_time_ms", time_ms)
            _llm_span.set_attribute("llm.tokens_input", in_tok)
            _llm_span.set_attribute("llm.tokens_output", out_tok)
            _llm_span.set_attribute("llm.cost_usd", cost)
        _llm_ctx.__exit__(None, None, None)

        # Extract content from potential code fences
        content = extract_code_from_response(
            response_text,
            language="yaml" if route == ContractorRoute.PRIME else "markdown",
        )

        # Validate output
        _md_quality_warning = None
        if route == ContractorRoute.PRIME:
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as exc:
                return None, StepResult(
                    step_name="transform",
                    agent_name=agent.name,
                    input=prompt[:_INPUT_TRUNCATION],
                    output=content[:_OUTPUT_TRUNCATION],
                    time_ms=elapsed_ms,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost=cost,
                    error=f"Generated YAML is invalid: {exc}",
                )
        else:
            # Markdown: check for at least one heading
            if not re.search(r'^#{1,6}\s', content, re.MULTILINE):
                _md_quality_warning = "Generated markdown has no headings — may be low quality"
                logger.warning(_md_quality_warning)

        # Write output
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / out_filename
        atomic_write(out_path, content)

        _output_msg = f"Wrote {out_path}"
        if _md_quality_warning:
            _output_msg += f" [warning: {_md_quality_warning}]"
        step = StepResult(
            step_name="transform",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=_output_msg,
            time_ms=elapsed_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
        )

        return out_path, step

    # ------------------------------------------------------------------
    # Preflight / quality helpers
    # ------------------------------------------------------------------

    def _preflight_export_contract(
        self,
        contextcore_export_dir: Optional[str],
        context_files: Optional[List[str]],
        output_dir: Path,
        min_export_coverage: float,
        contextcore_yaml_path: Optional[Path] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], List[str], List[str]]:
        """Validate ContextCore export artifacts before PARSE."""
        warnings: List[str] = []
        errors: List[str] = []
        evidence: Dict[str, Any] = {"checksums": {}, "paths": {}, "coverage": {}}

        onboarding_path: Optional[Path] = None
        if contextcore_export_dir:
            export_dir = _resolve_path(contextcore_export_dir, output_dir)
            onboarding_path = export_dir / "onboarding-metadata.json"
            if not onboarding_path.exists():
                errors.append(
                    f"Preflight: missing onboarding-metadata.json in contextcore_export_dir: {export_dir}"
                )
                return None, evidence, warnings, errors
        elif context_files:
            for raw in context_files:
                p = _resolve_path(raw, output_dir)
                if p.name == "onboarding-metadata.json":
                    onboarding_path = p
                    break

        if onboarding_path is None:
            warnings.append(
                "Preflight: onboarding metadata not provided; skipping export contract checks"
            )
            return None, evidence, warnings, errors
        if not onboarding_path.exists():
            errors.append(f"Preflight: onboarding metadata not found: {onboarding_path}")
            return None, evidence, warnings, errors

        onboarding = _safe_json_load(onboarding_path)
        if onboarding is None:
            errors.append(f"Preflight: onboarding metadata is invalid JSON: {onboarding_path}")
            return None, evidence, warnings, errors

        evidence["paths"]["onboarding_metadata"] = str(onboarding_path)
        base_dir = onboarding_path.parent

        amp = onboarding.get("artifact_manifest_path")
        pcp = onboarding.get("project_context_path")
        if not isinstance(amp, str):
            errors.append("Preflight: onboarding missing artifact_manifest_path")
        if not isinstance(pcp, str):
            errors.append("Preflight: onboarding missing project_context_path")
        if errors:
            return onboarding, evidence, warnings, errors

        artifact_manifest_path = _resolve_path(amp, base_dir)
        project_context_path = _resolve_path(pcp, base_dir)
        evidence["paths"]["artifact_manifest"] = str(artifact_manifest_path)
        evidence["paths"]["project_context"] = str(project_context_path)

        if not artifact_manifest_path.exists():
            errors.append(f"Preflight: expected artifact manifest missing: {artifact_manifest_path}")
        if not project_context_path.exists():
            errors.append(f"Preflight: expected project context missing: {project_context_path}")
        if errors:
            return onboarding, evidence, warnings, errors

        # Check checksum integrity when checksums are present.
        expected_manifest_checksum = onboarding.get("artifact_manifest_checksum")
        expected_project_checksum = onboarding.get("project_context_checksum")
        actual_manifest_checksum = _checksum_file(artifact_manifest_path)
        actual_project_checksum = _checksum_file(project_context_path)
        evidence["checksums"]["artifact_manifest_actual"] = actual_manifest_checksum
        evidence["checksums"]["project_context_actual"] = actual_project_checksum

        if isinstance(expected_manifest_checksum, str):
            evidence["checksums"]["artifact_manifest_expected"] = expected_manifest_checksum
            if actual_manifest_checksum != expected_manifest_checksum:
                errors.append(
                    "Preflight: artifact_manifest_checksum mismatch between onboarding and artifact manifest"
                )
        if isinstance(expected_project_checksum, str):
            evidence["checksums"]["project_context_expected"] = expected_project_checksum
            if actual_project_checksum != expected_project_checksum:
                errors.append(
                    "Preflight: project_context_checksum mismatch between onboarding and project context"
                )

        # Parameter source resolvability summary guardrail.
        has_resolvability_summary = (
            isinstance(onboarding.get("resolved_artifact_parameters"), dict)
            or isinstance(onboarding.get("parameter_resolvability"), dict)
        )
        if not has_resolvability_summary:
            errors.append(
                "Preflight: onboarding lacks parameter resolvability summary "
                "(expected resolved_artifact_parameters or parameter_resolvability)"
            )

        coverage = onboarding.get("coverage")
        if not isinstance(coverage, dict):
            errors.append("Preflight: onboarding missing coverage block")
            return onboarding, evidence, warnings, errors
        evidence["coverage"] = coverage

        gaps = coverage.get("gaps")
        if not isinstance(gaps, list):
            errors.append("Preflight: coverage.gaps must be present as a list")

        overall = coverage.get("overallCoverage", coverage.get("overall_coverage"))
        try:
            overall_pct = float(overall) if overall is not None else 0.0
        except (TypeError, ValueError):
            overall_pct = 0.0
        evidence["coverage"]["overall_coverage_evaluated"] = overall_pct

        if overall_pct < min_export_coverage:
            errors.append(
                f"Preflight: export coverage {overall_pct:.1f}% below minimum {min_export_coverage:.1f}%"
            )

        # source_checksum verification against .contextcore.yaml
        expected_source_checksum = onboarding.get("source_checksum")
        if not isinstance(expected_source_checksum, str):
            warnings.append("Preflight: source_checksum missing in onboarding metadata")
            evidence["checksums"]["source_checksum_verified"] = None
        elif contextcore_yaml_path is None:
            warnings.append(
                "Preflight: .contextcore.yaml not available for verification"
            )
            evidence["checksums"]["source_checksum_verified"] = None
        elif not contextcore_yaml_path.exists():
            warnings.append(
                "Preflight: .contextcore.yaml not available for verification"
            )
            evidence["checksums"]["source_checksum_verified"] = None
        else:
            actual_checksum = _checksum_file(contextcore_yaml_path)
            evidence["checksums"]["source_checksum_expected"] = expected_source_checksum
            evidence["checksums"]["source_checksum_actual"] = actual_checksum
            evidence["paths"]["contextcore_yaml"] = str(contextcore_yaml_path)
            if actual_checksum == expected_source_checksum:
                evidence["checksums"]["source_checksum_verified"] = True
            else:
                evidence["checksums"]["source_checksum_verified"] = False
                errors.append(
                    f"Preflight: source_checksum mismatch "
                    f"(expected={expected_source_checksum}, actual={actual_checksum})"
                )

        return onboarding, evidence, warnings, errors

    @staticmethod
    def _evaluate_translation_quality(
        parsed_plan: ParsedPlan,
        requirements_docs: Dict[str, str],
        onboarding: Optional[Dict[str, Any]],
        requirements_hints: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Compute translation-quality metrics used for routing safeguards."""
        requirement_hints = requirements_hints or {}
        requirement_ids = sorted(requirement_hints.keys())
        if not requirement_ids:
            requirements_corpus = "\n\n".join(requirements_docs.values())
            requirement_ids = _extract_requirement_ids(requirements_corpus)

        # ── Classify pipeline-innate vs project-specific requirements ──
        pipeline_innate_ids: List[str] = []
        project_specific_ids: List[str] = []
        for rid in requirement_ids:
            hint = requirement_hints.get(rid, {})
            labels = hint.get("labels", [])
            if isinstance(labels, list) and "pipeline-innate" in labels:
                pipeline_innate_ids.append(rid)
            else:
                project_specific_ids.append(rid)

        req_to_feature: Dict[str, List[str]] = {}

        # Auto-satisfy pipeline-innate requirements with synthetic mapping
        for rid in pipeline_innate_ids:
            hint = requirement_hints.get(rid, {})
            artifact_type = hint.get("satisfied_by_artifact", "artifact")
            req_to_feature[rid] = [f"__pipeline_artifact:{artifact_type}"]

        # Match project-specific requirements against plan text
        for rid in project_specific_ids:
            rid_pattern = re.compile(r'\b' + re.escape(rid) + r'\b', re.IGNORECASE)
            matched_features = [
                f.feature_id for f in parsed_plan.features
                if rid_pattern.search(f"{f.feature_id} {f.name} {f.description}")
            ]
            req_to_feature[rid] = matched_features

        req_acceptance: Dict[str, List[str]] = {}
        req_sources: Dict[str, List[str]] = {}
        for rid in requirement_ids:
            hint = requirement_hints.get(rid, {})
            anchors = hint.get("acceptance_anchors", [])
            if isinstance(anchors, list):
                req_acceptance[rid] = [a for a in anchors if isinstance(a, str)]
            else:
                req_acceptance[rid] = []
            src_refs = hint.get("source_references", [])
            if isinstance(src_refs, list):
                req_sources[rid] = [s for s in src_refs if isinstance(s, str)]
            else:
                req_sources[rid] = []

        # Coverage computed from project-specific requirements only
        mapped_project_specific = sum(
            1 for rid in project_specific_ids if req_to_feature.get(rid)
        )
        total_project_specific = len(project_specific_ids)
        requirements_coverage = (
            (mapped_project_specific / total_project_specific) * 100.0
            if total_project_specific
            else 100.0
        )

        coverage = onboarding.get("coverage", {}) if isinstance(onboarding, dict) else {}
        gaps = coverage.get("gaps", []) if isinstance(coverage, dict) else []
        # Filter to entries that look like artifact IDs (not plain-text gap descriptions).
        # Artifact IDs contain hyphens/underscores and no spaces; prose descriptions have spaces
        # or are single bare words without structural separators.
        artifact_ids = [
            a for a in gaps
            if isinstance(a, str) and a.strip() and " " not in a.strip()
            and ("-" in a or "_" in a)
            and re.match(r'^[a-zA-Z][\w-]{2,}$', a.strip())
        ]
        artifact_to_feature: Dict[str, List[str]] = {}

        for aid in artifact_ids:
            expected_type = _artifact_type_from_id(aid)
            matched: List[str] = []
            for feat in parsed_plan.features:
                feat_types = {_normalize_artifact_type(t) for t in feat.artifact_types_addressed}
                if expected_type and expected_type in feat_types:
                    matched.append(feat.feature_id)
                elif aid.lower() in f"{feat.feature_id} {feat.name} {feat.description}".lower():
                    matched.append(feat.feature_id)
            artifact_to_feature[aid] = sorted(set(matched))

        mapped_artifacts = sum(1 for fids in artifact_to_feature.values() if fids)
        total_artifacts = len(artifact_ids)
        artifact_completeness = (
            (mapped_artifacts / total_artifacts) * 100.0
            if total_artifacts
            else 100.0
        )

        # Only project-specific requirements count toward unmet/conflict
        unmet_requirements = [
            rid for rid in project_specific_ids
            if not req_to_feature.get(rid)
        ]
        unmet_artifacts = [aid for aid, fids in artifact_to_feature.items() if not fids]
        conflict_count = len(unmet_requirements) + len(unmet_artifacts)

        return {
            "requirements_total": len(requirement_ids),
            "requirements_mapped": mapped_project_specific + len(pipeline_innate_ids),
            "requirements_project_specific_total": total_project_specific,
            "requirements_pipeline_innate_total": len(pipeline_innate_ids),
            "requirements_coverage_percent": round(requirements_coverage, 2),
            "artifact_total": total_artifacts,
            "artifact_mapped": mapped_artifacts,
            "artifact_mapping_percent": round(artifact_completeness, 2),
            "conflict_count": conflict_count,
            "unmet_requirement_count": len(unmet_requirements),
            "unmet_artifact_count": len(unmet_artifacts),
            "unmapped_requirements": unmet_requirements,
            "unmapped_artifacts": unmet_artifacts,
            "requirement_to_feature": req_to_feature,
            "artifact_to_feature": artifact_to_feature,
            "requirement_acceptance_anchors": req_acceptance,
            "requirement_source_references": req_sources,
        }

    @staticmethod
    def _build_traceability_artifact(
        route: ContractorRoute,
        parsed_plan: ParsedPlan,
        tasks: List[Dict[str, Any]],
        quality: Dict[str, Any],
        checksum_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build deterministic traceability artifact payload."""
        feature_to_task: Dict[str, List[str]] = {}
        for t in tasks:
            ctx = t.get("config", {}).get("context", {})
            fid = ctx.get("feature_id")
            if not isinstance(fid, str) or not fid:
                continue
            feature_to_task.setdefault(fid, []).append(t.get("task_id", ""))

        req_mappings: List[Dict[str, Any]] = []
        for rid, fids in quality.get("requirement_to_feature", {}).items():
            # Detect pipeline-innate entries by __pipeline_artifact: prefix
            is_auto = any(
                isinstance(f, str) and f.startswith("__pipeline_artifact:")
                for f in fids
            )
            if is_auto:
                req_mappings.append(
                    {
                        "requirement_id": rid,
                        "feature_ids": fids,
                        "task_ids": [],
                        "status": "auto-satisfied",
                        "acceptance_obligations": quality.get(
                            "requirement_acceptance_anchors", {}
                        ).get(rid, []),
                        "source_references": quality.get(
                            "requirement_source_references", {}
                        ).get(rid, []),
                        "mapping_rationale": [
                            "pipeline-innate: satisfied by artifact generation"
                        ],
                    }
                )
            else:
                task_ids: List[str] = []
                for fid in fids:
                    task_ids.extend(feature_to_task.get(fid, []))
                req_mappings.append(
                    {
                        "requirement_id": rid,
                        "feature_ids": fids,
                        "task_ids": sorted(set(tid for tid in task_ids if tid)),
                        "status": "mapped" if fids else "unresolved",
                        "acceptance_obligations": quality.get(
                            "requirement_acceptance_anchors", {}
                        ).get(rid, []),
                        "source_references": quality.get(
                            "requirement_source_references", {}
                        ).get(rid, []),
                        "mapping_rationale": (
                            ["matched by requirement hint id against parsed feature text"]
                            if fids
                            else ["no parsed feature contained requirement identifier"]
                        ),
                    }
                )

        artifact_mappings: List[Dict[str, Any]] = []
        for aid, fids in quality.get("artifact_to_feature", {}).items():
            task_ids: List[str] = []
            for fid in fids:
                task_ids.extend(feature_to_task.get(fid, []))
            artifact_mappings.append(
                {
                    "artifact_id": aid,
                    "artifact_type": _artifact_type_from_id(aid),
                    "feature_ids": fids,
                    "task_ids": sorted(set(tid for tid in task_ids if tid)),
                    "status": "mapped" if fids else "unresolved",
                }
            )

        unresolved: List[Dict[str, Any]] = []
        for rid in quality.get("unmapped_requirements", []):
            unresolved.append(
                {
                    "type": "requirement",
                    "id": rid,
                    "severity": "high",
                    "message": "No plan feature/task mapping found",
                }
            )
        for aid in quality.get("unmapped_artifacts", []):
            unresolved.append(
                {
                    "type": "artifact",
                    "id": aid,
                    "severity": "medium",
                    "message": "No plan feature/task mapping found",
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "route": route.value,
            "plan_title": parsed_plan.title,
            "requirement_mappings": req_mappings,
            "artifact_mappings": artifact_mappings,
            "unresolved": unresolved,
            "translation_quality": {
                "requirements_coverage_percent": quality.get("requirements_coverage_percent", 100.0),
                "artifact_mapping_percent": quality.get("artifact_mapping_percent", 100.0),
                "conflict_count": quality.get("conflict_count", 0),
            },
            "checksum_evidence": checksum_evidence,
        }

    @staticmethod
    def _write_traceability_artifact(output_dir: Path, payload: Dict[str, Any]) -> Path:
        """Write ingestion-traceability.json and return the path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "ingestion-traceability.json"
        atomic_write_json(path, payload, indent=2)
        return path

    @staticmethod
    def _write_preflight_report(
        output_dir: Path,
        *,
        passed: bool,
        evidence: Dict[str, Any],
        warnings: List[str],
        errors: List[str],
    ) -> Path:
        """Write preflight-report.json and return the path."""
        from datetime import datetime, timezone

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "preflight-report.json"
        payload = {
            "passed": passed,
            "source_checksum_verified": evidence.get("checksums", {}).get(
                "source_checksum_verified"
            ),
            "evidence": evidence,
            "warnings": warnings,
            "errors": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(path, payload, indent=2)
        return path

    # ------------------------------------------------------------------
    # Phase: REFINE
    # ------------------------------------------------------------------

    def _phase_refine(
        self,
        doc_path: Path,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
        feature_requirements: Optional[List[str]],
        warn_cost_usd: Optional[float],
        max_cost_usd: Optional[float],
        enable_apply: Optional[bool] = None,
        enable_prompt_caching: Optional[bool] = None,
        enable_triage: Optional[bool] = None,
    ) -> Tuple[int, List[StepResult], float, Dict[str, Any]]:
        if review_rounds <= 0:
            return 0, [], 0.0, {}

        # Local import to avoid circular dependencies
        from .architectural_review_log_workflow import ArchitecturalReviewLogWorkflow

        review_wf = ArchitecturalReviewLogWorkflow()
        review_config: Dict[str, Any] = {
            "document_path": str(doc_path),
            "quality_tier": review_quality_tier,
            # Arc-review maps 1 agent = 1 round; reviewer_count controls round count.
            # Cap at 5 (arc-review's validated max).
            "reviewer_count": min(review_rounds, 5),
            "max_suggestions": 10,
            "init_if_missing": True,
        }
        if scope:
            review_config["scope"] = scope
        if context_files:
            review_config["context_files"] = context_files
        if feature_requirements:
            review_config["feature_requirements"] = feature_requirements
        if warn_cost_usd is not None:
            review_config["warn_cost_usd"] = warn_cost_usd
        if max_cost_usd is not None:
            review_config["max_cost_usd"] = max_cost_usd
        if enable_apply is not None:
            review_config["enable_apply"] = enable_apply
        if enable_prompt_caching is not None:
            review_config["enable_prompt_caching"] = enable_prompt_caching
        if enable_triage is not None:
            review_config["enable_triage"] = enable_triage

        with _tracer.start_as_current_span("ingestion.refine.review") as _review_span:
            result = review_wf.run(review_config)

        review_cost = result.metrics.total_cost if result.metrics else 0.0
        rounds_completed = (
            result.output.get("rounds_completed", len(result.steps))
            if isinstance(result.output, dict) else len(result.steps)
        )

        refine_steps = []
        for s in result.steps:
            refine_steps.append(StepResult(
                step_name=f"refine:{s.step_name}",
                agent_name=s.agent_name,
                input=s.input,
                output=s.output,
                time_ms=s.time_ms,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                cost=s.cost,
                error=s.error,
            ))

        if not result.success and result.error:
            refine_steps.append(StepResult(
                step_name="refine:error",
                error=result.error,
            ))

        review_output = result.output or {}
        return rounds_completed, refine_steps, review_cost, review_output

    # ------------------------------------------------------------------
    # Artisan context seed helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_refine_suggestions_for_seed(
        review_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract accepted triage suggestions for seed injection."""
        triage = review_output.get("triage")
        if not triage or not isinstance(triage, dict):
            return []

        decisions = triage.get("decisions", [])
        if not decisions:
            # Fallback: return aggregate summary when decisions not available
            accepted = _safe_int(triage.get("accepted"), 0)
            if accepted == 0:
                return []
            return [{
                "decision": "ACCEPT",
                "source": "triage_summary",
                "triage_accepted_count": accepted,
                "triage_rejected_count": triage.get("rejected", 0),
                "substantially_addressed_areas": triage.get(
                    "substantially_addressed_areas", [],
                ),
                "areas_needing_review": triage.get("areas_needing_review", []),
            }]

        # Return individual ACCEPT decisions with full detail
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

    @staticmethod
    def _estimate_story_points(estimated_loc: int) -> int:
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

    @staticmethod
    def _is_trivial_test_init(file_path: str) -> bool:
        """Return True if *file_path* is a ``__init__.py`` inside a test directory.

        Python 3 + pytest do not require ``tests/__init__.py`` (or
        ``tests/unit/__init__.py``, etc.).  These files are wasted
        implementation slots when generated by the pipeline.
        """
        if not file_path.endswith("__init__.py"):
            return False
        parts = file_path.replace("\\", "/").split("/")
        return any(p in ("tests", "test") for p in parts[:-1])

    @staticmethod
    def _derive_tasks_from_features(
        features: List[ParsedFeature],
        dependency_graph: Dict[str, List[str]],
        requirement_to_feature: Optional[Dict[str, List[str]]] = None,
        artifact_to_feature: Optional[Dict[str, List[str]]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        output_path_conventions: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert ParsedFeatures into task dicts matching prime-route schema.

        Args:
            features: Parsed features from the PARSE phase.
            dependency_graph: Feature dependency graph.
        """
        # Build a mapping from feature_id to task_id
        fid_to_tid: Dict[str, str] = {}
        for idx, feat in enumerate(features, start=1):
            fid_to_tid[feat.feature_id] = f"PI-{idx:03d}"

        feature_to_requirements: Dict[str, List[str]] = {}
        for rid, fids in (requirement_to_feature or {}).items():
            if not isinstance(rid, str):
                continue
            if not isinstance(fids, list):
                continue
            for fid in fids:
                if not isinstance(fid, str):
                    continue
                feature_to_requirements.setdefault(fid, []).append(rid)
        for fid in feature_to_requirements:
            feature_to_requirements[fid] = sorted(set(feature_to_requirements[fid]))

        feature_to_artifacts: Dict[str, List[str]] = {}
        for aid, fids in (artifact_to_feature or {}).items():
            if not isinstance(aid, str):
                continue
            if not isinstance(fids, list):
                continue
            for fid in fids:
                if not isinstance(fid, str):
                    continue
                feature_to_artifacts.setdefault(fid, []).append(aid)
        for fid in feature_to_artifacts:
            feature_to_artifacts[fid] = sorted(set(feature_to_artifacts[fid]))

        tasks: List[Dict[str, Any]] = []
        for idx, feat in enumerate(features, start=1):
            tid = fid_to_tid[feat.feature_id]
            sp = PlanIngestionWorkflow._estimate_story_points(feat.estimated_loc)

            # Resolve dependency feature IDs → task IDs
            deps = []
            for dep_fid in feat.dependencies:
                dep_tid = fid_to_tid.get(dep_fid)
                if dep_tid:
                    deps.append(dep_tid)

            # Also include edges from the dependency graph
            for dep_fid in dependency_graph.get(feat.feature_id, []):
                dep_tid = fid_to_tid.get(dep_fid)
                if dep_tid and dep_tid not in deps:
                    deps.append(dep_tid)

            # Priority: features with more dependents are higher priority
            # (they block more downstream work).
            dependent_count = sum(
                1 for f in features
                if feat.feature_id in dependency_graph.get(f.feature_id, [])
                or feat.feature_id in f.dependencies
            )
            if dependent_count >= 2:
                priority = "high"
            elif dependent_count == 1:
                priority = "medium"
            else:
                priority = "low"

            # ── Normalize target_files ordering ────────────────────────
            # __init__.py first: it's the package root that other files
            # import from.  Consistent ordering improves LLM output format
            # compliance and matches the MULTI_FILE_OUTPUT_FORMAT contract
            # in lead_contractor_workflow.py.
            mapped_artifacts = feature_to_artifacts.get(feat.feature_id, [])
            resolved_target_files = list(feat.target_files)
            if (
                not resolved_target_files
                and mapped_artifacts
                and isinstance(output_path_conventions, dict)
            ):
                resolved_target_files = _derive_target_files_from_artifact_ids(
                    mapped_artifacts,
                    output_path_conventions,
                )

            # ── Strip trivial test __init__.py files ──────────────────
            # Python 3 + pytest don't require them; they are wasted slots.
            pre_filter_count = len(resolved_target_files)
            resolved_target_files = [
                f for f in resolved_target_files
                if not PlanIngestionWorkflow._is_trivial_test_init(f)
            ]
            if not resolved_target_files and pre_filter_count > 0:
                logger.info(
                    "Skipping feature %s (%s): all target files are trivial "
                    "test __init__.py",
                    feat.feature_id,
                    feat.name,
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
                # Mottainai Phase 2.2: infer artifact types from target file
                # patterns so downstream injections keyed on artifact_types
                # have something to match against.
                inferred = _infer_artifact_types_from_files(ordered_files)
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

            # REQ-PD-003: Build requirements_text from description +
            # acceptance_obligations + source_references so DESIGN has
            # authoritative parameter details without re-deriving.
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
            # Avoid duplicating task_description when no additional
            # acceptance/source context was appended.
            if _requirements_text == feat.description:
                _requirements_text = ""
            elif len(_requirements_text) > 2000:
                _requirements_text = _requirements_text[:2000] + " [truncated]"

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

        # ── Clean up dangling dependency references from skipped features ──
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

        # ── Gate 2a: single-file enforcement ─────────────────────────
        # Per defense-in-depth Principle 2 (adversarial thinking): even if
        # the PARSE prompt says "one file per feature," the LLM may ignore
        # it.  Structurally split any multi-file tasks so downstream
        # phases always receive single-file work items.
        tasks = PlanIngestionWorkflow._split_oversized_tasks(
            tasks, max_files=1,
        )

        # ── Validate task IDs against safe pattern ──────────────────
        for t in tasks:
            tid = t.get("task_id", "")
            if not _SAFE_TASK_ID_PATTERN.match(tid):
                logger.warning(
                    "Task ID %r does not match safe pattern — may cause "
                    "checkpoint path issues downstream",
                    tid,
                )

        # ── Gate 2b: filter trivial test __init__.py after split ─────
        # A multi-file feature like ["tests/__init__.py", "tests/test_auth.py"]
        # becomes two sub-tasks after Gate 2a.  Filter the __init__.py one.
        tasks = PlanIngestionWorkflow._filter_trivial_test_init_tasks(tasks)

        if not tasks and features:
            logger.warning(
                "Zero tasks derived from %d features — all features may have been "
                "filtered (trivial __init__.py, empty target_files). "
                "Downstream seed will contain no work items.",
                len(features),
            )

        return tasks

    @staticmethod
    def _split_oversized_tasks(
        tasks: List[Dict[str, Any]],
        max_files: int = 1,
    ) -> List[Dict[str, Any]]:
        """Gate 2a: Split tasks with more than *max_files* target files.

        Default is ``max_files=1`` (single-file enforcement).  The PARSE
        prompt instructs the LLM to emit one file per feature, but this
        gate structurally enforces it (defense-in-depth Principle 2:
        treat upstream as potentially adversarial).

        Each multi-file task is replaced by single-file sub-tasks:
        - ``__init__.py`` (if present) becomes the first sub-task so
          other sub-tasks can depend on it.
        - Sub-tasks are lettered (PI-001a, PI-001b, …) for traceability.
        - Estimated LOC is divided proportionally.

        Single-file tasks (≤ *max_files*) pass through unchanged.
        """
        result: List[Dict[str, Any]] = []

        for task in tasks:
            ctx = task.get("config", {}).get("context", {})
            target_files = ctx.get("target_files", [])

            if len(target_files) <= max_files:
                result.append(task)
                continue

            # This task needs splitting.
            parent_id = task["task_id"]
            parent_deps = list(task.get("depends_on", []))
            parent_desc = task.get("config", {}).get("task_description", "")
            estimated_loc = ctx.get("estimated_loc", 0)
            loc_per_file = max(estimated_loc // len(target_files), 10)

            # Cap sub-tasks at 26 (a-z) to stay within
            # _SAFE_TASK_ID_PATTERN.  Extra files are grouped into the
            # last sub-task.
            _MAX_SUB_TASKS = 26

            # Separate __init__.py (if any) — it becomes sub-task 'a'
            # so other sub-tasks can depend on it.
            init_files = [f for f in target_files if f.endswith("__init__.py")]
            non_init_files = [f for f in target_files if not f.endswith("__init__.py")]
            ordered = init_files + non_init_files

            if len(ordered) > _MAX_SUB_TASKS:
                logger.warning(
                    "Gate 2a: task %s has %d files — capping at %d "
                    "sub-tasks; last sub-task will contain %d files",
                    parent_id,
                    len(ordered),
                    _MAX_SUB_TASKS,
                    len(ordered) - _MAX_SUB_TASKS + 1,
                )

            # Build groups: first _MAX_SUB_TASKS groups each get one file;
            # additional files accumulate in the last group.
            groups: List[List[str]] = []
            for f in ordered:
                if len(groups) < _MAX_SUB_TASKS:
                    groups.append([f])
                else:
                    groups[-1].append(f)

            num_sub = len(groups)

            logger.info(
                "Gate 2a: splitting task %s (%d files > max %d) into %d "
                "sub-tasks",
                parent_id,
                len(target_files),
                max_files,
                num_sub,
            )

            # Pre-compute init sub-task ID for dependency wiring
            # (before the loop so it is available on the first
            # non-init iteration).
            init_sub_id: Optional[str] = None
            for pre_idx, pre_group in enumerate(groups):
                if any(gf.endswith("__init__.py") for gf in pre_group):
                    pre_suffix = chr(ord("a") + pre_idx)
                    init_sub_id = f"{parent_id}{pre_suffix}"
                    break

            for idx, file_group in enumerate(groups):
                suffix = chr(ord("a") + idx)
                sub_id = f"{parent_id}{suffix}"

                # Sub-task deps: parent's deps + init sub-task (if this
                # isn't the init sub-task itself).
                sub_deps = list(parent_deps)
                if init_sub_id and sub_id != init_sub_id:
                    sub_deps.append(init_sub_id)

                group_loc = loc_per_file * len(file_group)

                sub_ctx: Dict[str, Any] = {
                    "feature_id": ctx.get("feature_id", ""),
                    "target_files": file_group,
                    "estimated_loc": group_loc,
                    "_split_from": parent_id,
                    "_split_index": idx,
                }
                # Carry forward optional context fields
                for key in (
                    "design_doc_sections",
                    "artifact_types_addressed",
                    "requirement_ids",
                    "acceptance_obligations",
                    "source_references",
                    "mapping_rationale",
                ):
                    if key in ctx:
                        sub_ctx[key] = ctx[key]

                if len(file_group) == 1:
                    file_name = file_group[0].rsplit("/", 1)[-1]
                    sub_title = f"{task['title']} — {file_name}"
                    desc_detail = f"implement `{file_group[0]}` only."
                else:
                    sub_title = (
                        f"{task['title']} — {len(file_group)} files "
                        f"(group {suffix})"
                    )
                    file_list = ", ".join(
                        f"`{gf}`" for gf in file_group
                    )
                    desc_detail = (
                        f"implement {len(file_group)} files: "
                        f"{file_list}."
                    )

                result.append({
                    "task_id": sub_id,
                    "title": sub_title,
                    "task_type": task.get("task_type", "task"),
                    "story_points": PlanIngestionWorkflow._estimate_story_points(
                        group_loc
                    ),
                    "priority": task.get("priority", "medium"),
                    "labels": list(task.get("labels", [])),
                    "depends_on": sub_deps,
                    "config": {
                        "task_description": (
                            f"{parent_desc}\n\n"
                            f"[Auto-split from {parent_id}: {desc_detail}]"
                        ),
                        "requirements_text": task.get("config", {}).get("requirements_text", ""),
                        "context": sub_ctx,
                    },
                })

        return result

    @staticmethod
    def _filter_trivial_test_init_tasks(
        tasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Gate 2b: Remove tasks whose sole target file is a test ``__init__.py``.

        After Gate 2a splits multi-file features into single-file sub-tasks,
        some sub-tasks may target ``tests/__init__.py`` or similar.  These are
        wasted implementation slots (Python 3 + pytest don't require them).

        Dangling dependency references to filtered task IDs are cleaned up so
        downstream wave/lane assignment sees a consistent graph.
        """
        filtered_ids: set[str] = set()
        result: List[Dict[str, Any]] = []
        for task in tasks:
            tf = task.get("config", {}).get("context", {}).get("target_files", [])
            if (
                len(tf) == 1
                and PlanIngestionWorkflow._is_trivial_test_init(tf[0])
            ):
                filtered_ids.add(task["task_id"])
                logger.info(
                    "Gate 2b: filtering trivial test init task %s (%s)",
                    task["task_id"],
                    tf[0],
                )
            else:
                result.append(task)
        # Clean up dangling dependency references
        if filtered_ids:
            for task in result:
                task["depends_on"] = [
                    d for d in task.get("depends_on", [])
                    if d not in filtered_ids
                ]
        return result

    # ------------------------------------------------------------------
    # Manifest + context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_manifest_context(manifest: Any) -> Dict[str, Any]:
        """Extract architectural context from a ContextCore manifest."""
        ctx: Dict[str, Any] = {}

        # Objectives → project goals for prompt injection
        if hasattr(manifest, "strategy") and manifest.strategy:
            objectives = getattr(manifest.strategy, "objectives", [])
            if objectives:
                ctx["objectives"] = []
                for obj in objectives:
                    # v2 ObjectiveV2 has .description, v1 has .name
                    desc = getattr(obj, "description", None)
                    name_val = getattr(obj, "name", None)
                    label = desc if isinstance(desc, str) else (name_val if isinstance(name_val, str) else str(obj))
                    # Convert KeyResult models to dicts for JSON serialization
                    key_results = getattr(obj, "key_results", [])
                    kr_list = [
                        kr.model_dump() if hasattr(kr, "model_dump") else kr.dict()
                        if hasattr(kr, "dict") else kr
                        for kr in key_results
                    ]
                    ctx["objectives"].append({"name": label, "key_results": kr_list})

        # Guidance → constraints, preferences, focus
        guidance = getattr(manifest, "guidance", None)
        if guidance:
            constraints = getattr(guidance, "constraints", [])
            if constraints:
                ctx["constraints"] = [
                    {
                        "rule": getattr(c, "rule", str(c)),
                        "severity": getattr(c, "severity", "info"),
                        # v2 Constraint has .applies_to, v1 has .scope
                        "scope": getattr(c, "applies_to", None)
                        or getattr(c, "scope", "*"),
                    }
                    for c in constraints
                ]
            preferences = getattr(guidance, "preferences", [])
            if preferences:
                prefs = []
                for p in preferences:
                    # v2 Preference has .description, v1 has .preference
                    desc = getattr(p, "description", None)
                    pref_val = getattr(p, "preference", None)
                    prefs.append(
                        desc if isinstance(desc, str) else (pref_val if isinstance(pref_val, str) else str(p))
                    )
                ctx["preferences"] = prefs
            focus = getattr(guidance, "focus", None)
            if focus:
                areas = getattr(focus, "areas", [])
                if areas:
                    ctx["focus_areas"] = list(areas)

        return ctx

    @staticmethod
    def _extract_project_metadata(manifest: Any) -> Dict[str, Any]:
        """Extract operational project metadata from a ContextCore manifest.

        Pulls business criticality, SLO requirements, risk inventory, and
        observability config from ``manifest.spec``.  These are *operational*
        concerns (distinct from the *strategic* data in
        ``_extract_manifest_context``).
        """
        meta: Dict[str, Any] = {}
        spec = getattr(manifest, "spec", None)
        if spec is None:
            return meta

        # --- business criticality ---
        business = getattr(spec, "business", None)
        if business:
            criticality = getattr(business, "criticality", None)
            if criticality is not None:
                meta["criticality"] = (
                    criticality.value
                    if hasattr(criticality, "value")
                    else str(criticality)
                )
            # v2 BusinessSpec has .business_owner, v1 has .owner
            owner = getattr(business, "business_owner", None) or getattr(
                business, "owner", None
            )
            if owner:
                meta["business_owner"] = str(owner)
            # v2 BusinessSpec has .business_value, v1 has .value
            value = getattr(business, "business_value", None) or getattr(
                business, "value", None
            )
            if value:
                meta["business_value"] = str(value)

        # --- SLO / requirements ---
        requirements = getattr(spec, "requirements", None)
        if requirements:
            reqs: Dict[str, Any] = {}
            for attr in (
                "availability",
                "latency_p99",
                "throughput",
                "error_budget",
            ):
                val = getattr(requirements, attr, None)
                if val is not None:
                    reqs[attr] = (
                        val.value if hasattr(val, "value") else val
                    )
            if reqs:
                meta["requirements"] = reqs

        # --- risk inventory ---
        # Risk fields are all string-semantic (type, priority, description,
        # etc.), so non-enum values are coerced with str() — unlike
        # requirements/observability where numeric values are preserved.
        risks_raw = getattr(spec, "risks", None)
        if risks_raw:
            risks_list = []
            for risk in risks_raw:
                entry: Dict[str, Any] = {}
                for attr in (
                    "type",
                    "priority",
                    "description",
                    "scope",
                    "mitigation",
                    "component",
                ):
                    val = getattr(risk, attr, None)
                    if val is not None:
                        entry[attr] = (
                            val.value if hasattr(val, "value") else str(val)
                        )
                if entry:
                    risks_list.append(entry)
            if risks_list:
                meta["risks"] = risks_list

        # --- observability config ---
        observability = getattr(spec, "observability", None)
        if observability:
            obs: Dict[str, Any] = {}
            for attr in (
                "trace_sampling",
                "metrics_interval",
                "log_level",
            ):
                val = getattr(observability, attr, None)
                if val is not None:
                    obs[attr] = (
                        val.value if hasattr(val, "value") else val
                    )
            if obs:
                meta["observability"] = obs

        return meta

    @staticmethod
    def _extend_inventory_with_ingestion(
        output_dir: Path,
        doc_path: Path,
        context_seed_path: Path,
        design_calibration: Optional[Dict[str, Any]],
        context_files: Optional[List[str]],
        source_checksum_val: Optional[str],
        review_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Extend the artifact inventory with ingestion-stage entries.

        Finds run-provenance.json in the export output directory (derived
        from context_files) and extends it with plan_document,
        refine_suggestions, design_calibration, and task_decomposition entries.
        """
        from startd8.utils.artifact_inventory import extend_inventory

        # Derive export output directory from context_files
        export_dir: Optional[Path] = None
        if context_files:
            for raw_path in context_files:
                p = Path(raw_path.strip()).expanduser()
                if p.name == "onboarding-metadata.json":
                    export_dir = p.resolve().parent if p.is_absolute() else (output_dir / p).resolve().parent
                    break
                if p.name == "run-provenance.json":
                    export_dir = p.resolve().parent if p.is_absolute() else (output_dir / p).resolve().parent
                    break

        # Fall back to output_dir itself
        if not export_dir:
            export_dir = output_dir

        # Also check output_dir for run-provenance.json (common when export
        # and ingestion share the same output directory)
        if not (export_dir / "run-provenance.json").exists():
            if (output_dir / "run-provenance.json").exists():
                export_dir = output_dir
            else:
                logger.debug(
                    "artifact_inventory: no run-provenance.json found — "
                    "skipping inventory extension"
                )
                return

        now_iso = datetime.now(timezone.utc).isoformat()
        freshness = {}
        if source_checksum_val:
            freshness["source_checksum"] = source_checksum_val
            freshness["source_file"] = ".contextcore.yaml"

        entries: List[Dict[str, Any]] = []

        # plan_document
        if doc_path.exists():
            entries.append({
                "artifact_id": "ingestion.plan_document",
                "role": "plan_document",
                "description": "Structured plan with architecture, risk register, phase breakdown",
                "produced_by": "startd8.workflow.plan_ingestion",
                "stage": "ingestion",
                "source_file": doc_path.name,
                "sha256": _sha256_file_hex(doc_path),
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.design"],
                "consumption_hint": (
                    "Load architecture and risk sections as additional context "
                    "for design prompt."
                ),
            })

        # refine_suggestions — stored in the plan document appendix
        if doc_path.exists():
            plan_text = doc_path.read_text(encoding="utf-8")
            if review_output or "Appendix C" in plan_text or "## Architectural Review" in plan_text:
                entries.append({
                    "artifact_id": "ingestion.refine_suggestions",
                    "role": "refine_suggestions",
                    "description": "Architectural review suggestions from REFINE phase",
                    "produced_by": "startd8.workflow.plan_ingestion.refine",
                    "stage": "ingestion",
                    "source_file": doc_path.name,
                    "json_path": "Appendix C",
                    "sha256": _sha256_file_hex(doc_path),
                    "produced_at": now_iso,
                    "freshness": freshness,
                    "consumers": ["artisan.design"],
                    "consumption_hint": (
                        "Extract per-task suggestions and inject into FeatureContext. "
                        "Eliminates redundant architectural review in DESIGN."
                    ),
                })

        # refine_apply_provenance — structured triage/apply metadata
        if review_output:
            apply_data = review_output.get("apply", {})
            if apply_data.get("applied_count", 0) > 0:
                entries.append({
                    "artifact_id": "ingestion.refine_apply_provenance",
                    "role": "refine_apply_provenance",
                    "description": "Apply-step integration metadata from REFINE architectural review",
                    "produced_by": "startd8.workflow.plan_ingestion.refine",
                    "stage": "ingestion",
                    "applied_count": apply_data.get("applied_count", 0),
                    "applied_ids": apply_data.get("applied_ids", []),
                    "produced_at": now_iso,
                    "freshness": freshness,
                    "consumers": ["artisan.design", "artisan.implement"],
                    "consumption_hint": (
                        "Check applied_ids to avoid re-implementing suggestions "
                        "already integrated into the document body."
                    ),
                })

            # Enrich existing refine_suggestions entry with triage counts
            triage_data = review_output.get("triage", {})
            for entry in entries:
                if entry.get("artifact_id") == "ingestion.refine_suggestions":
                    entry["triage_accepted_count"] = triage_data.get("accepted", 0)
                    entry["triage_rejected_count"] = triage_data.get("rejected", 0)
                    break

        # design_calibration
        if design_calibration and context_seed_path.exists():
            cal_json = json.dumps(design_calibration, sort_keys=True, default=str)
            entries.append({
                "artifact_id": "ingestion.design_calibration",
                "role": "design_calibration",
                "description": "Per-task depth tier, calibrated section list, max output tokens",
                "produced_by": "startd8.workflow.plan_ingestion.emit",
                "stage": "ingestion",
                "source_file": context_seed_path.name,
                "json_path": "$.design_calibration",
                "sha256": sha256(cal_json.encode()).hexdigest(),
                "checksum_scope": "calibration_data_json",
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.design"],
                "consumption_hint": (
                    "Already consumed via seed. Listed for inventory completeness."
                ),
            })

        # task_decomposition
        if context_seed_path.exists():
            entries.append({
                "artifact_id": "ingestion.task_decomposition",
                "role": "task_decomposition",
                "description": "Per-task descriptions, file targets, complexity assessment",
                "produced_by": "startd8.workflow.plan_ingestion.emit",
                "stage": "ingestion",
                "source_file": context_seed_path.name,
                "json_path": "$.tasks",
                "sha256": _sha256_file_hex(context_seed_path),
                "produced_at": now_iso,
                "freshness": freshness,
                "consumers": ["artisan.plan", "artisan.design"],
                "consumption_hint": "Use for task ordering and feature context.",
            })

        if entries:
            extend_inventory(export_dir, entries)

    @staticmethod
    def _load_onboarding_metadata(
        context_files: Optional[List[str]],
        output_dir: Path,
    ) -> Optional[Dict[str, Any]]:
        """Load onboarding-metadata.json if present among context files.

        When context_files includes a path ending with 'onboarding-metadata.json',
        load and return its contents. Used for Items 5, 7 (merge into seed,
        artifact_manifest_path, project_context_path).
        """
        if not context_files:
            return None
        for raw_path in context_files:
            path = Path(raw_path.strip()).expanduser()
            if path.name != "onboarding-metadata.json":
                continue
            if not path.is_absolute():
                # Resolve relative to output_dir (common for plan ingestion)
                path = (output_dir / path).resolve()
            if not path.exists():
                logger.debug(
                    "onboarding-metadata.json referenced but not found: %s",
                    path,
                )
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    logger.debug(
                        "Loaded onboarding metadata from %s (%d keys)",
                        path,
                        len(data),
                    )
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to load onboarding-metadata.json %s: %s",
                    path,
                    exc,
                )
        return None

    @staticmethod
    def _derive_architectural_context(
        parsed_plan: ParsedPlan,
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

        # shared_modules: files targeted by 2+ features
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

        # import_conventions: most common parent directories
        dir_counter: Counter[str] = Counter()
        for feat in parsed_plan.features:
            for tf in feat.target_files:
                parent = str(Path(tf).parent)
                if parent != ".":
                    dir_counter[parent] += 1
        ctx["import_conventions"] = [
            d for d, _ in dir_counter.most_common(5)
        ]

        # domain_concepts: capitalized terms from goals
        concepts: list[str] = []
        for goal in parsed_plan.goals:
            # Parenthetical lists
            for m in re.findall(r"\(([^)]+)\)", goal):
                concepts.extend(
                    t.strip() for t in m.split(",") if t.strip()
                )
            # CamelCase / PascalCase terms
            concepts.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", goal))
        ctx["domain_concepts"] = list(dict.fromkeys(concepts))[:20]

        # dependency_clusters: root features (depended upon, no deps of their own)
        dep_graph = parsed_plan.dependency_graph
        # Features that are depended upon by others (from both dep_graph and feat.dependencies)
        depended_upon: set[str] = set()
        for deps in dep_graph.values():
            depended_upon.update(deps)
        for feat in parsed_plan.features:
            depended_upon.update(feat.dependencies)
        # Features that have their own dependencies (from either source)
        has_deps: set[str] = set(dep_graph.keys()) | {
            f.feature_id for f in parsed_plan.features if f.dependencies
        }
        # Roots = depended upon but have no deps of their own
        # Filter against known feature IDs to exclude hallucinated/typo'd IDs
        known_fids = {f.feature_id for f in parsed_plan.features}
        root_ids = [
            fid for fid in depended_upon
            if fid in known_fids
            and fid not in has_deps
        ]

        clusters: list[Dict[str, Any]] = []
        for root_id in root_ids[:10]:
            dependents: list[str] = []
            for fid, deps in dep_graph.items():
                if root_id in deps:
                    dependents.append(fid)
            # Also check feat.dependencies (may not be in dep_graph)
            for feat in parsed_plan.features:
                if root_id in feat.dependencies and feat.feature_id not in dependents:
                    dependents.append(feat.feature_id)
            if dependents:
                clusters.append({"root": root_id, "dependents": dependents})
        ctx["dependency_clusters"] = clusters

        return ctx

    @staticmethod
    def _derive_design_calibration(
        tasks: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Derive per-task design depth calibration.

        Uses ContextCore SizeEstimator when available, falls back to
        LOC-based heuristics.
        """
        estimator = None
        try:
            from contextcore.agent.size_estimation import SizeEstimator
            estimator = SizeEstimator()
        except ImportError:
            pass

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
                    complexity = (
                        "low" if loc <= 50
                        else ("medium" if loc <= 150 else "high")
                    )
            else:
                complexity = (
                    "low" if loc <= 50
                    else ("medium" if loc <= 150 else "high")
                )

            tier_name = {
                "low": "brief",
                "medium": "standard",
                "high": "comprehensive",
            }.get(complexity, "standard")
            tier = DEPTH_TIERS[tier_name]

            # Implement phase token caps: code gen needs more than design.
            # Claude models support 64K output; previous 16K default caused
            # truncation on medium-complexity tasks (PI-003/PI-005 post-mortem).
            implement_tokens = {
                "brief": 16384,
                "standard": 32768,
                "comprehensive": 49152,
            }.get(tier_name, 32768)

            # --- WCP-005: Domain-aware token adjustment ---
            # Prefer _enrichment from domain preflight if available;
            # otherwise infer domain from target file extensions.
            enrichment = task.get("_enrichment", {})
            domain = enrichment.get("domain")
            if not domain:
                target_files = ctx.get("target_files", [])
                if target_files:
                    exts = {
                        tf.rsplit(".", 1)[-1].lower()
                        for tf in target_files if "." in tf
                    }
                    has_python = "py" in exts
                    config_exts = {"toml", "yaml", "yml", "json", "ini", "cfg"}
                    has_config = bool(exts & config_exts)

                    if has_python:
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
                    elif has_config:
                        # Use the first config ext for the domain label
                        config_ext = next(
                            e for e in sorted(exts) if e in config_exts
                        )
                        domain = f"config-{config_ext.replace('yml', 'yaml')}"
                    elif exts:
                        domain = "non-python"
                if not domain:
                    domain = "unknown"
            domain_token_multipliers = {
                "config-toml": 0.5,
                "config-yaml": 0.5,
                "config-json": 0.5,
                "config-ini": 0.5,
                "config-cfg": 0.5,
                "non-python": 0.6,
                "python-test": 0.8,
                "python-single-module": 1.0,
                "python-package-module": 1.0,
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

    # ------------------------------------------------------------------
    # Phase: EMIT
    # ------------------------------------------------------------------

    def _phase_emit(
        self,
        doc_path: Path,
        route: ContractorRoute,
        complexity: ComplexityScore,
        output_dir: Path,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
        warn_cost_usd: Optional[float],
        max_cost_usd: Optional[float],
        parsed_plan: Optional[ParsedPlan] = None,
        step_costs: Optional[Dict[str, float]] = None,
        tracking_config: Optional["TaskTrackingConfig"] = None,
        manifest_context: Optional[Dict[str, Any]] = None,
        translation_quality: Optional[Dict[str, Any]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        onboarding_metadata: Optional[Dict[str, Any]] = None,
        review_output: Optional[Dict[str, Any]] = None,
        project_metadata: Optional[Dict[str, Any]] = None,
    ) -> EmitResult:
        from startd8.forward_manifest_extractor import extract_forward_contracts

        forward_manifest_dict: Optional[Dict[str, Any]] = None
        forward_manifest = None
        if parsed_plan is not None and parsed_plan.features:
            try:
                # REQ-PC-FM-001: Bridge to extractor API (features, proto_dir, etc.)
                features = parsed_plan.features
                tentative_contracts: Optional[List[Any]] = None
                if review_output:
                    # REFINE phase may produce tentative contracts (Phase 3)
                    triage = review_output.get("triage") or {}
                    if isinstance(triage, dict) and triage.get("contracts"):
                        from startd8.forward_manifest import InterfaceContract

                        raw = triage["contracts"]
                        if isinstance(raw, list):
                            tentative_contracts = [
                                c if isinstance(c, InterfaceContract) else InterfaceContract.model_validate(c)
                                for c in raw
                            ]
                proto_dir: Optional[Path] = None
                for candidate in (output_dir / "proto", output_dir.parent / "proto"):
                    if candidate.is_dir() and any(candidate.glob("*.proto")):
                        proto_dir = candidate
                        break
                yaml_text: Optional[str] = None
                if doc_path and doc_path.exists():
                    plan_text = doc_path.read_text(encoding="utf-8")
                    if "shared_contracts:" in plan_text:
                        yaml_text = plan_text

                forward_manifest = extract_forward_contracts(
                    features,
                    yaml_text=yaml_text,
                    proto_dir=proto_dir,
                    tentative_contracts=tentative_contracts,
                )

                forward_manifest_dict = forward_manifest.model_dump()
                if forward_manifest.contracts:
                    logger.info(
                        "Forward manifest extracted: %d contract(s) for Prime/Artisan",
                        len(forward_manifest.contracts),
                    )
            except Exception as exc:
                logger.warning("Forward manifest extraction failed: %s", exc, exc_info=True)
                forward_manifest_dict = None

        # Mottainai: deterministic file assembly — validate specs from ForwardManifest
        stub_manifest: Optional[List[Dict[str, Any]]] = None
        if forward_manifest_dict is not None and forward_manifest is not None:
            try:
                if hasattr(forward_manifest, "file_specs") and forward_manifest.file_specs:
                    from startd8.utils.file_assembler import DeterministicFileAssembler

                    assembler = DeterministicFileAssembler(module_inventory=None)
                    render_result = assembler.render_specs(forward_manifest)
                    if render_result.metadata:
                        stub_manifest = [entry._asdict() for entry in render_result.metadata]
                        logger.info(
                            "EMIT: deterministic file assembly validated %d skeleton(s) "
                            "from FLCM (%d render failures)",
                            len(stub_manifest),
                            len(render_result.failures),
                        )
            except Exception as exc:
                logger.warning(
                    "EMIT: deterministic file assembly validation failed: %s",
                    exc,
                    exc_info=True,
                )

        review_config: Dict[str, Any] = {
            "document_path": str(doc_path),
            "quality_tier": review_quality_tier,
            # Arc-review maps 1 agent = 1 round; reviewer_count controls round count.
            # Cap at 5 (arc-review's validated max).
            "reviewer_count": min(review_rounds, 5),
            "max_suggestions": 10,
            "scope": scope or "",
            "init_if_missing": True,
        }

        if context_files:
            review_config["context_files"] = context_files
        if warn_cost_usd is not None:
            review_config["warn_cost_usd"] = warn_cost_usd
        if max_cost_usd is not None:
            review_config["max_cost_usd"] = max_cost_usd

        # Add ingestion metadata
        review_config["_ingestion_metadata"] = {
            "route": route.value,
            "complexity_score": complexity.composite,
            "complexity_reasoning": complexity.reasoning,
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = output_dir / "review-config.json"
        with _tracer.start_as_current_span("io.review_config.write") as _io_span:
            atomic_write_json(config_path, review_config, indent=2)
            if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                _io_span.set_attribute("io.path", str(config_path))

        # --- Resolve onboarding once for both routes (eliminates
        # onboarding_early/onboarding_prime split that caused divergent
        # task derivation between seed, tracking, and traceability).
        context_seed_path: Optional[Path] = None
        onboarding_resolved: Optional[Dict[str, Any]] = None
        if parsed_plan is not None:
            if onboarding_metadata:
                onboarding_resolved = onboarding_metadata
            elif context_files:
                logger.debug("Onboarding not passed from PREFLIGHT — falling back to disk load")
                onboarding_resolved = self._load_onboarding_metadata(context_files, output_dir)

        # --- Derive tasks once and reuse for seed, tracking, and traceability.
        tasks: List[Dict[str, Any]] = []
        if parsed_plan is not None:
            tasks = self._derive_tasks_from_features(
                parsed_plan.features,
                parsed_plan.dependency_graph,
                requirement_to_feature=(translation_quality or {}).get(
                    "requirement_to_feature", {}
                ),
                artifact_to_feature=(translation_quality or {}).get(
                    "artifact_to_feature", {}
                ),
                requirement_hints=requirement_hints or {},
                output_path_conventions=(
                    onboarding_resolved.get("output_path_conventions")
                    if isinstance(onboarding_resolved, dict)
                    else None
                ),
            )

        # --- REQ-PC-FM-005: Rewrite forward manifest applicable_task_ids using actual task IDs
        # (must run AFTER _derive_tasks_from_features so skipped features and split
        #  sub-tasks are reflected — see task ID mapping divergence fix)
        if forward_manifest_dict is not None and parsed_plan is not None:
            # Build feature_id → [task_id, ...] from actual derived tasks
            # (accounts for skipped features and split sub-tasks)
            actual_fid_to_tids: Dict[str, List[str]] = {}
            for t in tasks:
                fid = t.get("config", {}).get("context", {}).get("feature_id", "")
                if fid:
                    actual_fid_to_tids.setdefault(fid, []).append(t["task_id"])

            # C-3 fix: build full set of ALL feature IDs (including skipped)
            # so we can distinguish stale feature refs from legitimate task IDs
            all_feature_ids = {
                f.feature_id for f in parsed_plan.features
            } if parsed_plan.features else set()

            if actual_fid_to_tids and forward_manifest_dict.get("contracts"):
                rewritten_contracts = []
                for c_dict in forward_manifest_dict["contracts"]:
                    old_ids = c_dict.get("applicable_task_ids") or []
                    if not old_ids:
                        rewritten_contracts.append(c_dict)
                        continue
                    new_ids: List[str] = []
                    for aid in old_ids:
                        mapped = actual_fid_to_tids.get(aid)
                        if mapped:
                            new_ids.extend(mapped)
                        elif aid in all_feature_ids:
                            # C-3: stale feature ID — was skipped/filtered,
                            # no tasks derived. Drop it to avoid downstream
                            # phases receiving contracts with nonexistent IDs.
                            logger.warning(
                                "Forward manifest: dropping stale feature ID %r from "
                                "contract %r (feature was skipped/filtered)",
                                aid, c_dict.get("contract_id", "?"),
                            )
                        else:
                            new_ids.append(aid)  # keep as-is — already a task ID or external ref
                    if not new_ids:
                        logger.warning(
                            "Forward manifest: dropping contract %r — all applicable "
                            "task IDs were invalidated (stale feature references)",
                            c_dict.get("contract_id", "?"),
                        )
                        continue
                    if new_ids != old_ids:
                        c_copy = dict(c_dict)
                        c_copy["applicable_task_ids"] = new_ids
                        rewritten_contracts.append(c_copy)
                    else:
                        rewritten_contracts.append(c_dict)
                forward_manifest_dict["contracts"] = rewritten_contracts
            elif forward_manifest_dict.get("contracts") and not actual_fid_to_tids:
                logger.warning(
                    "Forward manifest: skipping contract rewrite — no feature-to-task "
                    "mappings available (all tasks may have empty feature_id)"
                )

        # --- Shared derived data (both routes use the same logic) ---
        costs = step_costs or {}
        total_cost = sum(costs.values())
        m_ctx = manifest_context or {}
        architectural_context = (
            self._derive_architectural_context(parsed_plan, m_ctx)
            if parsed_plan is not None else {}
        )
        design_calibration = self._derive_design_calibration(tasks) if tasks else {}

        refine_suggestions = (
            self._extract_refine_suggestions_for_seed(review_output)
            if review_output else []
        )

        # --- Build common artifacts and onboarding_var ---
        def _build_seed_artifacts() -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
            """Build artifacts dict, onboarding_var, and source_checksum from resolved onboarding."""
            artifacts_out: Dict[str, Any] = {
                "plan_document_path": str(doc_path),
                "review_config_path": str(config_path),
            }
            ob_var: Optional[Dict[str, Any]] = None
            sc_val: Optional[str] = None

            if onboarding_resolved:
                ob_var = dict(onboarding_resolved)
                amp = onboarding_resolved.get("artifact_manifest_path")
                pcp = onboarding_resolved.get("project_context_path")
                if amp:
                    artifacts_out["artifact_manifest_path"] = str(amp)
                if pcp:
                    artifacts_out["project_context_path"] = str(pcp)
                ex = onboarding_resolved.get("example_artifacts")
                if ex and isinstance(ex, dict):
                    artifacts_out["example_artifacts"] = dict(ex)
                cg = onboarding_resolved.get("coverage_gaps")
                if cg and isinstance(cg, list):
                    artifacts_out["coverage_gaps"] = list(cg)
                sc = onboarding_resolved.get("source_checksum") or onboarding_resolved.get(
                    "export_provenance_checksum"
                )
                if sc and isinstance(sc, str):
                    artifacts_out["source_checksum"] = sc
                    sc_val = sc

            if ob_var is None:
                ob_var = {}
            ob_var["refine_suggestions"] = refine_suggestions
            # Keep artifacts["onboarding"] in sync with ob_var (which now includes refine_suggestions)
            if onboarding_resolved:
                artifacts_out["onboarding"] = ob_var

            if review_output:
                apply_data = review_output.get("apply", {})
                triage_data = review_output.get("triage", {})
                artifacts_out["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "triage_accepted": triage_data.get("accepted", 0),
                    "triage_rejected": triage_data.get("rejected", 0),
                    "applied_ids": apply_data.get("applied_ids", []),
                    "warning_ids": apply_data.get("warning_ids", []),
                    "apply_error": apply_data.get("error"),
                    "state_path": review_output.get("state_path"),
                }
            else:
                artifacts_out["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "apply_enabled": False,
                }

            if stub_manifest:
                artifacts_out["stub_manifest"] = stub_manifest

            return artifacts_out, ob_var, sc_val

        context_files_list = _context_files_with_checksums(
            context_files, base_dir=output_dir
        ) if context_files else None

        _ensure_onboarding_in_context_files(
            context_files_list, onboarding_resolved, output_dir,
        )

        service_metadata = _infer_service_metadata(
            parsed_plan.features if parsed_plan else [], onboarding_resolved,
        )

        ingestion_metrics = {
            **{f"{k}_cost": v for k, v in costs.items()},
            "total_cost": total_cost,
        }

        # Artisan route: emit artisan-context-seed.json
        if route == ContractorRoute.ARTISAN and parsed_plan is not None:
            artifacts, onboarding_var, source_checksum_val = _build_seed_artifacts()

            seed = ArtisanContextSeed(
                generated_at=datetime.now(timezone.utc).isoformat(),
                source_checksum=source_checksum_val,
                plan=parsed_plan.to_seed_dict(),
                complexity=complexity.to_seed_dict(),
                tasks=tasks,
                artifacts=artifacts,
                ingestion_metrics=ingestion_metrics,
                architectural_context=architectural_context,
                design_calibration=design_calibration,
                onboarding=onboarding_var,
                context_files=context_files_list,
                service_metadata=service_metadata or None,
                wave_metadata=None,
                lane_assignments=None,
                project_metadata=project_metadata or None,
                forward_manifest=forward_manifest_dict,
            )

            seed_dict = seed.to_dict()
            if not _validate_context_seed(seed_dict):
                seed_dict["_schema_valid"] = False
            _log_seed_coverage(seed_dict)
            context_seed_path = output_dir / "artisan-context-seed.json"
            with _tracer.start_as_current_span("io.context_seed.write") as _io_span:
                atomic_write_json(context_seed_path, seed_dict, indent=2)
                if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                    _io_span.set_attribute("io.path", str(context_seed_path))
                    _io_span.set_attribute("io.route", route.value)
                    _io_span.set_attribute("io.task_count", len(tasks))

            # Mottainai Rule 6: log propagation chain status
            _triage = review_output.get("triage", {}) if review_output else {}
            if refine_suggestions:
                logger.info(
                    "REFINE→seed chain INTACT: %d accepted suggestions forwarded",
                    len(refine_suggestions),
                )
            elif _triage.get("accepted", 0) > 0:
                logger.warning(
                    "REFINE→seed chain DEGRADED: %d accepted suggestions "
                    "available but not forwarded",
                    _triage["accepted"],
                )
            else:
                logger.debug("REFINE→seed chain N/A: no accepted suggestions to forward")

            # Mottainai: extend artifact inventory with ingestion-stage entries
            self._extend_inventory_with_ingestion(
                output_dir=output_dir,
                doc_path=doc_path,
                context_seed_path=context_seed_path,
                design_calibration=design_calibration,
                context_files=context_files,
                source_checksum_val=source_checksum_val,
                review_output=review_output,
            )

        # Prime route: emit prime-context-seed.json (symmetric with artisan)
        if route == ContractorRoute.PRIME and parsed_plan is not None:
            artifacts_prime, onboarding_var_prime, source_checksum_prime = _build_seed_artifacts()

            seed_prime = ArtisanContextSeed(
                generated_at=datetime.now(timezone.utc).isoformat(),
                source_checksum=source_checksum_prime,
                plan=parsed_plan.to_seed_dict(),
                complexity=complexity.to_seed_dict(),
                tasks=tasks,
                artifacts=artifacts_prime,
                ingestion_metrics=ingestion_metrics,
                architectural_context=architectural_context,
                design_calibration=design_calibration,
                onboarding=onboarding_var_prime,
                context_files=context_files_list,
                service_metadata=service_metadata or None,
                wave_metadata=None,
                lane_assignments=None,
                forward_manifest=forward_manifest_dict,
                project_metadata=project_metadata or None,
            )

            seed_prime_dict = seed_prime.to_dict()
            if not _validate_context_seed(seed_prime_dict):
                seed_prime_dict["_schema_valid"] = False
            _log_seed_coverage(seed_prime_dict, label="prime")
            prime_seed_path = output_dir / "prime-context-seed.json"
            with _tracer.start_as_current_span("io.context_seed.write") as _io_span:
                atomic_write_json(prime_seed_path, seed_prime_dict, indent=2)
                if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                    _io_span.set_attribute("io.path", str(prime_seed_path))
                    _io_span.set_attribute("io.route", route.value)
                    _io_span.set_attribute("io.task_count", len(tasks))

            # Mottainai Rule 6: log propagation chain status (prime)
            _triage_p = review_output.get("triage", {}) if review_output else {}
            if refine_suggestions:
                logger.info(
                    "REFINE→prime seed chain INTACT: %d accepted suggestions forwarded",
                    len(refine_suggestions),
                )
            elif _triage_p.get("accepted", 0) > 0:
                logger.warning(
                    "REFINE→prime seed chain DEGRADED: %d accepted suggestions "
                    "available but not forwarded",
                    _triage_p["accepted"],
                )
            else:
                logger.debug("REFINE→prime seed chain N/A: no accepted suggestions to forward")

            # Mottainai: extend artifact inventory
            self._extend_inventory_with_ingestion(
                output_dir=output_dir,
                doc_path=doc_path,
                context_seed_path=prime_seed_path,
                design_calibration=design_calibration,
                context_files=context_files,
                source_checksum_val=source_checksum_prime,
                review_output=review_output,
            )

            # Track as context_seed_path for return value
            if context_seed_path is None:
                context_seed_path = prime_seed_path

        # Task tracking artifact generation (opt-in) — reuses the single
        # tasks list derived above (eliminates divergent onboarding source).
        tracking_result = None
        if tracking_config is not None and parsed_plan is not None:
            from .task_tracking_emitter import emit_task_tracking_artifacts

            with _tracer.start_as_current_span("io.task_tracking.write") as _io_span:
                tracking_result = emit_task_tracking_artifacts(
                    parsed_plan, complexity, tasks, tracking_config, output_dir,
                )
                if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                    _io_span.set_attribute(
                        "io.file_count",
                        tracking_result.get("state_file_count", 0) if tracking_result else 0,
                    )

        return EmitResult(config_path, review_config, context_seed_path, tracking_result, tasks)

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)
        steps: List[StepResult] = []
        state = IngestionState()

        plan_path = Path(str(config["plan_path"])).expanduser().resolve()
        output_dir = Path(str(config.get("output_dir", "."))).expanduser().resolve()
        threshold = int(config.get("complexity_threshold", 40))
        force_route = config.get("force_route")
        review_rounds = int(config.get("review_rounds", 2))
        skip_arc_review = _as_bool(config.get("skip_arc_review"), False)
        review_quality_tier = str(config.get("review_quality_tier", "flagship"))
        contextcore_export_dir = config.get("contextcore_export_dir")
        min_export_coverage = float(config.get("min_export_coverage", 0))
        scope = config.get("scope")
        _raw_warn = config.get("warn_cost_usd")
        warn_cost_usd = float(_raw_warn) if _raw_warn is not None else None
        _raw_max = config.get("max_cost_usd")
        max_cost_usd = float(_raw_max) if _raw_max is not None else None
        context_files = _parse_context_files(config.get("context_files"))
        llm_read_timeout_seconds = float(config.get("llm_read_timeout_seconds", 300))
        llm_max_attempts = int(config.get("llm_max_attempts", 1))
        enable_heuristic_parse_fallback = _as_bool(
            config.get("enable_heuristic_parse_fallback"), True
        )
        requirements_path = config.get("requirements_path")
        requirements_files = _parse_file_list(config.get("requirements_files"))
        if requirements_path:
            requirements_files = [str(requirements_path)] + requirements_files
        _VALID_QUALITY_POLICIES = {"fail", "bias_artisan"}
        low_quality_policy = str(config.get("low_quality_policy", "bias_artisan")).strip().lower()
        if low_quality_policy not in _VALID_QUALITY_POLICIES:
            logger.warning(
                "Unrecognized low_quality_policy %r — defaulting to 'bias_artisan'. "
                "Valid values: %s",
                low_quality_policy, _VALID_QUALITY_POLICIES,
            )
            low_quality_policy = "bias_artisan"
        min_requirements_coverage = float(config.get("min_requirements_coverage", 70))
        min_artifact_mapping_coverage = float(config.get("min_artifact_mapping_coverage", 70))
        max_contract_conflicts = int(config.get("max_contract_conflicts", 2))
        timeout_config = TimeoutConfig(read=llm_read_timeout_seconds)
        retry_config = RetryConfig(max_attempts=llm_max_attempts)

        # Mottainai (Layer 1): Attempt to load onboarding from inventory to prevent waste
        try:
            from startd8.utils import artifact_inventory
            inventory = artifact_inventory.load_inventory(output_dir)
            onboarding_entry, outcome = artifact_inventory.lookup_artifact(inventory, "onboarding")
            
            if outcome == "hit" and onboarding_entry:
                onboarding_raw = artifact_inventory.load_artifact_content(onboarding_entry, output_dir)
                if isinstance(onboarding_raw, dict) and "_cc_capabilities" in onboarding_raw:
                    config["_cc_capabilities"] = onboarding_raw["_cc_capabilities"]
                    logger.info("Mottainai: loaded _cc_capabilities from artifact_inventory")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning(
                "Mottainai Layer 1: inventory lookup failed (non-fatal): %s",
                exc,
            )

        # Capability Propagation (Layer 5)
        _cap_validation_error: Optional[str] = None
        try:
            from contextcore.contracts.capability.validator import CapabilityValidator
            from contextcore.contracts.propagation.loader import ContractLoader
            
            contract_path = Path(__file__).parent.parent.parent / "contractors" / "contracts" / "plan-ingestion.contract.yaml"
            if contract_path.exists():
                logger.info("Loading CapabilityContract from %s", contract_path)
                # We load the contract and initiate the CapabilityValidator
                contract = ContractLoader.load_contract(str(contract_path))
                validator = CapabilityValidator(contract)

                # We validate entry capabilities
                cap_result = validator.validate_entry("plan-ingestion", config)
                if hasattr(cap_result, 'has_blocking_violations') and cap_result.has_blocking_violations():
                    _cap_validation_error = (
                        f"Capability validation failed (Layer 5): {cap_result}"
                    )
        except ImportError as e:
            logger.warning("ContextCore Layer 5 validation unavailable: %s", e)
        except Exception as e:
            logger.warning(
                "Capability validation unavailable (Layer 5 internal error, non-fatal): %s",
                e,
                exc_info=True,
            )

        # Task tracking (opt-in)
        generate_task_tracking = config.get("generate_task_tracking", False)
        tracking_config = None
        if generate_task_tracking:
            from .plan_ingestion_models import TaskTrackingConfig
            tracking_config = TaskTrackingConfig(
                project_id=config.get("project_id"),
                project_name=config.get("project_name"),
                sprint_id=config.get("sprint_id"),
                install_to_contextcore=config.get("install_to_contextcore", False),
                emit_ndjson_events=config.get("emit_ndjson_events", True),
            )

        total_steps = 6  # preflight, parse, assess, transform, refine, emit
        current_step = 0

        def progress(msg: str):
            nonlocal current_step
            current_step += 1
            if on_progress:
                on_progress(current_step, total_steps, msg)

        def _check_cost(label: str) -> Optional[WorkflowResult]:
            """Check cost thresholds, return error result if exceeded."""
            if warn_cost_usd is not None and state.total_cost > warn_cost_usd:
                logger.warning(
                    "Cost warning: $%.4f exceeds warn threshold $%.2f after %s",
                    state.total_cost, warn_cost_usd, label,
                )
            if max_cost_usd is not None and state.total_cost > max_cost_usd:
                return _fail(
                    f"Cost limit exceeded: ${state.total_cost:.4f} > "
                    f"${max_cost_usd:.2f} after {label}"
                )
            return None

        # Save state for debugging
        state_dir = output_dir / ".startd8"
        state_dir.mkdir(parents=True, exist_ok=True)

        def _save_state():
            """Persist current state for post-mortem debugging."""
            try:
                with _tracer.start_as_current_span("io.state.write") as _io_span:
                    atomic_write_json(
                        state_dir / "plan_ingestion_state.json",
                        state.to_dict(),
                        indent=2,
                    )
                    if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                        _io_span.set_attribute(
                            "io.path", str(state_dir / "plan_ingestion_state.json"),
                        )
            except Exception as exc:
                logger.debug("Failed to save ingestion state: %s", exc)

        def _fail(error_msg: str) -> WorkflowResult:
            """Record failure in state and return error result."""
            state.current_phase = IngestionPhase.FAILED
            state.error = error_msg
            _save_state()
            return WorkflowResult.from_error(
                self.metadata.workflow_id, error_msg, steps=steps,
            )

        # Deferred Layer 5 capability validation failure (set before _fail was defined)
        if _cap_validation_error:
            return _fail(_cap_validation_error)

        # OTel root span (manual lifecycle to avoid re-indenting 400 lines)
        _root_span_ctx = _tracer.start_as_current_span(
            "workflow.plan-ingestion",
            attributes={"workflow.id": self.metadata.workflow_id},
        )
        root_span = _root_span_ctx.__enter__()
        _active_phase_ctx = None  # Track open phase span for cleanup on early return

        try:
            # Read plan
            plan_text = plan_path.read_text(encoding="utf-8")
            step_costs: Dict[str, float] = {}
            onboarding_metadata: Optional[Dict[str, Any]] = None
            preflight_evidence: Dict[str, Any] = {"checksums": {}, "paths": {}, "coverage": {}}
            requirements_hints_index: Dict[str, Dict[str, Any]] = {}

            # --- DISCOVER .contextcore.yaml (needed by both PREFLIGHT and MANIFEST) ---
            contextcore_yaml: Optional[Path] = None
            _raw_cc_yaml = config.get("contextcore_yaml")
            if _raw_cc_yaml is not None:
                contextcore_yaml = Path(str(_raw_cc_yaml)).expanduser()
            else:
                # Auto-discover: project_root (most specific), output_dir, cwd
                candidates = [output_dir / ".contextcore.yaml", Path.cwd() / ".contextcore.yaml"]
                project_root = config.get("project_root")
                if project_root:
                    candidates.insert(0, Path(project_root) / ".contextcore.yaml")
                for candidate in candidates:
                    if candidate.exists():
                        contextcore_yaml = candidate
                        break

            # --- PREFLIGHT ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.preflight")
            _pf_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "preflight"})

            progress("Preflight")
            preflight_step = StepResult(step_name="preflight", output="Running export contract checks")
            onboarding_metadata, preflight_evidence, preflight_warnings, preflight_errors = (
                self._preflight_export_contract(
                    contextcore_export_dir=contextcore_export_dir,
                    context_files=context_files,
                    output_dir=output_dir,
                    min_export_coverage=min_export_coverage,
                    contextcore_yaml_path=contextcore_yaml,
                )
            )
            if preflight_warnings:
                preflight_step.output = (
                    preflight_step.output
                    + "; warnings: "
                    + " | ".join(preflight_warnings[:5])
                )
            if preflight_errors:
                preflight_step.error = " ; ".join(preflight_errors)
            steps.append(preflight_step)

            if _HAS_OTEL and not isinstance(_pf_span, _NoOpSpan):
                _pf_span.set_attribute("phase.warnings_count", len(preflight_warnings))
                _pf_span.set_attribute("phase.errors_count", len(preflight_errors))
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if preflight_step.error:
                return _fail(preflight_step.error)
            requirements_hints_index = _normalize_requirements_hints(onboarding_metadata)

            # Load requirements corpus for routing quality + dual-document refine
            requirements_docs = _load_requirements_documents(requirements_files, output_dir)
            if requirements_files and not requirements_docs:
                return _fail(
                    "Requirements files were provided but none could be loaded. "
                    "Check requirements_path/requirements_files paths."
                )

            # --- MANIFEST LOADING (optional) ---
            manifest_context: Dict[str, Any] = {}
            project_metadata: Dict[str, Any] = {}
            if contextcore_yaml:
                try:
                    from contextcore.models import load_manifest
                    manifest = load_manifest(str(contextcore_yaml))
                    manifest_context = self._extract_manifest_context(manifest)
                    project_metadata = self._extract_project_metadata(manifest)
                    logger.debug(
                        "Loaded manifest from %s: %d context keys, %d metadata keys",
                        contextcore_yaml, len(manifest_context), len(project_metadata),
                    )
                except ImportError:
                    logger.debug("contextcore not installed — skipping manifest loading")
                except Exception as exc:
                    logger.warning("Failed to load manifest %s: %s", contextcore_yaml, exc)

            # --- PARSE ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.parse")
            _parse_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "parse"})

            progress("Parse")
            state.current_phase = IngestionPhase.PARSE
            assessor = self._resolve_assessor_agent(
                config,
                timeout_config=timeout_config,
                retry_config=retry_config,
            )

            parsed_plan, parse_step = self._phase_parse(plan_text, assessor)
            _used_heuristic_parse = False
            if parse_step.error and enable_heuristic_parse_fallback:
                parsed_plan = _heuristic_parse_plan(plan_text)
                _used_heuristic_parse = True
                parse_step.error = None
                parse_step.output = (
                    parse_step.output + "\n[heuristic fallback] parse succeeded without LLM JSON"
                )[:_OUTPUT_TRUNCATION]
                parse_step.metadata["heuristic_fallback"] = True
                if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                    _parse_span.add_event("decision.heuristic_fallback", {
                        "phase": "parse",
                        "reason": "LLM parse failed, heuristic enabled",
                    })
            steps.append(parse_step)
            state.total_cost += parse_step.cost
            step_costs["parse"] = parse_step.cost
            if parse_step.error:
                return _fail(parse_step.error)
            state.parsed_plan = parsed_plan
            logger.debug(
                "Parsed plan: '%s' with %d features (heuristic=%s)",
                parsed_plan.title, len(parsed_plan.features), _used_heuristic_parse,
            )

            # When heuristic parse collapses all features into a single
            # fallback entry, translation quality metrics are unreliable
            # (everything maps to the one feature → inflated coverage).
            # Track this so downstream routing can compensate.
            _heuristic_degraded = (
                _used_heuristic_parse
                and len(parsed_plan.features) == 1
                and parsed_plan.features[0].feature_id == "F-001"
                and not parsed_plan.features[0].target_files
                and parsed_plan.features[0].description
                == _HEURISTIC_FALLBACK_DESCRIPTION
            )
            if _heuristic_degraded:
                logger.warning(
                    "Heuristic parse collapsed plan to single fallback feature — "
                    "translation quality metrics are unreliable; biasing toward artisan"
                )

            translation_quality = self._evaluate_translation_quality(
                parsed_plan=parsed_plan,
                requirements_docs=requirements_docs,
                onboarding=onboarding_metadata,
                requirements_hints=requirements_hints_index,
            )
            # Mark quality as degraded so traceability report is honest
            if _heuristic_degraded:
                translation_quality["_heuristic_degraded"] = True

            cost_err = _check_cost("parse")

            if _HAS_OTEL and not isinstance(_parse_span, _NoOpSpan):
                _parse_span.set_attribute("phase.cost", parse_step.cost)
                _parse_span.set_attribute("phase.heuristic_fallback", _used_heuristic_parse)
                _parse_span.set_attribute(
                    "phase.features_count",
                    len(parsed_plan.features) if parsed_plan else 0,
                )
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- ASSESS ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.assess")
            _assess_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "assess"})

            progress("Assess")
            state.current_phase = IngestionPhase.ASSESS

            _used_heuristic_assess = False
            complexity, assess_step = self._phase_assess(
                parsed_plan, assessor, threshold, force_route,
            )
            if assess_step.error and enable_heuristic_parse_fallback:
                _used_heuristic_assess = True
                complexity = _heuristic_assess_complexity(
                    parsed_plan,
                    threshold=threshold,
                    force_route=force_route,
                )
                assess_step.error = None
                assess_step.output = (
                    assess_step.output + "\n[heuristic fallback] assess succeeded deterministically"
                )[:_OUTPUT_TRUNCATION]
                assess_step.metadata["heuristic_fallback"] = True
                if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                    _assess_span.add_event("decision.heuristic_fallback", {
                        "phase": "assess",
                        "reason": "LLM assess failed, heuristic enabled",
                    })
            steps.append(assess_step)
            state.total_cost += assess_step.cost
            step_costs["assess"] = assess_step.cost
            if assess_step.error:
                return _fail(assess_step.error)
            state.complexity = complexity
            state.route = complexity.route

            # When heuristic parse produced a degraded single-feature plan,
            # the composite score is artificially low and quality metrics
            # are inflated.  Override routing to artisan unless the user
            # explicitly forced a route.
            if _heuristic_degraded and not force_route:
                complexity = _dataclass_replace(complexity, route=ContractorRoute.ARTISAN)
                state.complexity = complexity
                state.route = ContractorRoute.ARTISAN
                steps.append(
                    StepResult(
                        step_name="assess:heuristic-degradation-override",
                        output=(
                            "Heuristic parse produced single fallback feature — "
                            "routing forced to artisan to prevent under-orchestration"
                        ),
                    )
                )
                if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                    _assess_span.add_event("decision.route_override", {
                        "reason": "heuristic_degradation",
                        "original_route": complexity.route.value,
                        "forced_route": "artisan",
                    })

            low_quality_reasons: List[str] = []
            if (
                translation_quality["requirements_coverage_percent"]
                < min_requirements_coverage
            ):
                low_quality_reasons.append(
                    f"requirements_coverage={translation_quality['requirements_coverage_percent']:.1f}%"
                )
            if (
                translation_quality["artifact_mapping_percent"]
                < min_artifact_mapping_coverage
            ):
                low_quality_reasons.append(
                    f"artifact_mapping={translation_quality['artifact_mapping_percent']:.1f}%"
                )
            if translation_quality["conflict_count"] > max_contract_conflicts:
                low_quality_reasons.append(
                    f"conflict_count={translation_quality['conflict_count']}"
                )

            if not force_route and low_quality_reasons:
                details = ", ".join(low_quality_reasons)
                if low_quality_policy == "fail":
                    if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                        _assess_span.add_event("decision.quality_gate_failed", {
                            "policy": "fail",
                            "details": details,
                        })
                    return _fail(
                        "Translation quality gate failed: "
                        + details
                        + ". Either improve mappings or use low_quality_policy=bias_artisan."
                    )
                complexity = _dataclass_replace(complexity, route=ContractorRoute.ARTISAN)
                state.complexity = complexity
                state.route = ContractorRoute.ARTISAN
                steps.append(
                    StepResult(
                        step_name="assess:quality-override",
                        output=(
                            "Low translation quality detected; routing forced to artisan. "
                            + details
                        ),
                    )
                )
                if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                    _assess_span.add_event("decision.route_override", {
                        "reason": "low_translation_quality",
                        "policy": low_quality_policy,
                        "details": details,
                        "original_route": complexity.route.value,
                        "forced_route": "artisan",
                    })

            logger.debug(
                "Complexity: %d → route=%s (threshold=%d)",
                complexity.composite,
                complexity.route.value if complexity.route else "?",
                threshold,
            )

            cost_err = _check_cost("assess")

            if _HAS_OTEL and not isinstance(_assess_span, _NoOpSpan):
                _assess_span.set_attribute("phase.cost", assess_step.cost)
                _assess_span.set_attribute(
                    "phase.route",
                    complexity.route.value if complexity.route else "unknown",
                )
                _assess_span.set_attribute("phase.composite_score", complexity.composite)
                _assess_span.set_attribute("phase.heuristic_fallback", _used_heuristic_assess)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            route = complexity.route
            if route is None:
                return _fail("Assessment did not produce a route")

            # --- TRANSFORM ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.transform")
            _transform_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "transform"})

            progress("Transform")
            state.current_phase = IngestionPhase.TRANSFORM
            transformer = self._resolve_transformer_agent(
                config,
                timeout_config=timeout_config,
                retry_config=retry_config,
            )

            doc_path, transform_step = self._phase_transform(
                parsed_plan, route, transformer, output_dir,
            )
            if transform_step.error and enable_heuristic_parse_fallback:
                out_filename = (
                    "plan-ingestion-tasks.yaml"
                    if route == ContractorRoute.PRIME
                    else "PLAN-ingested.md"
                )
                doc_path = output_dir / out_filename
                output_dir.mkdir(parents=True, exist_ok=True)
                atomic_write(doc_path, _heuristic_transform_content(parsed_plan, route))
                transform_step.error = None
                transform_step.output = f"Wrote {doc_path} via heuristic fallback"
            steps.append(transform_step)
            state.total_cost += transform_step.cost
            step_costs["transform"] = transform_step.cost
            if transform_step.error:
                return _fail(transform_step.error)
            state.plan_document_path = str(doc_path)

            cost_err = _check_cost("transform")

            if _HAS_OTEL and not isinstance(_transform_span, _NoOpSpan):
                _transform_span.set_attribute("phase.cost", transform_step.cost)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- REFINE ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.refine")
            _refine_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "refine"})

            progress("Refine")
            state.current_phase = IngestionPhase.REFINE

            if skip_arc_review:
                rounds_completed, refine_steps, refine_cost, review_output = (
                    0, [], 0.0, {},
                )
            else:
                rounds_completed, refine_steps, refine_cost, review_output = self._phase_refine(
                    doc_path,
                    review_rounds,
                    review_quality_tier,
                    scope,
                    context_files,
                    list(requirements_docs.values()) if requirements_docs else None,
                    warn_cost_usd,
                    max_cost_usd,
                    enable_apply=config.get("enable_apply"),
                    enable_prompt_caching=config.get("enable_prompt_caching"),
                    enable_triage=config.get("enable_triage"),
                )
            steps.extend(refine_steps)
            state.total_cost += refine_cost
            step_costs["refine"] = refine_cost

            cost_err = _check_cost("refine")

            if _HAS_OTEL and not isinstance(_refine_span, _NoOpSpan):
                _refine_span.set_attribute("phase.cost", refine_cost)
                _refine_span.set_attribute("phase.rounds_completed", rounds_completed)
                _refine_span.set_attribute("phase.skipped", skip_arc_review)
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            if cost_err:
                return cost_err

            # --- EMIT ---
            _active_phase_ctx = _tracer.start_as_current_span("ingestion.emit")
            _emit_span = _active_phase_ctx.__enter__()
            root_span.add_event("state.transition", {"phase": "emit"})

            progress("Emit")
            state.current_phase = IngestionPhase.EMIT

            emit_result = self._phase_emit(
                doc_path, route, complexity, output_dir,
                review_rounds, review_quality_tier, scope, context_files,
                warn_cost_usd, max_cost_usd,
                parsed_plan=parsed_plan,
                step_costs=step_costs,
                tracking_config=tracking_config,
                manifest_context=manifest_context,
                translation_quality=translation_quality,
                requirement_hints=requirements_hints_index,
                onboarding_metadata=onboarding_metadata,
                review_output=review_output,
                project_metadata=project_metadata,
            )

            # Emit deterministic traceability report for downstream auditing.
            # Reuse the same tasks derived in _phase_emit to ensure seed,
            # tracking, and traceability all agree on task decomposition.
            trace_payload = self._build_traceability_artifact(
                route=route,
                parsed_plan=parsed_plan,
                tasks=emit_result.tasks,
                quality=translation_quality,
                checksum_evidence=preflight_evidence.get("checksums", {}),
            )
            with _tracer.start_as_current_span("io.traceability.write") as _io_span:
                traceability_path = self._write_traceability_artifact(output_dir, trace_payload)
                if _HAS_OTEL and not isinstance(_io_span, _NoOpSpan):
                    _io_span.set_attribute("io.path", str(traceability_path))
            state.review_config_path = str(emit_result.config_path)
            if emit_result.context_seed_path is not None:
                state.context_seed_path = str(emit_result.context_seed_path)

            emit_output = f"Wrote {emit_result.config_path}"
            if emit_result.context_seed_path is not None:
                emit_output += f", {emit_result.context_seed_path}"
            emit_output += f", {traceability_path}"
            if emit_result.tracking_result:
                emit_output += f", {emit_result.tracking_result.get('state_file_count', 0)} tracking files"
            emit_step = StepResult(
                step_name="emit",
                output=emit_output,
            )
            steps.append(emit_step)

            if _HAS_OTEL and not isinstance(_emit_span, _NoOpSpan):
                _emit_span.set_attribute(
                    "phase.seed_path",
                    str(emit_result.context_seed_path) if emit_result.context_seed_path else "",
                )
                _emit_span.set_attribute("phase.config_path", str(emit_result.config_path))
            _active_phase_ctx.__exit__(None, None, None)
            _active_phase_ctx = None

            # --- DONE ---
            state.current_phase = IngestionPhase.COMPLETED

            # Save final state
            _save_state()

            completed_at = datetime.now(timezone.utc)
            total_ms = int((completed_at - started_at).total_seconds() * 1000)

            output: Dict[str, Any] = {
                "route": route.value,
                "plan_document_path": str(doc_path),
                "review_config_path": str(emit_result.config_path),
                "complexity_score": complexity.composite,
                "refine_rounds_completed": rounds_completed,
                "traceability_path": str(traceability_path),
                "translation_quality": {
                    "requirements_coverage_percent": translation_quality.get(
                        "requirements_coverage_percent", 100.0
                    ),
                    "artifact_mapping_percent": translation_quality.get(
                        "artifact_mapping_percent", 100.0
                    ),
                    "conflict_count": translation_quality.get("conflict_count", 0),
                },
            }
            if emit_result.context_seed_path is not None:
                output["context_seed_path"] = str(emit_result.context_seed_path)
            if emit_result.tracking_result:
                output["task_tracking"] = emit_result.tracking_result

            # OTel: finalize root span on success
            if _HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                root_span.set_attribute("workflow.route", route.value)
                root_span.set_attribute("workflow.total_cost", state.total_cost)
                root_span.set_status(_StatusCode.OK)

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output=output,
                metrics=WorkflowMetrics(
                    total_time_ms=total_ms,
                    input_tokens=sum(s.input_tokens for s in steps),
                    output_tokens=sum(s.output_tokens for s in steps),
                    total_cost=state.total_cost,
                    step_count=len(steps),
                ),
                steps=steps,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as exc:
            if _HAS_OTEL and not isinstance(root_span, _NoOpSpan):
                root_span.record_exception(exc)
                root_span.set_status(_StatusCode.ERROR, str(exc))
            logger.error("Plan ingestion failed: %s", exc, exc_info=True)
            return _fail(str(exc))
        finally:
            if _active_phase_ctx is not None:
                _active_phase_ctx.__exit__(None, None, None)
            _root_span_ctx.__exit__(None, None, None)
