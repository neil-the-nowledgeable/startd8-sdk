"""
PlanIngestionWorkflow — Parse a generic plan, assess complexity,
transform into SDK-native format, refine via architectural review,
and emit the plan doc + review-config.json.

Pipeline:  parse → assess → transform → refine → emit
"""

from __future__ import annotations

import json
import re
import time
from hashlib import sha256
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
from ...contractors.artisan_contractor import (
    _SAFE_TASK_ID_PATTERN,
    compute_lanes,
    compute_wave_index_map,
    compute_wave_metadata,
    compute_waves,
)
from ...logging_config import get_logger

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


def _validate_context_seed(data: Dict[str, Any]) -> None:
    """Validate context seed against JSON schema before write (Item 6).

    Uses jsonschema if installed; no-op otherwise.
    """
    try:
        import jsonschema

        jsonschema.validate(data, _ARTISAN_SEED_SCHEMA)
        logger.debug("Context seed validated against schema")
    except ImportError:
        pass  # Graceful fallback — jsonschema not installed
    except Exception as e:
        logger.warning(
            "Context seed schema validation failed: %s — writing anyway",
            str(e),
        )
        # Log but do not raise — validation is advisory; seed may have extra keys


class _TaskDictAdapter:
    """Adapts plan-ingestion task dicts to the ``WaveComputeTask`` protocol.

    Satisfies the ``WaveComputeTask`` Protocol defined in
    ``artisan_contractor.py`` (``task_id`` + ``depends_on`` properties).

    This is the single normalization point for task dict → WaveComputeTask
    conversion. Plan ingestion task dicts come from LLM-generated PARSE
    output where depends_on may be null, absent, or contain non-string
    entries.
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def task_id(self) -> str:
        return self._data["task_id"]

    @property
    def depends_on(self) -> list[str]:
        raw = self._data.get("depends_on") or []
        cleaned = []
        for d in raw:
            if not isinstance(d, str) or not d:
                continue
            if not _SAFE_TASK_ID_PATTERN.match(d):
                logger.warning(
                    "Task %s: depends_on reference %r contains unsafe "
                    "characters (must match %s) — filtering out",
                    self._data.get("task_id"), d,
                    _SAFE_TASK_ID_PATTERN.pattern,
                )
                continue
            cleaned.append(d)
        return cleaned

    @property
    def target_files(self) -> list:
        """Read target_files from config.context (compute_lanes() protocol)."""
        return self._data.get("config", {}).get("context", {}).get(
            "target_files", []
        ) or []


def _assign_wave_indices(
    tasks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Assign wave_index to each task dict based on dependency depth.

    Delegates to compute_waves() via _TaskDictAdapter objects, then
    uses compute_wave_index_map() to map wave indices back onto the
    original task dicts.

    Returns:
        (tasks, wave_metadata) — tasks with wave_index added, and
        wave metadata dict (wave_count, wave_summary, critical_path_length).
    """
    if not tasks:
        return tasks, {"wave_count": 0, "wave_summary": [], "critical_path_length": 0}

    adapters = [_TaskDictAdapter(t) for t in tasks]
    waves = compute_waves(adapters)
    wave_map = compute_wave_index_map(waves)
    wave_meta = compute_wave_metadata(waves)

    for task in tasks:
        tid = task.get("task_id", "")
        task["wave_index"] = wave_map.get(tid, 0)

    return tasks, wave_meta


