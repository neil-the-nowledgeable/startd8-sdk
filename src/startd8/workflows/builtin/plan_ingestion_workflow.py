"""
PlanIngestionWorkflow — Parse a generic plan, assess complexity,
transform into SDK-native format, refine via architectural review,
and emit the plan doc + review-config.json.

Pipeline:  parse → assess → transform → refine → emit
"""

from __future__ import annotations

import json
import logging
import re
import time
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

logger = logging.getLogger(__name__)


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
      "labels": ["label"]
    }}
  ],
  "mentioned_files": ["every file path mentioned in the plan"],
  "dependency_graph": {{"F-001": ["F-002"]}}
}}

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

        feature_summary = "\n".join(
            f"  - {f.feature_id}: {f.name} (files: {len(f.target_files)}, deps: {len(f.dependencies)})"
            for f in parsed_plan.features
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
                logger.info(
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
    # Phase: REFINE
    # ------------------------------------------------------------------

    def _phase_refine(
        self,
        doc_path: Path,
        review_rounds: int,
        review_quality_tier: str,
        scope: Optional[str],
        context_files: Optional[List[str]],
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
    ) -> List[Dict[str, Any]]:
        """Convert ParsedFeatures into task dicts matching prime-route schema."""
        # Build a mapping from feature_id to task_id
        fid_to_tid: Dict[str, str] = {}
        for idx, feat in enumerate(features, start=1):
            fid_to_tid[feat.feature_id] = f"PI-{idx:03d}"

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
                    "context": {
                        "feature_id": feat.feature_id,
                        "target_files": list(feat.target_files),
                        "estimated_loc": feat.estimated_loc,
                    },
                },
            })

        return tasks

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
                ctx["objectives"] = [
                    {
                        # v2 ObjectiveV2 has .description, v1 has .name
                        "name": getattr(obj, "description", None)
                        or getattr(obj, "name", str(obj)),
                        # Convert KeyResult models to dicts for JSON serialization
                        "key_results": [
                            kr.model_dump() if hasattr(kr, "model_dump") else kr.dict()
                            if hasattr(kr, "dict") else kr
                            for kr in getattr(obj, "key_results", [])
                        ],
                    }
                    for obj in objectives
                ]

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
                ctx["preferences"] = [
                    # v2 Preference has .description, v1 has .preference
                    getattr(p, "description", None)
                    or getattr(p, "preference", str(p))
                    for p in preferences
                ]
            focus = getattr(guidance, "focus", None)
            if focus:
                areas = getattr(focus, "areas", [])
                if areas:
                    ctx["focus_areas"] = list(areas)

        return ctx

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

            calibration[task["task_id"]] = {
                "depth_tier": tier_name,
                "sections": tier["sections"],
                "max_output_tokens": tier["max_tokens"],
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

            tasks = self._derive_tasks_from_features(
                parsed_plan.features,
                parsed_plan.dependency_graph,
            )

            # Derive architectural context + design calibration
            m_ctx = manifest_context or {}
            architectural_context = self._derive_architectural_context(
                parsed_plan, m_ctx,
            )
            design_calibration = self._derive_design_calibration(tasks)

            seed = ArtisanContextSeed(
                generated_at=datetime.now(timezone.utc).isoformat(),
                plan=parsed_plan.to_seed_dict(),
                complexity=complexity.to_seed_dict(),
                tasks=tasks,
                artifacts={
                    "plan_document_path": str(doc_path),
                    "review_config_path": str(config_path),
                },
                ingestion_metrics={
                    **{f"{k}_cost": v for k, v in costs.items()},
                    "total_cost": total_cost,
                },
                architectural_context=architectural_context,
                design_calibration=design_calibration,
            )

            context_seed_path = output_dir / "artisan-context-seed.json"
            atomic_write_json(context_seed_path, seed.to_dict(), indent=2)

        # Task tracking artifact generation (opt-in)
        tracking_result = None
        if tracking_config is not None and parsed_plan is not None:
            from .task_tracking_emitter import emit_task_tracking_artifacts

            tracking_tasks = self._derive_tasks_from_features(
                parsed_plan.features, parsed_plan.dependency_graph,
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
        scope = config.get("scope")
        warn_cost_usd = config.get("warn_cost_usd")
        max_cost_usd = config.get("max_cost_usd")
        context_files = _parse_context_files(config.get("context_files"))

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

        total_steps = 5  # parse, assess, transform, refine, emit
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

            # --- MANIFEST LOADING (optional) ---
            manifest_context: Dict[str, Any] = {}
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
                    logger.info(
                        "Loaded manifest from %s: %d context keys",
                        contextcore_yaml, len(manifest_context),
                    )
                except ImportError:
                    logger.debug("contextcore not installed — skipping manifest loading")
                except Exception as exc:
                    logger.warning("Failed to load manifest %s: %s", contextcore_yaml, exc)

            # --- PARSE ---
            progress("Parsing plan")
            state.current_phase = IngestionPhase.PARSE
            assessor = self._resolve_assessor_agent(config)

            parsed_plan, parse_step = self._phase_parse(plan_text, assessor)
            steps.append(parse_step)
            state.total_cost += parse_step.cost
            step_costs["parse"] = parse_step.cost
            if parse_step.error:
                return _fail(parse_step.error)
            state.parsed_plan = parsed_plan
            logger.info(
                "Parsed plan: '%s' with %d features",
                parsed_plan.title, len(parsed_plan.features),
            )

            cost_err = _check_cost("parse")
            if cost_err:
                return cost_err

            # --- ASSESS ---
            progress("Assessing complexity")
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
            logger.info(
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
            progress("Transforming plan")
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

            # --- REFINE ---
            progress("Refining via architectural review")
            state.current_phase = IngestionPhase.REFINE

            rounds_completed, refine_steps, refine_cost = self._phase_refine(
                doc_path,
                review_rounds,
                review_quality_tier,
                scope,
                context_files,
                warn_cost_usd,
                max_cost_usd,
            )
            steps.extend(refine_steps)
            state.total_cost += refine_cost
            step_costs["refine"] = refine_cost

            cost_err = _check_cost("refine")
            if cost_err:
                return cost_err

            # --- EMIT ---
            progress("Emitting review config")
            state.current_phase = IngestionPhase.EMIT

            config_path, review_config_data, context_seed_path, tracking_result = self._phase_emit(
                doc_path, route, complexity, output_dir,
                review_rounds, review_quality_tier, scope, context_files,
                warn_cost_usd, max_cost_usd,
                parsed_plan=parsed_plan,
                step_costs=step_costs,
                tracking_config=tracking_config,
                manifest_context=manifest_context,
            )
            state.review_config_path = str(config_path)
            if context_seed_path is not None:
                state.context_seed_path = str(context_seed_path)

            emit_output = f"Wrote {config_path}"
            if context_seed_path is not None:
                emit_output += f", {context_seed_path}"
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
