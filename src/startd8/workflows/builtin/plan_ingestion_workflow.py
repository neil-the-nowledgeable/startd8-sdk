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
from ...model_catalog import Models
from ...utils.agent_resolution import resolve_agent_spec
from ...utils.code_extraction import extract_code_from_response
from ...utils.file_operations import atomic_write, atomic_write_json
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
from ...logging_config import get_logger

logger = get_logger(__name__)

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
    },
    "additionalProperties": True,
}


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
DEPTH_TIERS: Dict[str, Dict[str, Any]] = {
    "brief": {
        "sections": ["Overview", "Architecture", "Testing Strategy"],
        "max_tokens": 2048,
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
        "max_tokens": 4096,
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
        "max_tokens": 8192,
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
    if "-" not in artifact_id:
        return None
    suffix = artifact_id.split("-", 1)[1]
    return _normalize_artifact_type(suffix)


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

        return errors

    # ------------------------------------------------------------------
    # Agent resolution
    # ------------------------------------------------------------------

    def _resolve_assessor_agent(self, config: Dict[str, Any]) -> BaseAgent:
        spec = config.get("assessor_agent") or Models.CLAUDE_SONNET_LATEST
        return resolve_agent_spec(str(spec), name="plan-assessor")

    def _resolve_transformer_agent(self, config: Dict[str, Any]) -> BaseAgent:
        spec = config.get("transformer_agent") or Models.CLAUDE_SONNET_LATEST
        agent = resolve_agent_spec(str(spec), name="plan-transformer")
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

        response_text, time_ms, token_usage = agent.generate(prompt)
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

        response_text, time_ms, token_usage = agent.generate(prompt)
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

        response_text, time_ms, token_usage = agent.generate(prompt)
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

        # source_checksum verification — close provenance chain at ingestion.
        expected_source_checksum = onboarding.get("source_checksum")
        if not isinstance(expected_source_checksum, str):
            warnings.append("Preflight: source_checksum missing in onboarding metadata")
            evidence["checksums"]["source_checksum_verified"] = None
        elif contextcore_yaml_path is not None and contextcore_yaml_path.exists():
            actual_source_checksum = _checksum_file(contextcore_yaml_path)
            evidence["checksums"]["source_checksum_expected"] = expected_source_checksum
            evidence["checksums"]["source_checksum_actual"] = actual_source_checksum
            evidence["paths"]["contextcore_yaml"] = str(contextcore_yaml_path)
            if actual_source_checksum != expected_source_checksum:
                errors.append(
                    "Preflight: source_checksum mismatch — .contextcore.yaml has changed "
                    "since the export was generated. Re-run ContextCore export to refresh."
                )
                evidence["checksums"]["source_checksum_verified"] = False
            else:
                evidence["checksums"]["source_checksum_verified"] = True
                logger.info(
                    "Preflight: source_checksum verified against %s",
                    contextcore_yaml_path.name,
                )
        else:
            warnings.append(
                "Preflight: source_checksum present but .contextcore.yaml not available "
                "for verification"
            )
            evidence["checksums"]["source_checksum_verified"] = None

        return onboarding, evidence, warnings, errors

    @staticmethod
    def _write_preflight_report(
        output_dir: Path,
        passed: bool,
        evidence: Dict[str, Any],
        warnings: List[str],
        errors: List[str],
    ) -> Path:
        """Write preflight-report.json for downstream gating and auditing.

        Always written regardless of pass/fail so that downstream tools
        can programmatically inspect the preflight outcome.
        """
        source_checksum_verified = evidence.get("checksums", {}).get(
            "source_checksum_verified"
        )
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "source_checksum_verified": source_checksum_verified,
            "evidence": evidence,
            "warnings": warnings,
            "errors": errors,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "preflight-report.json"
        atomic_write_json(path, report, indent=2)
        return path

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
        req_to_feature: Dict[str, List[str]] = {}
        for rid in requirement_ids:
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

        mapped_requirements = sum(1 for fids in req_to_feature.values() if fids)
        total_requirements = len(requirement_ids)
        requirements_coverage = (
            (mapped_requirements / total_requirements) * 100.0
            if total_requirements
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
            artifact_to_feature[aid] = sorted(set(matched))

        mapped_artifacts = sum(1 for fids in artifact_to_feature.values() if fids)
        total_artifacts = len(artifact_ids)
        artifact_completeness = (
            (mapped_artifacts / total_artifacts) * 100.0
            if total_artifacts
            else 100.0
        )

        unmet_requirements = [rid for rid, fids in req_to_feature.items() if not fids]
        unmet_artifacts = [aid for aid, fids in artifact_to_feature.items() if not fids]
        conflict_count = len(unmet_requirements) + len(unmet_artifacts)

        return {
            "requirements_total": total_requirements,
            "requirements_mapped": mapped_requirements,
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
        refine_impact: Optional[Dict[str, Any]] = None,
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

        payload: Dict[str, Any] = {
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
        if refine_impact is not None:
            payload["refine_impact"] = refine_impact
        return payload

    @staticmethod
    def _write_traceability_artifact(output_dir: Path, payload: Dict[str, Any]) -> Path:
        """Write ingestion-traceability.json and return the path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "ingestion-traceability.json"
        atomic_write_json(path, payload, indent=2)
        return path

    @staticmethod
    def _enrich_prime_yaml_with_traceability(
        yaml_path: Path,
        translation_quality: Dict[str, Any],
        requirement_hints: Dict[str, Dict[str, Any]],
        parsed_plan: ParsedPlan,
    ) -> None:
        """Post-process Prime YAML output to inject requirement traceability.

        Injects ``requirement_ids``, ``acceptance_obligations``, and
        ``source_references`` into each Prime task's ``config.context`` block
        by matching feature IDs from translation quality mappings.

        This is a zero-LLM-cost enrichment — it modifies the YAML file
        in-place after the LLM generates it.
        """
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Cannot enrich Prime YAML at %s: %s", yaml_path, exc)
            return

        if not isinstance(data, dict):
            return
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            return

        req_to_feature = translation_quality.get("requirement_to_feature", {})
        req_acceptance = translation_quality.get("requirement_acceptance_anchors", {})
        req_sources = translation_quality.get("requirement_source_references", {})

        # Build reverse map: feature_id -> [requirement_ids]
        feature_to_requirements: Dict[str, List[str]] = {}
        for rid, fids in req_to_feature.items():
            for fid in fids:
                feature_to_requirements.setdefault(fid, []).append(rid)

        # Map task titles to feature IDs for matching.
        feature_by_name: Dict[str, str] = {}
        for feat in parsed_plan.features:
            feature_by_name[feat.name.lower()] = feat.feature_id
            feature_by_name[feat.feature_id.lower()] = feat.feature_id

        enriched = False
        for task in tasks:
            if not isinstance(task, dict):
                continue
            config = task.setdefault("config", {})
            ctx = config.setdefault("context", {})

            # Try to match task to a feature.
            task_title = (task.get("title") or "").lower()
            task_id = (task.get("task_id") or "").lower()
            matched_fid: Optional[str] = None
            for key in (task_title, task_id):
                if key in feature_by_name:
                    matched_fid = feature_by_name[key]
                    break
            if matched_fid is None:
                # Fallback: substring match on feature names.
                for feat in parsed_plan.features:
                    if feat.name.lower() in task_title or feat.feature_id.lower() in task_title:
                        matched_fid = feat.feature_id
                        break

            if matched_fid is None:
                continue

            mapped_requirements = feature_to_requirements.get(matched_fid, [])
            if not mapped_requirements:
                continue

            ctx["requirement_ids"] = sorted(set(mapped_requirements))

            acceptance_obligations: List[str] = []
            source_references: List[str] = []
            for rid in mapped_requirements:
                hint = requirement_hints.get(rid, {})
                anchors = hint.get("acceptance_anchors", req_acceptance.get(rid, []))
                if isinstance(anchors, list):
                    acceptance_obligations.extend(a for a in anchors if isinstance(a, str))
                refs = hint.get("source_references", req_sources.get(rid, []))
                if isinstance(refs, list):
                    source_references.extend(r for r in refs if isinstance(r, str))
            if acceptance_obligations:
                ctx["acceptance_obligations"] = sorted(set(acceptance_obligations))
            if source_references:
                ctx["source_references"] = sorted(set(source_references))

            enriched = True

        if enriched:
            atomic_write(yaml_path, yaml.dump(data, default_flow_style=False, sort_keys=False))
            logger.info("Enriched Prime YAML with requirement traceability fields")

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
    ) -> Tuple[int, List[StepResult], float]:
        if review_rounds <= 0:
            return 0, [], 0.0

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

        return rounds_completed, refine_steps, review_cost

    # ------------------------------------------------------------------
    # Artisan context seed helpers
    # ------------------------------------------------------------------

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
            ordered_files = sorted(
                feat.target_files,
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

                mapped_artifacts = feature_to_artifacts.get(feat.feature_id, [])
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
                    "context": ctx,
                },
            })

        # ── Gate 2a: structural enforcement of multi-file task limits ──
        # Per defense-in-depth Principle 2 (adversarial thinking): even if
        # the PARSE prompt says "max 3 files," the LLM may ignore it.
        # Structurally split tasks that exceed the threshold so downstream
        # phases always receive well-sized work items.
        tasks = PlanIngestionWorkflow._split_oversized_tasks(tasks)

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
            # brief=8192, standard=16384, comprehensive=32768
            implement_tokens = {
                "brief": 8192,
                "standard": 16384,
                "comprehensive": 32768,
            }.get(tier_name, 16384)

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
        if route == ContractorRoute.ARTISAN and parsed_plan is not None:
            costs = step_costs or {}
            total_cost = sum(costs.values())

            # Load onboarding metadata early so file_ownership is available
            # for _derive_tasks_from_features (defense-in-depth Principle 1).
            onboarding_early = self._load_onboarding_metadata(
                context_files, output_dir
            ) if context_files else None
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
                # Fix 2a: propagate parameter_sources for DESIGN/IMPLEMENT injection
                ps = onboarding.get("parameter_sources")
                if ps and isinstance(ps, dict):
                    artifacts["parameter_sources"] = ps
                # Fix 3a: propagate semantic_conventions for DESIGN/IMPLEMENT injection
                sc_conv = onboarding.get("semantic_conventions")
                if sc_conv and isinstance(sc_conv, dict):
                    artifacts["semantic_conventions"] = sc_conv
                # Fix 5: propagate output_conventions for SCAFFOLD validation
                oc = onboarding.get("output_conventions")
                if oc and isinstance(oc, dict):
                    artifacts["output_conventions"] = oc

            context_files_list = _context_files_with_checksums(
                context_files, base_dir=output_dir
            ) if context_files else None

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
            )

            seed_dict = seed.to_dict()
            _validate_context_seed(seed_dict)
            context_seed_path = output_dir / "artisan-context-seed.json"
            atomic_write_json(context_seed_path, seed_dict, indent=2)

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
        review_quality_tier = str(config.get("review_quality_tier", "flagship"))
        contextcore_export_dir = config.get("contextcore_export_dir")
        min_export_coverage = float(config.get("min_export_coverage", 0))
        scope = config.get("scope")
        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        context_files = _parse_context_files(config.get("context_files"))
        requirements_path = config.get("requirements_path")
        requirements_files = _parse_file_list(config.get("requirements_files"))
        if requirements_path:
            requirements_files = [str(requirements_path)] + requirements_files
        low_quality_policy = str(config.get("low_quality_policy", "bias_artisan")).strip().lower()
        min_requirements_coverage = float(config.get("min_requirements_coverage", 70))
        min_artifact_mapping_coverage = float(config.get("min_artifact_mapping_coverage", 70))
        max_contract_conflicts = int(config.get("max_contract_conflicts", 2))

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

            # --- DISCOVER .contextcore.yaml (needed for preflight + manifest) ---
            contextcore_yaml: Optional[Path] = None
            raw_yaml = config.get("contextcore_yaml")
            if raw_yaml is not None:
                contextcore_yaml = Path(str(raw_yaml)).expanduser()
                if not contextcore_yaml.is_absolute():
                    contextcore_yaml = (output_dir / contextcore_yaml).resolve()
            else:
                # Auto-discover: project_root (most specific), then output_dir.
                # Deliberately avoid Path.cwd() — it picks up unrelated
                # .contextcore.yaml files when the SDK is used from a
                # different working directory.
                candidates: list[Path] = [output_dir / ".contextcore.yaml"]
                project_root = config.get("project_root")
                if project_root:
                    candidates.insert(0, Path(project_root) / ".contextcore.yaml")
                for candidate in candidates:
                    if candidate.exists():
                        contextcore_yaml = candidate
                        break

            # --- PREFLIGHT ---
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

            # Write preflight report artifact regardless of pass/fail.
            preflight_passed = not preflight_errors
            preflight_report_path = self._write_preflight_report(
                output_dir, preflight_passed, preflight_evidence,
                preflight_warnings, preflight_errors,
            )
            logger.debug(
                "Preflight report written to %s (passed=%s)",
                preflight_report_path, preflight_passed,
            )

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
            if contextcore_yaml:
                try:
                    from contextcore.models import load_manifest
                    manifest = load_manifest(str(contextcore_yaml))
                    manifest_context = self._extract_manifest_context(manifest)
                    logger.debug(
                        "Loaded manifest from %s: %d context keys",
                        contextcore_yaml, len(manifest_context),
                    )
                except ImportError:
                    logger.debug("contextcore not installed — skipping manifest loading")
                except Exception as exc:
                    logger.warning("Failed to load manifest %s: %s", contextcore_yaml, exc)

            # --- PARSE ---
            progress("Parse")
            state.current_phase = IngestionPhase.PARSE
            assessor = self._resolve_assessor_agent(config)

            parsed_plan, parse_step = self._phase_parse(plan_text, assessor)
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
            transformer = self._resolve_transformer_agent(config)

            doc_path, transform_step = self._phase_transform(
                parsed_plan, route, transformer, output_dir,
            )
            steps.append(transform_step)
            state.total_cost += transform_step.cost
            step_costs["transform"] = transform_step.cost
            if transform_step.error:
                return _fail(transform_step.error)
            state.plan_document_path = str(doc_path)

            cost_err = _check_cost("transform")
            if cost_err:
                return cost_err

            # Enrich Prime YAML with requirement traceability (zero LLM cost).
            if route == ContractorRoute.PRIME and doc_path is not None:
                self._enrich_prime_yaml_with_traceability(
                    yaml_path=doc_path,
                    translation_quality=translation_quality,
                    requirement_hints=requirements_hints_index,
                    parsed_plan=parsed_plan,
                )

            # --- REFINE ---
            progress("Refine")
            state.current_phase = IngestionPhase.REFINE

            rounds_completed, refine_steps, refine_cost = self._phase_refine(
                doc_path,
                review_rounds,
                review_quality_tier,
                scope,
                context_files,
                list(requirements_docs.keys()) if requirements_docs else None,
                warn_cost_usd,
                max_cost_usd,
            )
            steps.extend(refine_steps)
            state.total_cost += refine_cost
            step_costs["refine"] = refine_cost

            # Re-evaluate translation quality after REFINE for traceability delta.
            refine_impact: Optional[Dict[str, Any]] = None
            if rounds_completed > 0:
                try:
                    refined_text = doc_path.read_text(encoding="utf-8")
                except OSError:
                    refined_text = ""
                if refined_text:
                    from dataclasses import replace as dc_replace

                    refined_plan = dc_replace(parsed_plan, raw_text=refined_text)
                    post_refine_quality = self._evaluate_translation_quality(
                        parsed_plan=refined_plan,
                        requirements_docs=requirements_docs,
                        onboarding=onboarding_metadata,
                        requirements_hints=requirements_hints_index,
                    )
                    refine_impact = {
                        "rounds_applied": rounds_completed,
                        "requirements_coverage_before": translation_quality.get(
                            "requirements_coverage_percent", 100.0
                        ),
                        "requirements_coverage_after": post_refine_quality.get(
                            "requirements_coverage_percent", 100.0
                        ),
                        "artifact_mapping_before": translation_quality.get(
                            "artifact_mapping_percent", 100.0
                        ),
                        "artifact_mapping_after": post_refine_quality.get(
                            "artifact_mapping_percent", 100.0
                        ),
                    }
                    # Use post-refine quality for downstream traceability.
                    translation_quality = post_refine_quality
                    logger.info(
                        "Post-REFINE quality: req_coverage %.1f%% -> %.1f%%, "
                        "artifact_mapping %.1f%% -> %.1f%%",
                        refine_impact["requirements_coverage_before"],
                        refine_impact["requirements_coverage_after"],
                        refine_impact["artifact_mapping_before"],
                        refine_impact["artifact_mapping_after"],
                    )

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
            )
            trace_payload = self._build_traceability_artifact(
                route=route,
                parsed_plan=parsed_plan,
                tasks=trace_tasks,
                quality=translation_quality,
                checksum_evidence=preflight_evidence.get("checksums", {}),
                refine_impact=refine_impact,
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
                "preflight_report_path": str(preflight_report_path),
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