def _assign_lane_indices(
    tasks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Assign lane_index to each task dict based on shared target_files.

    Delegates to compute_lanes() via _TaskDictAdapter objects.
    Lane indices are advisory — target_files may be incomplete at
    plan ingestion time (populated later during PLAN/SCAFFOLD).

    Returns:
        (tasks, lane_assignments) — tasks with lane_index added
        (at top level), and lane_assignments dict (task_id → lane_index).
        When compute_lanes() fails or target_files are all empty,
        lane_assignments is {} and no lane_index keys are added.
    """
    if not tasks:
        return tasks, {}

    adapters = [_TaskDictAdapter(t) for t in tasks]
    try:
        lanes = compute_lanes(adapters)
    except Exception as exc:
        logger.warning(
            "Lane assignment skipped (compute_lanes() failed): %s", exc
        )
        return tasks, {}

    lane_assignments: dict[str, int] = {}
    for lane_idx, lane_tasks in enumerate(lanes):
        for adapter in lane_tasks:
            lane_assignments[adapter.task_id] = lane_idx

    for task in tasks:
        tid = task.get("task_id", "")
        if tid in lane_assignments:
            task["lane_index"] = lane_assignments[tid]

    return tasks, lane_assignments


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
        1 for t in tasks if not t.get("config", {}).get("target_files")
    )
    if tasks_missing_targets > 0:
        warnings.append(
            f"{tasks_missing_targets}/{len(tasks)} task(s) missing target_files"
        )

    tasks_missing_description = sum(
        1 for t in tasks if not t.get("config", {}).get("description")
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
      "artifact_types_addressed": ["optional artifact types e.g. servicemonitor", "prometheus_rule"]
    }}
  ],
  "mentioned_files": ["every file path mentioned in the plan"],
  "dependency_graph": {{"F-001": ["F-002"]}}
}}

## target_files guidance

Each feature becomes ONE implementation task sent to a code-generation LLM.
Multi-file tasks are significantly harder for the generator — it must produce a
separate code block per file, and commonly drops files (especially __init__.py).

Rules for target_files:
1. PREFER one primary file per feature. Split into separate features if files
   can be implemented independently.
2. Group files into ONE feature ONLY when they MUST be implemented atomically
   (e.g. a module + its __init__.py that re-exports from it).
3. NEVER exceed 3 target_files per feature. If a feature needs 4+ files,
   decompose it into smaller features with dependencies between them.
4. When __init__.py is among target_files, list it FIRST — it is the package
   root that other files import from.

design_doc_sections: optional list of content hints to emphasize in the design doc (e.g. parameter validation, error handling). Omit or empty if not applicable.
artifact_types_addressed: optional list of artifact types this feature generates (e.g. servicemonitor, prometheus_rule, dashboard). Omit or empty if not applicable.

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

    features: List[ParsedFeature] = []
    for idx, m in enumerate(
        re.finditer(r"^\s*###\s+([A-Za-z]+-\d+)\s*:\s*(.+)$", plan_text, flags=re.MULTILINE),
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
        deps = sorted(set(re.findall(r"\b([A-Za-z]+-\d+)\b", block)))
        deps = [d.upper() for d in deps if d.upper() != fid]
        features.append(
            ParsedFeature(
                feature_id=fid,
                name=name,
                description=block.strip().splitlines()[0].strip() if block.strip() else name,
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
                description="Fallback parsed feature from plan text",
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
    - PI-3: (future) modification_type classification via fqn_exists
    """
    feature_count = len(parsed_plan.features)

    # PI-2: Use manifest dependency graph when available
    if manifest_registry is not None:
        try:
            dep_graph = manifest_registry.dependency_graph()
            # Count unique cross-file dependencies from mentioned files
            mentioned_files = set()
            for f in parsed_plan.features:
                for tf in f.target_files:
                    mentioned_files.add(tf)
            cross_file_deps = sum(
                len(dep_graph.get(mf, set()))
                for mf in mentioned_files
            )
            logger.debug(
                "PI-2: manifest dependency graph used — %d files, %d edges",
                len(mentioned_files),
                cross_file_deps,
            )
        except Exception:
            cross_file_deps = sum(len(f.dependencies) for f in parsed_plan.features)
    else:
        cross_file_deps = sum(len(f.dependencies) for f in parsed_plan.features)

    # PI-1: Use manifest public_element_count when available
    if manifest_registry is not None:
        try:
            mentioned_files = set()
            for f in parsed_plan.features:
                for tf in f.target_files:
                    mentioned_files.add(tf)
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
    api_surface = min(100, max(10, api_surface))  # ensure bounds
    test_complexity = min(100, max(10, feature_count * 6))
    integration_depth = min(100, max(10, cross_file_deps * 10))
    domain_novelty = 40
    ambiguity = 45
    composite = int(
        (api_surface + test_complexity + integration_depth + domain_novelty + ambiguity) / 5
    )
    if force_route:
        route = ContractorRoute(force_route)
    else:
        route = ContractorRoute.PRIME if composite <= threshold else ContractorRoute.ARTISAN
    return ComplexityScore(
        feature_count=feature_count,
        cross_file_deps=cross_file_deps,
        api_surface=api_surface,
        test_complexity=test_complexity,
        integration_depth=integration_depth,
        domain_novelty=domain_novelty,
        ambiguity=ambiguity,
        composite=composite,
        reasoning="Heuristic fallback complexity used after assess failure",
        route=route,
    )


def _heuristic_transform_content(parsed_plan: ParsedPlan, route: ContractorRoute) -> str:
    """Deterministic fallback transform output."""
    if route == ContractorRoute.PRIME:
        tasks = []
        for idx, f in enumerate(parsed_plan.features, start=1):
            tasks.append(
                {
                    "task_id": f"PI-{idx:03d}",
                    "title": f.name,
                    "task_type": "task",
                    "priority": "medium",
                    "story_points": 3,
                    "labels": list(f.labels) or ["implementation"],
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
    if "-" in aid:
        suffix = aid.split("-", 1)[1]
        return _normalize_artifact_type(suffix)
    if "_" in aid:
        suffix = aid.split("_", 1)[1]
        return _normalize_artifact_type(suffix)
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

    fallback: List[str] = []
    for idx, line in enumerate(requirements_text.splitlines(), start=1):
        lower = line.lower()
        if ("must" in lower or "shall" in lower) and line.strip().startswith(("-", "*")):
            fallback.append(f"REQ-LINE-{idx}")
    return fallback


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
                    default=20,
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
                attempts_val = int(attempts_raw)
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
            agent.max_tokens = 64000
        return agent

    # ------------------------------------------------------------------
    # Phase: PARSE
    # ------------------------------------------------------------------

    def _phase_parse(
        self, plan_text: str, agent: BaseAgent
    ) -> Tuple[Optional[ParsedPlan], StepResult]:
        t0 = time.time()
        prompt = _PARSE_PROMPT.format(plan_text=plan_text)

        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
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

        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
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
        if force_route:
            route = ContractorRoute(force_route)
        else:
            composite = int(data.get("composite", 50))
            route = ContractorRoute.PRIME if composite <= threshold else ContractorRoute.ARTISAN
            llm_route = data.get("route", "").lower()
            if llm_route and llm_route != route.value:
                logger.debug(
                    "LLM suggested route '%s' but composite %d with threshold %d → '%s'",
                    llm_route, composite, threshold, route.value,
                )

        score = ComplexityScore(
            feature_count=int(data.get("feature_count", 0)),
            cross_file_deps=int(data.get("cross_file_deps", 0)),
            api_surface=int(data.get("api_surface", 0)),
            test_complexity=int(data.get("test_complexity", 0)),
            integration_depth=int(data.get("integration_depth", 0)),
            domain_novelty=int(data.get("domain_novelty", 0)),
            ambiguity=int(data.get("ambiguity", 0)),
            composite=int(data.get("composite", 0)),
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

        try:
            response_text, time_ms, token_usage = agent.generate(prompt)
        except Exception as exc:
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

        # Extract content from potential code fences
        content = extract_code_from_response(
            response_text,
            language="yaml" if route == ContractorRoute.PRIME else "markdown",
        )

        # Validate output
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
            if "##" not in content and "# " not in content:
                logger.warning("Generated markdown has no headings — may be low quality")

        # Write output
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / out_filename
        atomic_write(out_path, content)

        step = StepResult(
            step_name="transform",
            agent_name=agent.name,
            input=prompt[:_INPUT_TRUNCATION],
            output=f"Wrote {out_path}",
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
        plan_text = "\n".join(
            [
                parsed_plan.title,
                parsed_plan.raw_text,
                *(f"{f.feature_id} {f.name} {f.description}" for f in parsed_plan.features),
            ]
        ).lower()

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
            rid_lower = rid.lower()
            matched_features = [
                f.feature_id for f in parsed_plan.features
                if rid_lower in f"{f.feature_id} {f.name} {f.description}".lower()
            ]
            # fallback: requirement appears somewhere in plan text
            if rid_lower in plan_text and not matched_features and parsed_plan.features:
                matched_features = [parsed_plan.features[0].feature_id]
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
                req_sources[rid] = list(req_acceptance[rid])

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
        artifact_ids = [a for a in gaps if isinstance(a, str)]
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
            if not matched and parsed_plan.features:
                matched = [parsed_plan.features[0].feature_id]
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
            "reviewer_count": review_rounds,
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

        result = review_wf.run(review_config)

        review_cost = result.metrics.total_cost if result.metrics else 0.0
        rounds_completed = len(result.steps) if result.success else 0

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

        review_output = result.output if result.success else {}
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
            accepted = triage.get("accepted", 0)
            if accepted == 0:
                return []
            return [{
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
    def _derive_tasks_from_features(
        features: List[ParsedFeature],
        dependency_graph: Dict[str, List[str]],
        file_ownership: Optional[Dict[str, Any]] = None,
        requirement_to_feature: Optional[Dict[str, List[str]]] = None,
        artifact_to_feature: Optional[Dict[str, List[str]]] = None,
        requirement_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        output_path_conventions: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert ParsedFeatures into task dicts matching prime-route schema.

        Args:
            features: Parsed features from the PARSE phase.
            dependency_graph: Feature dependency graph.
            file_ownership: Optional file ownership mapping from ContextCore
                export's onboarding-metadata.json.  When present, enables
                contract-level file scope classification ("primary" vs "shared")
                per Principle 1 of the Export Pipeline Analysis Guide.
        """
        # Build a mapping from feature_id to task_id
        fid_to_tid: Dict[str, str] = {}
        for idx, feat in enumerate(features, start=1):
            fid_to_tid[feat.feature_id] = f"PI-{idx:03d}"

        # ------------------------------------------------------------------
        # Detect shared files: files that appear in multiple features'
        # target_files. These need special handling during implementation
        # to avoid the multi-file split failure (drafter omits shared files
        # thinking they belong to other tasks).
        # ------------------------------------------------------------------
        file_to_features: Dict[str, List[str]] = {}
        for feat in features:
            for tf in feat.target_files:
                file_to_features.setdefault(tf, []).append(feat.feature_id)
        shared_files: Dict[str, List[str]] = {
            f: fids for f, fids in file_to_features.items() if len(fids) > 1
        }

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

            # Priority: first third high, second third medium, rest low
            third = max(len(features) // 3, 1)
            if idx <= third:
                priority = "high"
            elif idx <= 2 * third:
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

            # ── Multi-file risk metadata ──────────────────────────────
            # Embed risk signals directly in the seed so downstream
            # phases (preflight, IMPLEMENT) don't need to re-derive them.
            if len(ordered_files) > 1:
                has_init = any(f.endswith("__init__.py") for f in ordered_files)
                ctx["_multi_file_risk"] = {
                    "file_count": len(ordered_files),
                    "has_init_py": has_init,
                    "high_loc": bool(
                        feat.estimated_loc and feat.estimated_loc > 200
                    ),
                }
                if len(ordered_files) > 3:
                    logger.warning(
                        "Task %s has %d target files (exceeds recommended "
                        "max of 3). Consider splitting into smaller features. "
                        "Files: %s",
                        tid,
                        len(ordered_files),
                        ", ".join(ordered_files),
                    )

            # ── File scope classification (defense-in-depth Principle 1) ──
            # Classify each target file as "primary" (this task owns it) or
            # "shared"/"stub" (other tasks also target it).  Sources:
            #   1. file_ownership from ContextCore export (contract-level)
            #   2. shared_files from feature cross-ref (plan-level)
            # This metadata flows into the seed so downstream phases
            # (Gate 2c, smart retry gate, review guard) use it directly
            # instead of re-deriving from design docs at runtime.
            _file_scope: Dict[str, str] = {}
            for tf in ordered_files:
                scope = "primary"
                # Check contract-level ownership from export
                if file_ownership:
                    ownership_entry = file_ownership.get(tf)
                    if ownership_entry and ownership_entry.get("scope") == "shared":
                        scope = "shared"
                # Check plan-level shared file detection
                if tf in shared_files and len(shared_files[tf]) > 1:
                    # File appears in multiple features — this task may
                    # not be the primary owner
                    owning_features = shared_files[tf]
                    if feat.feature_id != owning_features[0]:
                        # This task is NOT the first feature to claim the file
                        scope = "stub"
                    elif scope != "shared":
                        scope = "shared"
                _file_scope[tf] = scope

            if any(s != "primary" for s in _file_scope.values()):
                ctx["_file_scope"] = _file_scope
                logger.info(
                    "Task %s file scope: %s",
                    tid,
                    {f: s for f, s in _file_scope.items() if s != "primary"},
                )

            # Auto-generate prompt hints for multi-file tasks with shared modules.
            # These are merged into prompt_constraints during SeedTask.from_seed_entry().
            prompt_hints: List[str] = []
            if len(ordered_files) > 1:
                task_shared = [
                    f for f in ordered_files if f in shared_files
                ]
                if task_shared:
                    others_map = {
                        f: [fid_to_tid[fid] for fid in shared_files[f] if fid != feat.feature_id]
                        for f in task_shared
                    }
                    hint_parts = [
                        f"{f} (also used by {', '.join(tids)})"
                        for f, tids in others_map.items() if tids
                    ]
                    if hint_parts:
                        prompt_hints.append(
                            f"Shared module warning: {'; '.join(hint_parts)}. "
                            f"For this task, produce a minimal stub or interface "
                            f"for shared files (imports, docstring, empty registrations). "
                            f"Downstream tasks will implement the full logic."
                        )
            if prompt_hints:
                ctx["prompt_hints"] = prompt_hints

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
            if len(_requirements_text) > 2000:
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

        # ── Gate 2a: structural enforcement of multi-file task limits ──
        # Per defense-in-depth Principle 2 (adversarial thinking): even if
        # the PARSE prompt says "max 3 files," the LLM may ignore it.
        # Structurally split tasks that exceed the threshold so downstream
        # phases always receive well-sized work items.
        tasks = PlanIngestionWorkflow._split_oversized_tasks(tasks)

        # ── Wave assignment: BFS dependency-depth layering ──
        tasks, wave_metadata = _assign_wave_indices(tasks)
        logger.info(
            "Wave assignment: %d waves for %d tasks (critical path: %d)",
            wave_metadata.get("wave_count", 0),
            len(tasks),
            wave_metadata.get("critical_path_length", 0),
        )

        # CCD-402: Lane assignment: Union-Find on shared target_files (advisory)
        tasks, _lane_assignments = _assign_lane_indices(tasks)
        if _lane_assignments:
            _lane_count = len(set(_lane_assignments.values()))
            logger.info(
                "Lane assignment: %d lane(s) for %d tasks (advisory)",
                _lane_count,
                len(tasks),
            )

        return tasks

    @staticmethod
    def _split_oversized_tasks(
        tasks: List[Dict[str, Any]],
        max_files: int = 3,
    ) -> List[Dict[str, Any]]:
        """Gate 2a: Split tasks with more than `max_files` target files.

        Follows the Export Pipeline Analysis Guide's defense-in-depth
        Principle 1 (validate at the boundary) and Principle 2 (treat
        upstream as potentially adversarial).

        For each oversized task:
        - If an __init__.py is present, it becomes the first sub-task
          and all subsequent sub-tasks depend on it.
        - Remaining files become individual sub-tasks, each preserving
          the parent's description, labels, and dependencies.
        - Sub-tasks are numbered with a letter suffix (e.g. PI-001a,
          PI-001b) to preserve traceability to the original feature.
        - Estimated LOC is divided proportionally across sub-tasks.

        Tasks with ≤ max_files are passed through unchanged.
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

            logger.info(
                "Gate 2a: splitting task %s (%d files > max %d) into %d "
                "sub-tasks",
                parent_id,
                len(target_files),
                max_files,
                len(target_files),
            )

            # Separate __init__.py (if any) — it becomes sub-task 'a'
            # so other sub-tasks can depend on it.
            init_files = [f for f in target_files if f.endswith("__init__.py")]
            non_init_files = [f for f in target_files if not f.endswith("__init__.py")]
            ordered = init_files + non_init_files

            init_sub_id = None
            for idx, target_file in enumerate(ordered):
                suffix = chr(ord("a") + idx)
                sub_id = f"{parent_id}{suffix}"

                # Sub-task deps: parent's deps + init sub-task (if this
                # isn't the init sub-task itself).
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
                # Carry forward optional context fields
                for key in (
                    "design_doc_sections",
                    "artifact_types_addressed",
                ):
                    if key in ctx:
                        sub_ctx[key] = ctx[key]

                file_name = target_file.rsplit("/", 1)[-1]
                sub_title = f"{task['title']} — {file_name}"

                result.append({
                    "task_id": sub_id,
                    "title": sub_title,
                    "task_type": task.get("task_type", "task"),
                    "story_points": PlanIngestionWorkflow._estimate_story_points(
                        loc_per_file
                    ),
                    "priority": task.get("priority", "medium"),
                    "labels": list(task.get("labels", [])),
                    "depends_on": sub_deps,
                    "config": {
                        "task_description": (
                            f"{parent_desc}\n\n"
                            f"[Auto-split from {parent_id}: implement "
                            f"`{target_file}` only.]"
                        ),
                        "context": sub_ctx,
                    },
                })

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
                    export_dir = p.parent if p.is_absolute() else (output_dir / p).resolve().parent
                    break
                if p.name == "run-provenance.json":
                    export_dir = p.parent if p.is_absolute() else (output_dir / p).resolve().parent
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
            if "Appendix C" in plan_text or "refine" in plan_text.lower():
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
            import hashlib as _hashlib
            cal_json = json.dumps(design_calibration, sort_keys=True, default=str)
            entries.append({
                "artifact_id": "ingestion.design_calibration",
                "role": "design_calibration",
                "description": "Per-task depth tier, calibrated section list, max output tokens",
                "produced_by": "startd8.workflow.plan_ingestion.emit",
                "stage": "ingestion",
                "source_file": context_seed_path.name,
                "json_path": "$.design_calibration",
                "sha256": _hashlib.sha256(cal_json.encode()).hexdigest(),
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
        # Features that are depended upon by others
        depended_upon: set[str] = set()
        for deps in dep_graph.values():
            depended_upon.update(deps)
        # Features that have their own dependencies
        has_deps: set[str] = set(dep_graph.keys())
        # Roots = depended upon but have no deps of their own
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
            enrichment = task.get("_enrichment", {})
            domain = enrichment.get("domain", "unknown")
            domain_token_multipliers = {
                "config-toml": 0.5,
                "config-yaml": 0.5,
                "config-json": 0.5,
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
    ) -> Tuple[Path, dict, Optional[Path], Optional[Dict[str, Any]]]:
        review_config: Dict[str, Any] = {
            "document_path": str(doc_path),
            "quality_tier": review_quality_tier,
            "reviewer_count": review_rounds,
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
        atomic_write_json(config_path, review_config, indent=2)

        # Artisan route: also emit context seed JSON
        context_seed_path: Optional[Path] = None
        onboarding_early: Optional[Dict[str, Any]] = None
        if route == ContractorRoute.ARTISAN and parsed_plan is not None:
            costs = step_costs or {}
            total_cost = sum(costs.values())

            # Mottainai: prefer onboarding already loaded by PREFLIGHT
            # (avoids re-reading from disk and ensures data never silently
            # disappears when context_files omits onboarding-metadata.json).
            if onboarding_metadata:
                onboarding_early = onboarding_metadata
            elif context_files:
                logger.debug("Onboarding not passed from PREFLIGHT — falling back to disk load")
                onboarding_early = self._load_onboarding_metadata(context_files, output_dir)
            else:
                onboarding_early = None
            _file_ownership = (
                onboarding_early.get("file_ownership") if onboarding_early else None
            )

            tasks = self._derive_tasks_from_features(
                parsed_plan.features,
                parsed_plan.dependency_graph,
                file_ownership=_file_ownership,
                requirement_to_feature=(translation_quality or {}).get(
                    "requirement_to_feature", {}
                ),
                artifact_to_feature=(translation_quality or {}).get(
                    "artifact_to_feature", {}
                ),
                requirement_hints=requirement_hints or {},
                output_path_conventions=(
                    onboarding_early.get("output_path_conventions")
                    if isinstance(onboarding_early, dict)
                    else None
                ),
            )

            # Derive architectural context + design calibration
            m_ctx = manifest_context or {}
            architectural_context = self._derive_architectural_context(
                parsed_plan, m_ctx,
            )
            design_calibration = self._derive_design_calibration(tasks)

            # Build artifacts dict
            artifacts: Dict[str, Any] = {
                "plan_document_path": str(doc_path),
                "review_config_path": str(config_path),
            }

            # Merge onboarding metadata if present in context files (Items 5, 7)
            # Reuse the early load from before _derive_tasks_from_features.
            onboarding = onboarding_early
            onboarding_var: Optional[Dict[str, Any]] = None
            source_checksum_val: Optional[str] = None
            if onboarding:
                onboarding_var = onboarding
                artifacts["onboarding"] = onboarding
                amp = onboarding.get("artifact_manifest_path")
                pcp = onboarding.get("project_context_path")
                if amp:
                    artifacts["artifact_manifest_path"] = str(amp)
                if pcp:
                    artifacts["project_context_path"] = str(pcp)
                # Item 9: example artifacts per type (e.g. ServiceMonitor YAML) for implement phase
                ex = onboarding.get("example_artifacts")
                if ex and isinstance(ex, dict):
                    artifacts["example_artifacts"] = dict(ex)
                # Item 11: coverage gaps — artifact types to generate first
                cg = onboarding.get("coverage_gaps")
                if cg and isinstance(cg, list):
                    artifacts["coverage_gaps"] = list(cg)
                # Item 16: provenance chain — propagate source_checksum to seed
                sc = onboarding.get("source_checksum") or onboarding.get(
                    "export_provenance_checksum"
                )
                if sc and isinstance(sc, str):
                    artifacts["source_checksum"] = sc
                    source_checksum_val = sc

            # Mottainai: inject REFINE triage suggestions into seed onboarding
            refine_suggestions = (
                self._extract_refine_suggestions_for_seed(review_output)
                if review_output else []
            )
            if onboarding_var is None:
                onboarding_var = {}
            onboarding_var["refine_suggestions"] = refine_suggestions

            # Mottainai: record REFINE apply provenance for traceability
            if review_output:
                apply_data = review_output.get("apply", {})
                triage_data = review_output.get("triage", {})
                artifacts["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "triage_accepted": triage_data.get("accepted", 0),
                    "triage_rejected": triage_data.get("rejected", 0),
                    "applied_ids": apply_data.get("applied_ids", []),
                    "warning_ids": apply_data.get("warning_ids", []),
                    "apply_error": apply_data.get("error"),
                    "state_path": review_output.get("state_path"),
                }
            else:
                artifacts["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "apply_enabled": False,
                }

            context_files_list = _context_files_with_checksums(
                context_files, base_dir=output_dir
            ) if context_files else None

            _ensure_onboarding_in_context_files(
                context_files_list, onboarding_early, output_dir,
            )

            service_metadata = _infer_service_metadata(
                parsed_plan.features, onboarding_early,
            )

            # Compute wave metadata from per-task wave_index assignments
            _wave_indices = [t.get("wave_index", 0) for t in tasks]
            if _wave_indices:
                _wave_count = max(_wave_indices) + 1
                _wave_summary = [0] * _wave_count
                for wi in _wave_indices:
                    _wave_summary[wi] += 1
                _wave_meta: Optional[Dict[str, Any]] = {
                    "wave_count": _wave_count,
                    "wave_summary": _wave_summary,
                    "critical_path_length": _wave_count,
                }
            else:
                _wave_meta = None

            # CCD-402: Reconstruct lane_assignments from per-task lane_index
            _lane_assignments_emit: Optional[Dict[str, int]] = None
            _lane_tasks = [
                (t.get("task_id", ""), t.get("lane_index"))
                for t in tasks
                if t.get("lane_index") is not None
            ]
            if _lane_tasks:
                _lane_assignments_emit = {
                    tid: li for tid, li in _lane_tasks
                }

            seed = ArtisanContextSeed(
                generated_at=datetime.now(timezone.utc).isoformat(),
                source_checksum=source_checksum_val,
                plan=parsed_plan.to_seed_dict(),
                complexity=complexity.to_seed_dict(),
                tasks=tasks,
                artifacts=artifacts,
                ingestion_metrics={
                    **{f"{k}_cost": v for k, v in costs.items()},
                    "total_cost": total_cost,
                },
                architectural_context=architectural_context,
                design_calibration=design_calibration,
                onboarding=onboarding_var,
                context_files=context_files_list,
                service_metadata=service_metadata or None,
                wave_metadata=_wave_meta,
                lane_assignments=_lane_assignments_emit,
                project_metadata=project_metadata or None,
            )

            seed_dict = seed.to_dict()
            _validate_context_seed(seed_dict)
            _log_seed_coverage(seed_dict)
            context_seed_path = output_dir / "artisan-context-seed.json"
            atomic_write_json(context_seed_path, seed_dict, indent=2)

            # Mottainai Rule 6: log propagation chain status
            if review_output and review_output.get("triage", {}).get("accepted", 0) > 0:
                if refine_suggestions:
                    logger.info(
                        "REFINE→seed chain INTACT: %d accepted suggestions forwarded",
                        len(refine_suggestions),
                    )
                else:
                    logger.warning(
                        "REFINE→seed chain DEGRADED: %d accepted suggestions "
                        "available but not forwarded",
                        review_output["triage"]["accepted"],
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
            costs = step_costs or {}
            total_cost = sum(costs.values())

            # Mottainai: prefer onboarding already loaded by PREFLIGHT
            if onboarding_metadata:
                onboarding_prime = onboarding_metadata
            elif context_files:
                logger.debug("Onboarding not passed from PREFLIGHT (prime) — falling back to disk load")
                onboarding_prime = self._load_onboarding_metadata(context_files, output_dir)
            else:
                onboarding_prime = None
            _file_ownership = (
                onboarding_prime.get("file_ownership") if onboarding_prime else None
            )

            tasks = self._derive_tasks_from_features(
                parsed_plan.features,
                parsed_plan.dependency_graph,
                file_ownership=_file_ownership,
                requirement_to_feature=(translation_quality or {}).get(
                    "requirement_to_feature", {}
                ),
                artifact_to_feature=(translation_quality or {}).get(
                    "artifact_to_feature", {}
                ),
                requirement_hints=requirement_hints or {},
                output_path_conventions=(
                    onboarding_prime.get("output_path_conventions")
                    if isinstance(onboarding_prime, dict)
                    else None
                ),
            )

            # Mottainai: derive architectural_context + design_calibration
            # for prime route too (closes Gaps 11-12).
            m_ctx_prime = manifest_context or {}
            architectural_context_prime = self._derive_architectural_context(
                parsed_plan, m_ctx_prime,
            )
            design_calibration_prime = self._derive_design_calibration(tasks)

            artifacts_prime: Dict[str, Any] = {
                "plan_document_path": str(doc_path),
                "review_config_path": str(config_path),
            }

            onboarding_var_prime: Optional[Dict[str, Any]] = None
            source_checksum_prime: Optional[str] = None
            if onboarding_prime:
                onboarding_var_prime = onboarding_prime
                artifacts_prime["onboarding"] = onboarding_prime
                amp = onboarding_prime.get("artifact_manifest_path")
                pcp = onboarding_prime.get("project_context_path")
                if amp:
                    artifacts_prime["artifact_manifest_path"] = str(amp)
                if pcp:
                    artifacts_prime["project_context_path"] = str(pcp)
                sc = onboarding_prime.get("source_checksum") or onboarding_prime.get(
                    "export_provenance_checksum"
                )
                if sc and isinstance(sc, str):
                    artifacts_prime["source_checksum"] = sc
                    source_checksum_prime = sc

            # Mottainai: inject REFINE triage suggestions into prime seed onboarding
            refine_suggestions_prime = (
                self._extract_refine_suggestions_for_seed(review_output)
                if review_output else []
            )
            if onboarding_var_prime is None:
                onboarding_var_prime = {}
            onboarding_var_prime["refine_suggestions"] = refine_suggestions_prime

            # Mottainai: record REFINE apply provenance for traceability
            if review_output:
                apply_data = review_output.get("apply", {})
                triage_data = review_output.get("triage", {})
                artifacts_prime["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "triage_accepted": triage_data.get("accepted", 0),
                    "triage_rejected": triage_data.get("rejected", 0),
                    "applied_ids": apply_data.get("applied_ids", []),
                    "warning_ids": apply_data.get("warning_ids", []),
                    "apply_error": apply_data.get("error"),
                    "state_path": review_output.get("state_path"),
                }
            else:
                artifacts_prime["refine_provenance"] = {
                    "origin_phase": "ingestion.refine",
                    "apply_enabled": False,
                }

            context_files_list_prime = _context_files_with_checksums(
                context_files, base_dir=output_dir
            ) if context_files else None

            _ensure_onboarding_in_context_files(
                context_files_list_prime, onboarding_prime, output_dir,
            )

            service_metadata_prime = _infer_service_metadata(
                parsed_plan.features, onboarding_prime,
            )

            seed_prime = ArtisanContextSeed(
                generated_at=datetime.now(timezone.utc).isoformat(),
                source_checksum=source_checksum_prime,
                plan=parsed_plan.to_seed_dict(),
                complexity=complexity.to_seed_dict(),
                tasks=tasks,
                artifacts=artifacts_prime,
                ingestion_metrics={
                    **{f"{k}_cost": v for k, v in costs.items()},
                    "total_cost": total_cost,
                },
                architectural_context=architectural_context_prime,
                design_calibration=design_calibration_prime,
                onboarding=onboarding_var_prime,
                context_files=context_files_list_prime,
                service_metadata=service_metadata_prime or None,
            )

            seed_prime_dict = seed_prime.to_dict()
            _validate_context_seed(seed_prime_dict)
            _log_seed_coverage(seed_prime_dict, label="prime")
            prime_seed_path = output_dir / "prime-context-seed.json"
            atomic_write_json(prime_seed_path, seed_prime_dict, indent=2)

            # Mottainai Rule 6: log propagation chain status (prime)
            if review_output and review_output.get("triage", {}).get("accepted", 0) > 0:
                if refine_suggestions_prime:
                    logger.info(
                        "REFINE→prime seed chain INTACT: %d accepted suggestions forwarded",
                        len(refine_suggestions_prime),
                    )
                else:
                    logger.warning(
                        "REFINE→prime seed chain DEGRADED: %d accepted suggestions "
                        "available but not forwarded",
                        review_output["triage"]["accepted"],
                    )
            else:
                logger.debug("REFINE→prime seed chain N/A: no accepted suggestions to forward")

            # Mottainai: extend artifact inventory
            self._extend_inventory_with_ingestion(
                output_dir=output_dir,
                doc_path=doc_path,
                context_seed_path=prime_seed_path,
                design_calibration=design_calibration_prime,
                context_files=context_files,
                source_checksum_val=source_checksum_prime,
                review_output=review_output,
            )

            # Track as context_seed_path for return value
            if context_seed_path is None:
                context_seed_path = prime_seed_path

        # Task tracking artifact generation (opt-in)
        tracking_result = None
        if tracking_config is not None and parsed_plan is not None:
            from .task_tracking_emitter import emit_task_tracking_artifacts

            tracking_tasks = self._derive_tasks_from_features(
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
                    onboarding_early.get("output_path_conventions")
                    if isinstance(onboarding_early, dict)
                    else None
                ),
            )
            tracking_result = emit_task_tracking_artifacts(
                parsed_plan, complexity, tracking_tasks, tracking_config, output_dir,
            )

        return config_path, review_config, context_seed_path, tracking_result

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
        skip_arc_review = bool(config.get("skip_arc_review", False))
        review_quality_tier = str(config.get("review_quality_tier", "flagship"))
        contextcore_export_dir = config.get("contextcore_export_dir")
        min_export_coverage = float(config.get("min_export_coverage", 0))
        scope = config.get("scope")
        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
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
        low_quality_policy = str(config.get("low_quality_policy", "bias_artisan")).strip().lower()
        min_requirements_coverage = float(config.get("min_requirements_coverage", 70))
        min_artifact_mapping_coverage = float(config.get("min_artifact_mapping_coverage", 70))
        max_contract_conflicts = int(config.get("max_contract_conflicts", 2))
        timeout_config = TimeoutConfig(read=llm_read_timeout_seconds)
        retry_config = RetryConfig(max_attempts=llm_max_attempts)

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
                atomic_write_json(
                    state_dir / "plan_ingestion_state.json",
                    state.to_dict(),
                    indent=2,
                )
            except Exception:
                pass

        def _fail(error_msg: str) -> WorkflowResult:
            """Record failure in state and return error result."""
            state.current_phase = IngestionPhase.FAILED
            state.error = error_msg
            _save_state()
            return WorkflowResult.from_error(
                self.metadata.workflow_id, error_msg, steps=steps,
            )

        try:
            # Read plan
            plan_text = plan_path.read_text(encoding="utf-8")
            step_costs: Dict[str, float] = {}
            onboarding_metadata: Optional[Dict[str, Any]] = None
            preflight_evidence: Dict[str, Any] = {"checksums": {}, "paths": {}, "coverage": {}}
            requirements_hints_index: Dict[str, Dict[str, Any]] = {}

            # --- PREFLIGHT ---
            progress("Preflight")
            preflight_step = StepResult(step_name="preflight", output="Running export contract checks")
            onboarding_metadata, preflight_evidence, preflight_warnings, preflight_errors = (
                self._preflight_export_contract(
                    contextcore_export_dir=contextcore_export_dir,
                    context_files=context_files,
                    output_dir=output_dir,
                    min_export_coverage=min_export_coverage,
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
            contextcore_yaml = config.get("contextcore_yaml")
            if contextcore_yaml is None:
                # Auto-discover: project_root (most specific), output_dir, cwd
                candidates = [output_dir / ".contextcore.yaml", Path.cwd() / ".contextcore.yaml"]
                project_root = config.get("project_root")
                if project_root:
                    candidates.insert(0, Path(project_root) / ".contextcore.yaml")
                for candidate in candidates:
                    if candidate.exists():
                        contextcore_yaml = candidate
                        break
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
            progress("Parse")
            state.current_phase = IngestionPhase.PARSE
            assessor = self._resolve_assessor_agent(
                config,
                timeout_config=timeout_config,
                retry_config=retry_config,
            )

            parsed_plan, parse_step = self._phase_parse(plan_text, assessor)
            if parse_step.error and enable_heuristic_parse_fallback:
                parsed_plan = _heuristic_parse_plan(plan_text)
                parse_step.error = None
                parse_step.output = (
                    parse_step.output + "\n[heuristic fallback] parse succeeded without LLM JSON"
                )[:_OUTPUT_TRUNCATION]
            steps.append(parse_step)
            state.total_cost += parse_step.cost
            step_costs["parse"] = parse_step.cost
            if parse_step.error:
                return _fail(parse_step.error)
            state.parsed_plan = parsed_plan
            logger.debug(
                "Parsed plan: '%s' with %d features",
                parsed_plan.title, len(parsed_plan.features),
            )

            translation_quality = self._evaluate_translation_quality(
                parsed_plan=parsed_plan,
                requirements_docs=requirements_docs,
                onboarding=onboarding_metadata,
                requirements_hints=requirements_hints_index,
            )

            cost_err = _check_cost("parse")
            if cost_err:
                return cost_err

            # --- ASSESS ---
            progress("Assess")
            state.current_phase = IngestionPhase.ASSESS

            complexity, assess_step = self._phase_assess(
                parsed_plan, assessor, threshold, force_route,
            )
            if assess_step.error and enable_heuristic_parse_fallback:
                complexity = _heuristic_assess_complexity(
                    parsed_plan,
                    threshold=threshold,
                    force_route=force_route,
                )
                assess_step.error = None
                assess_step.output = (
                    assess_step.output + "\n[heuristic fallback] assess succeeded deterministically"
                )[:_OUTPUT_TRUNCATION]
            steps.append(assess_step)
            state.total_cost += assess_step.cost
            step_costs["assess"] = assess_step.cost
            if assess_step.error:
                return _fail(assess_step.error)
            state.complexity = complexity
            state.route = complexity.route

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
                    return _fail(
                        "Translation quality gate failed: "
                        + details
                        + ". Either improve mappings or use low_quality_policy=bias_artisan."
                    )
                complexity.route = ContractorRoute.ARTISAN
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

            logger.debug(
                "Complexity: %d → route=%s (threshold=%d)",
                complexity.composite,
                complexity.route.value if complexity.route else "?",
                threshold,
            )

            cost_err = _check_cost("assess")
            if cost_err:
                return cost_err

            route = complexity.route
            if route is None:
                return _fail("Assessment did not produce a route")

            # --- TRANSFORM ---
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
            if cost_err:
                return cost_err

            # --- REFINE ---
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
                    list(requirements_docs.keys()) if requirements_docs else None,
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
            if cost_err:
                return cost_err

            # --- EMIT ---
            progress("Emit")
            state.current_phase = IngestionPhase.EMIT

            config_path, review_config_data, context_seed_path, tracking_result = self._phase_emit(
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
            file_ownership = (
                onboarding_metadata.get("file_ownership")
                if isinstance(onboarding_metadata, dict)
                else None
            )
            trace_tasks = self._derive_tasks_from_features(
                parsed_plan.features,
                parsed_plan.dependency_graph,
                file_ownership=file_ownership,
                requirement_to_feature=translation_quality.get("requirement_to_feature", {}),
                artifact_to_feature=translation_quality.get("artifact_to_feature", {}),
                requirement_hints=requirements_hints_index,
                output_path_conventions=(
                    onboarding_metadata.get("output_path_conventions")
                    if isinstance(onboarding_metadata, dict)
                    else None
                ),
            )
            trace_payload = self._build_traceability_artifact(
                route=route,
                parsed_plan=parsed_plan,
                tasks=trace_tasks,
                quality=translation_quality,
                checksum_evidence=preflight_evidence.get("checksums", {}),
            )
            traceability_path = self._write_traceability_artifact(output_dir, trace_payload)
            state.review_config_path = str(config_path)
            if context_seed_path is not None:
                state.context_seed_path = str(context_seed_path)

            emit_output = f"Wrote {config_path}"
            if context_seed_path is not None:
                emit_output += f", {context_seed_path}"
            emit_output += f", {traceability_path}"
            if tracking_result:
                emit_output += f", {tracking_result.get('state_file_count', 0)} tracking files"
            emit_step = StepResult(
                step_name="emit",
                output=emit_output,
            )
            steps.append(emit_step)

            # --- DONE ---
            state.current_phase = IngestionPhase.COMPLETED

            # Save final state
            _save_state()

            completed_at = datetime.now(timezone.utc)
            total_ms = int((completed_at - started_at).total_seconds() * 1000)

            output: Dict[str, Any] = {
                "route": route.value,
                "plan_document_path": str(doc_path),
                "review_config_path": str(config_path),
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
            if context_seed_path is not None:
                output["context_seed_path"] = str(context_seed_path)
            if tracking_result:
                output["task_tracking"] = tracking_result

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
            logger.error("Plan ingestion failed: %s", exc, exc_info=True)
            return _fail(str(exc))
