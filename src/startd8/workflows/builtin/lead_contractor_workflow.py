"""
PrimaryContractorWorkflow - Cost-efficient multi-agent implementation pattern.

Claude acts as "primary contractor" (architect, spec writer, reviewer, integrator)
while cheaper models handle the actual drafting work.

Pattern:
1. Claude creates detailed implementation spec
2. Drafter (Gemini Flash, GPT-4.1-nano, etc.) implements from spec
3. Claude reviews implementation
4. If not approved, loop back to step 2 (max 3 iterations)
5. Claude integrates/finalizes

Cost Structure (January 2026):
Primary Contractors (Claude 4.5 family - recommended):
- Claude Sonnet 4.5: $3.00/$15.00 per 1M tokens (default, best for coding/agents)
- Claude Opus 4.5: $5.00/$25.00 per 1M tokens (most intelligent)
- Claude Haiku 4.5: $1.00/$5.00 per 1M tokens (fastest)

Drafters (cost-efficient options):
- Gemini 2.5 Flash Lite: $0.075/$0.30 per 1M tokens (default - best value)
- GPT-4.1-nano: $0.10/$0.40 per 1M tokens (ultra-fast)
- Gemini 3 Flash Preview: $0.10/$0.40 per 1M tokens (latest)
- GPT-4o-mini: $0.15/$0.60 per 1M tokens (legacy but reliable)
- Gemini 2.5 Flash: $0.15/$0.60 per 1M tokens (balanced)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import re

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
    WorkflowMetrics,
    StepResult,
    AgentCount,
    ValidationResult,
)
from ...agents import BaseAgent
from ...model_catalog import Models
from ...utils.agent_resolution import resolve_agent_spec
from ...utils.retry import RetryConfig
from ...utils.code_extraction import extract_code_from_response
from ...logging_config import get_logger
from ...costs.pricing import PricingService
from ...truncation_detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_IS_TRUNCATED,
    detect_truncation,
    get_expected_sections_for_code,
)
# REQ-IME-200: Delegate to implementation_engine modules
from ...implementation_engine import parsers as _ie_parsers
from ...implementation_engine import budget as _ie_budget
from ...implementation_engine import spec_builder as _ie_spec_builder
from ...implementation_engine import drafter as _ie_drafter
from ...implementation_engine import reviewer as _ie_reviewer
from ...implementation_engine.models import (
    ReviewResult as _IEReviewResult,
)

from .lead_contractor_models import (
    ImplementationSpec,
    DraftResult,
    ReviewResult,
    IntegrationResult,
    LeadContractorResult,
    WorkflowPhase,
    TestPlanJSON,
    TestCase,
)

logger = get_logger(__name__)


# ============================================================================
# Prompt Templates — loaded from YAML (REQ-PPE-001 / REQ-PPE-004)
# ============================================================================

from ...implementation_engine.prompts import get_template as _get_contractor_template

# Backward-compatible prompt constants — now loaded from consolidated
# contractor_prompts.yaml via the implementation_engine prompt loader.
SPEC_PROMPT_TEMPLATE = _get_contractor_template("spec")
DRAFT_PROMPT_TEMPLATE = _get_contractor_template("draft")
SINGLE_FILE_OUTPUT_FORMAT = _get_contractor_template("single_file_output")
MULTI_FILE_OUTPUT_FORMAT = _get_contractor_template("multi_file_output")
REVIEW_PROMPT_TEMPLATE = _get_contractor_template("review")
INTEGRATION_PROMPT_TEMPLATE = _get_contractor_template("integration")
SINGLE_FILE_EDIT_OUTPUT_FORMAT = _get_contractor_template("single_file_edit_output")
MULTI_FILE_EDIT_OUTPUT_FORMAT = _get_contractor_template("multi_file_edit_output")
DRAFT_EDIT_PROMPT_TEMPLATE = _get_contractor_template("draft_edit")

def _format_lead_prompt(template_name: str, fallback: str, **kwargs: Any) -> str:
    """Format prompt from consolidated YAML; use fallback when unavailable.

    Args:
        template_name: Key in contractor_prompts.yaml prompts section.
        fallback: String to use when template unavailable.
        **kwargs: Placeholders for template.format().

    Returns:
        Formatted string (from YAML or fallback).
    """
    try:
        template = _get_contractor_template(template_name)
        return template.format(**kwargs)
    except (FileNotFoundError, KeyError):
        try:
            return fallback.format(**kwargs)
        except KeyError:
            return fallback

# PC-Y2: Inline fallback for spec completeness warning (still used in _execute)
_SPEC_COMPLETENESS_WARNING_FALLBACK: str = (
    "\n## Spec Completeness Warning\n"
    "The following parameters from requirements are NOT mentioned in the spec.\n"
    "Ensure these are included in your implementation:\n"
    "{missing_lines}\n"
)


# NOTE: Draft system prompts, budget constants, truncation helpers, existing files
# section builder, and output format builder have been extracted to
# startd8.implementation_engine (budget, drafter, spec_builder modules).
# See REQ-IME-200 imports at the top of this file.
#
# Backward-compatible re-exports for existing tests and downstream callers:
_PLAN_CONTEXT_MAX_CHARS = _ie_budget.PLAN_CONTEXT_MAX_CHARS
_ARCH_CONTEXT_MAX_CHARS = _ie_budget.ARCH_CONTEXT_MAX_CHARS
_SPEC_CONTEXT_BUDGET_CHARS = _ie_budget.SPEC_CONTEXT_BUDGET_CHARS
_EXISTING_FILES_BUDGET_BYTES = _ie_budget.EXISTING_FILES_BUDGET_BYTES
_TRUNCATION_MARKER = _ie_budget.TRUNCATION_MARKER
_SEARCH_REPLACE_LINE_THRESHOLD = _ie_budget.SEARCH_REPLACE_LINE_THRESHOLD
_get_drafter_system_prompt = _ie_drafter.get_drafter_system_prompt
_build_existing_files_section = _ie_drafter.build_existing_files_section
_build_output_format = _ie_drafter.build_output_format
_truncate_with_marker = _ie_budget.truncate_with_marker
_truncate_arch_context = _ie_budget.truncate_arch_context
# Fallback strings re-exported for test assertions
_PLAN_CONTEXT_EDIT_FRAMING_FALLBACK = _ie_spec_builder._PLAN_CONTEXT_EDIT_FRAMING_FALLBACK
_PLAN_CONTEXT_CREATE_FRAMING_FALLBACK = _ie_spec_builder._PLAN_CONTEXT_CREATE_FRAMING_FALLBACK
_ARCH_CONTEXT_EDIT_FRAMING_FALLBACK = _ie_spec_builder._ARCH_CONTEXT_EDIT_FRAMING_FALLBACK


class PrimaryContractorWorkflow(WorkflowBase):
    """
    Primary Contractor workflow for cost-efficient multi-agent implementation.

    Uses Claude as the architect/reviewer while cheaper models draft code.

    Config Schema:
        {
            "task_description": "string - What to implement",
            "context": {...} - Optional additional context,
            "lead_agent": Models.LEAD_CONTRACTOR_LEAD - Primary contractor,
            "drafter_agent": Models.LEAD_CONTRACTOR_DRAFTER - Drafter agent (best value),
            "max_iterations": 3 - Max review cycles,
            "pass_threshold": 80 - Minimum score to pass (0-100),
            "output_format": "string - Expected output format (optional)",
            "integration_instructions": "string - Final integration notes (optional)",
            "check_truncation": true - Enable truncation detection (default: true),
            "fail_on_api_truncation": true - Fail on API truncation (default: true),
            "fail_on_heuristic_truncation": false - Fail on heuristic truncation (default: false),
            "fail_on_truncation": true - Legacy flag, controls both (backward compat),
            "strict_truncation": false - Use strict detection threshold (default: false)
        }

    Truncation Protection:
        The workflow detects two types of truncation:

        1. **API truncation**: Model hit max_tokens (finish_reason="max_tokens").
           Default: fail (fail_on_api_truncation=True).
        2. **Heuristic truncation**: Output appears structurally incomplete.
           Default: warn (fail_on_heuristic_truncation=False).

        Config keys:
        - check_truncation (default: True): Enable/disable heuristic detection
        - fail_on_api_truncation (default: True): Fail on API truncation
        - fail_on_heuristic_truncation (default: False): Fail on heuristic truncation
        - fail_on_truncation: Legacy flag — controls both (backward compat)
        - strict_truncation (default: False): Lower confidence threshold for heuristics

        Recommended settings by use case:
        - Code generation: fail_on_api_truncation=True, fail_on_heuristic_truncation=True
        - Config/data generation: fail_on_api_truncation=True, fail_on_heuristic_truncation=False
        - Exploratory: fail_on_api_truncation=False, fail_on_heuristic_truncation=False

    Recommended Lead Agents:
        - anthropic:claude-sonnet-4-6 (default - best for coding/agents)
        - anthropic:claude-opus-4-6 (most intelligent)
        - anthropic:claude-haiku-4-5-20251001 (fastest, near-frontier)

    Recommended Drafter Agents:
        - anthropic:claude-haiku-4-5-20251001 (default - fast, low-cost)
        - openai:gpt-4.1-nano ($0.10/$0.40 - ultra-fast)
        - gemini:gemini-3-flash-preview ($0.10/$0.40 - latest)
        - openai:gpt-4o-mini ($0.15/$0.60 - reliable)

    Example:
        result = workflow.run(
            config={
                "task_description": "Implement a rate limiter using token bucket algorithm",
                "context": {"language": "Python", "framework": "FastAPI"},
                "drafter_agent": "openai:gpt-4.1-nano",
                "max_iterations": 3
            }
        )
    """

    def __init__(self):
        self._pricing = PricingService()

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="lead-contractor",
            name="Primary Contractor Workflow",  # alias: "Lead Contractor Workflow"
            description="Cost-efficient multi-agent pattern: Claude specs/reviews, cheaper models draft",
            version="1.0.0",
            capabilities=[
                "cost-optimization",
                "multi-agent",
                "iterative-development",
                "code-generation",
                "spec-driven"
            ],
            tags=["development", "cost-efficient", "multi-agent", "iterative"],
            requires_agents=False,  # We resolve agents from specs
            agent_count=AgentCount.NONE,  # Config specifies agents
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="task_description",
                    type="text",
                    required=True,
                    description="Description of what needs to be implemented"
                ),
                WorkflowInput(
                    name="context",
                    type="object",
                    required=False,
                    description="Additional context (existing code, requirements, constraints)"
                ),
                WorkflowInput(
                    name="lead_agent",
                    type="agent_spec",
                    required=False,
                    default=Models.LEAD_CONTRACTOR_LEAD,
                    description="Lead contractor agent (Claude recommended: sonnet-4.6, opus-4.6, haiku-4.5)"
                ),
                WorkflowInput(
                    name="drafter_agent",
                    type="agent_spec",
                    required=False,
                    default=Models.LEAD_CONTRACTOR_DRAFTER,
                    description="Drafter agent (cost-efficient: haiku-4.5, gpt-4.1-nano)"
                ),
                WorkflowInput(
                    name="max_iterations",
                    type="number",
                    required=False,
                    default=3,
                    description="Maximum draft/review iterations"
                ),
                WorkflowInput(
                    name="pass_threshold",
                    type="number",
                    required=False,
                    default=80,
                    description="Minimum review score to pass (0-100)"
                ),
                WorkflowInput(
                    name="output_format",
                    type="text",
                    required=False,
                    description="Expected output format guidance for drafter"
                ),
                WorkflowInput(
                    name="integration_instructions",
                    type="text",
                    required=False,
                    description="Instructions for final integration step"
                ),
                WorkflowInput(
                    name="check_truncation",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Enable truncation detection on drafter output (default: True)"
                ),
                WorkflowInput(
                    name="fail_on_api_truncation",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Fail workflow if API truncation detected (finish_reason=max_tokens). Default: True."
                ),
                WorkflowInput(
                    name="fail_on_heuristic_truncation",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Fail workflow if heuristic truncation detected (incomplete code structure). Default: False."
                ),
                WorkflowInput(
                    name="fail_on_truncation",
                    type="boolean",
                    required=False,
                    default=None,
                    description="Legacy flag: controls both API and heuristic truncation failure. Granular flags take precedence."
                ),
                WorkflowInput(
                    name="strict_truncation",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Use strict truncation detection with lower confidence threshold (default: False)"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate lead contractor configuration."""
        errors = []

        # Required: task_description
        if "task_description" not in config:
            errors.append("Missing required input: task_description")
        elif not config["task_description"].strip():
            errors.append("task_description cannot be empty")

        # Validate max_iterations
        max_iter = config.get("max_iterations", 3)
        if not isinstance(max_iter, int) or max_iter < 1 or max_iter > 10:
            errors.append("max_iterations must be an integer between 1 and 10")

        # Validate pass_threshold
        threshold = config.get("pass_threshold", 80)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 100:
            errors.append("pass_threshold must be a number between 0 and 100")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute the Primary Contractor workflow synchronously."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"lc-{uuid.uuid4().hex[:12]}"

        # Parse configuration
        task_description = config["task_description"]
        context = dict(config.get("context", {}))
        lead_spec = config.get("lead_agent", Models.LEAD_CONTRACTOR_LEAD)
        drafter_spec = config.get("drafter_agent", Models.LEAD_CONTRACTOR_DRAFTER)
        max_iterations = config.get("max_iterations", 3)
        pass_threshold = config.get("pass_threshold", 80)
        output_format = config.get("output_format")
        integration_instructions = config.get("integration_instructions", "")
        # Truncation protection defaults - safe by default
        check_truncation = config.get("check_truncation", True)
        strict_truncation = config.get("strict_truncation", False)

        # Granular truncation failure control
        # Legacy flag for backward compatibility
        legacy_fail_on_truncation = config.get("fail_on_truncation")
        if legacy_fail_on_truncation is not None:
            # Legacy mode: single flag controls both, but granular flags take precedence
            fail_on_api_truncation = config.get("fail_on_api_truncation", legacy_fail_on_truncation)
            fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", legacy_fail_on_truncation)
        else:
            # New mode: separate control (safe defaults)
            fail_on_api_truncation = config.get("fail_on_api_truncation", True)
            fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", False)

        # Extract ContextCore project context
        project_context = self._extract_project_context(config)

        # Resolve agents (forward max_tokens and retry config)
        agent_max_tokens = config.get("max_tokens")
        resolve_kwargs: Dict[str, Any] = {}
        if agent_max_tokens:
            resolve_kwargs["max_tokens"] = agent_max_tokens
        # Enable retry by default for transient API errors (429, 529, 5xx)
        resolve_kwargs["retry_config"] = config.get(
            "retry_config",
            RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=60.0,
                retryable_status_codes=(429, 500, 502, 503, 504, 529),
            ),
        )
        try:
            lead_agent = resolve_agent_spec(lead_spec, **resolve_kwargs)
            drafter_agent = resolve_agent_spec(drafter_spec, **resolve_kwargs)
        except Exception as e:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Failed to resolve agents: {e}"
            )

        # Initialize result tracking
        result = LeadContractorResult(
            workflow_id=workflow_id,
            success=False,
            final_implementation=""
        )

        step_results: List[StepResult] = []
        total_steps = 2 + max_iterations * 2 + 1  # spec + (draft+review)*N + integration
        current_step = 0

        self._emit_progress(on_progress, current_step, total_steps, "Starting Primary Contractor workflow")

        try:
            # =================================================================
            # Phase 1: Spec Creation (Lead)
            # =================================================================
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, "Creating implementation spec")

            spec = self._create_spec(
                lead_agent=lead_agent,
                task_description=task_description,
                context=context,
                output_format=output_format,
            )
            result.spec = spec

            step_results.append(StepResult(
                step_name="spec_creation",
                agent_name=f"{lead_agent.name}:{lead_agent.model}",
                output=spec.raw_spec[:500] + "..." if len(spec.raw_spec) > 500 else spec.raw_spec,
                time_ms=spec.time_ms,
                input_tokens=spec.input_tokens,
                output_tokens=spec.output_tokens,
                cost=spec.cost,
                metadata={"phase": WorkflowPhase.SPEC_CREATION.value}
            ))

            result.lead_input_tokens += spec.input_tokens
            result.lead_output_tokens += spec.output_tokens
            result.lead_cost += spec.cost

            # =================================================================
            # IMP-P6: Spec-to-draft validation — check for missing parameters
            # REQ-PEM-008: Mode-conditional — skipped when _run_validators=False
            # =================================================================
            spec_validation_warning = ""
            run_validators = context.get("_run_validators", True)
            resolved_params = context.get("resolved_parameters", [])
            if run_validators and resolved_params:
                from ...contractors.prompt_utils import find_missing_parameters
                missing = find_missing_parameters(spec.raw_spec, resolved_params)
                if missing:
                    missing_lines = "\n".join(
                        f"- {p.get('key_value', '')} (from requirements)"
                        for p in missing
                    )
                    spec_validation_warning = "\n" + _format_lead_prompt(
                        "spec_completeness_warning",
                        _SPEC_COMPLETENESS_WARNING_FALLBACK,
                        missing_lines=missing_lines,
                    ) + "\n"
                    logger.warning(
                        "IMP-P6: %d resolved parameter(s) missing from spec: %s",
                        len(missing),
                        [p.get("key_value") for p in missing],
                    )

            # =================================================================
            # Phase 2-4: Draft/Review Loop
            # =================================================================
            current_implementation = ""
            review_feedback = context.get("_multi_file_retry_initial_feedback", "")
            if spec_validation_warning and not review_feedback:
                review_feedback = spec_validation_warning

            for iteration in range(1, max_iterations + 1):
                # Draft phase
                current_step += 1
                self._emit_progress(
                    on_progress, current_step, total_steps,
                    f"Drafting implementation (iteration {iteration}/{max_iterations})"
                )

                draft = self._create_draft(
                    drafter_agent=drafter_agent,
                    spec=spec,
                    feedback=review_feedback,
                    iteration=iteration,
                    check_truncation=check_truncation,
                    strict_truncation=strict_truncation,
                    target_files=context.get("target_files"),
                    existing_files=context.get("existing_files"),
                    edit_mode=context.get("edit_mode"),
                )
                result.drafts.append(draft)
                current_implementation = draft.implementation

                step_results.append(StepResult(
                    step_name=f"draft_iteration_{iteration}",
                    agent_name=f"{drafter_agent.name}:{drafter_agent.model}",
                    output=draft.implementation[:500] + "..." if len(draft.implementation) > 500 else draft.implementation,
                    time_ms=draft.time_ms,
                    input_tokens=draft.input_tokens,
                    output_tokens=draft.output_tokens,
                    cost=draft.cost,
                    metadata={"phase": WorkflowPhase.DRAFTING.value, "iteration": iteration}
                ))

                result.drafter_input_tokens += draft.input_tokens
                result.drafter_output_tokens += draft.output_tokens
                result.drafter_cost += draft.cost

                # Check for truncation
                if check_truncation and draft.was_truncated:
                    is_api = draft.truncation_source == "api"
                    should_fail = (
                        (is_api and fail_on_api_truncation)
                        or (not is_api and fail_on_heuristic_truncation)
                    )

                    if should_fail and iteration < max_iterations:
                        # Auto-retry: skip review, re-draft with continuation prompt
                        logger.warning(
                            f"Draft truncated at iteration {iteration} "
                            f"(source: {draft.truncation_source}, "
                            f"{draft.output_tokens} tokens). Retrying with continuation prompt."
                        )
                        review_feedback = (
                            "Your previous response was TRUNCATED — it was cut off before "
                            "the code was complete. You MUST output the COMPLETE file in a "
                            "single response. Do not add commentary — output ONLY the full "
                            "source code for the file."
                        )
                        continue
                    elif should_fail:
                        error_msg = (
                            f"Draft was truncated at iteration {iteration} "
                            f"(source: {draft.truncation_source}). "
                            f"Output tokens: {draft.output_tokens}. "
                        )
                        if is_api:
                            error_msg += (
                                "Consider: (1) increasing max_tokens, (2) decomposing the task, "
                                "or (3) setting fail_on_api_truncation=False to continue anyway."
                            )
                        else:
                            error_msg += (
                                "Heuristic detection flagged incomplete code structure. "
                                "Consider setting fail_on_heuristic_truncation=False if this is a false positive."
                            )
                        logger.error(error_msg)
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            error_msg,
                            steps=step_results,
                        )
                    else:
                        logger.warning(
                            f"Draft truncation detected at iteration {iteration} "
                            f"(source: {draft.truncation_source}), continuing anyway."
                        )

                # Review phase
                current_step += 1
                self._emit_progress(
                    on_progress, current_step, total_steps,
                    f"Reviewing implementation (iteration {iteration}/{max_iterations})"
                )

                review = self._review_draft(
                    lead_agent=lead_agent,
                    task_description=task_description,
                    spec=spec,
                    implementation=current_implementation,
                    pass_threshold=pass_threshold,
                    iteration=iteration,
                    forward_manifest=context.get("forward_manifest"),
                    target_files=context.get("target_files"),
                )
                result.reviews.append(review)

                step_results.append(StepResult(
                    step_name=f"review_iteration_{iteration}",
                    agent_name=f"{lead_agent.name}:{lead_agent.model}",
                    output=review.review_text[:500] + "..." if len(review.review_text) > 500 else review.review_text,
                    time_ms=review.time_ms,
                    input_tokens=review.input_tokens,
                    output_tokens=review.output_tokens,
                    cost=review.cost,
                    metadata={
                        "phase": WorkflowPhase.REVIEW.value,
                        "iteration": iteration,
                        "score": review.score,
                        "passed": review.passed
                    }
                ))

                result.lead_input_tokens += review.input_tokens
                result.lead_output_tokens += review.output_tokens
                result.lead_cost += review.cost

                # Check if passed
                if review.passed:
                    logger.info(f"Review passed on iteration {iteration} with score {review.score}")
                    break

                # Prepare feedback for next iteration
                review_feedback = self._format_review_feedback(review)

                if iteration == max_iterations:
                    logger.warning(f"Max iterations ({max_iterations}) reached without passing review")

            result.total_iterations = len(result.drafts)

            # =================================================================
            # Phase 5: Integration (Lead)
            # =================================================================
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, "Integrating final implementation")

            integration = self._integrate_final(
                lead_agent=lead_agent,
                task_description=task_description,
                implementation=current_implementation,
                reviews=result.reviews,
                integration_instructions=integration_instructions,
                target_files=context.get("target_files"),
                existing_files=context.get("existing_files"),
            )
            result.integration = integration

            step_results.append(StepResult(
                step_name="integration",
                agent_name=f"{lead_agent.name}:{lead_agent.model}",
                output=integration.final_implementation[:500] + "..." if len(integration.final_implementation) > 500 else integration.final_implementation,
                time_ms=integration.time_ms,
                input_tokens=integration.input_tokens,
                output_tokens=integration.output_tokens,
                cost=integration.cost,
                metadata={"phase": WorkflowPhase.INTEGRATION.value}
            ))

            result.lead_input_tokens += integration.input_tokens
            result.lead_output_tokens += integration.output_tokens
            result.lead_cost += integration.cost

            # Finalize result
            result.success = True
            result.final_implementation = integration.final_implementation
            result.final_phase = WorkflowPhase.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
            result.total_cost = result.lead_cost + result.drafter_cost
            result.total_time_ms = sum(s.time_ms for s in step_results)

        except Exception as e:
            logger.error(f"Primary Contractor workflow failed: {e}", exc_info=True)
            result.success = False
            result.error = str(e)
            result.final_phase = WorkflowPhase.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.total_cost = result.lead_cost + result.drafter_cost
            result.total_time_ms = sum(s.time_ms for s in step_results)

        # Build workflow metrics
        metrics = WorkflowMetrics(
            total_time_ms=result.total_time_ms,
            input_tokens=result.lead_input_tokens + result.drafter_input_tokens,
            output_tokens=result.lead_output_tokens + result.drafter_output_tokens,
            total_cost=result.total_cost,
            step_count=len(step_results),
            model=lead_spec,
        )

        completed_at = datetime.now(timezone.utc)

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=result.success,
            output={
                "final_implementation": result.final_implementation,
                "summary": result.to_summary(),
                # PCA-607: Raw drafter response for multi-file extraction
                "last_draft_raw_response": result.drafts[-1].raw_response if result.drafts else "",
            },
            metrics=metrics,
            steps=step_results,
            error=result.error,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "lead_contractor_result": result.to_summary(),
                "lead_agent": lead_spec,
                "drafter_agent": drafter_spec,
                "total_iterations": result.total_iterations,
                "lead_cost": result.lead_cost,
                "drafter_cost": result.drafter_cost,
                "cost_efficiency_ratio": result.get_cost_efficiency_ratio(),
            },
            project_context=project_context if not project_context.is_empty() else None,
        )

    # =========================================================================
    # Private Methods - Phase Implementations
    # =========================================================================

    @staticmethod
    def _build_spec_prompt(
        task_description: str,
        context: Dict[str, Any],
        output_format: Optional[str],
    ) -> str:
        """Build the spec prompt. Delegates to implementation_engine.spec_builder."""
        edit_min_pct = context.pop("edit_min_pct", 80)
        return _ie_spec_builder.build_spec_prompt(
            task_description, context, output_format,
            edit_min_pct=edit_min_pct,
        )

    def _create_spec(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        context: Dict[str, Any],
        output_format: Optional[str],
    ) -> ImplementationSpec:
        """Phase 1: Lead creates implementation specification.

        Delegates to implementation_engine.spec_builder.build_spec() and
        converts the result to ImplementationSpec for backward compatibility.
        """
        ie_spec = _ie_spec_builder.build_spec(
            agent=lead_agent,
            task_description=task_description,
            context=context,
            output_format=output_format,
        )
        return ie_spec.to_implementation_spec()

    def _create_draft(
        self,
        drafter_agent: BaseAgent,
        spec: ImplementationSpec,
        feedback: str,
        iteration: int,
        check_truncation: bool = True,
        strict_truncation: bool = False,
        target_files: Optional[List[str]] = None,
        existing_files: Optional[Dict[str, str]] = None,
        edit_mode: Optional[Dict] = None,
    ) -> DraftResult:
        """Phase 2/4: Drafter creates implementation from spec.

        Delegates to implementation_engine.drafter.create_draft() and
        converts the result to DraftResult for backward compatibility.
        """
        ie_draft = _ie_drafter.create_draft(
            agent=drafter_agent,
            spec=spec,
            feedback=feedback,
            iteration=iteration,
            check_truncation=check_truncation,
            strict_truncation=strict_truncation,
            target_files=target_files,
            existing_files=existing_files,
            edit_mode=edit_mode,
        )
        return DraftResult(
            draft_id=ie_draft.draft_id,
            iteration=ie_draft.iteration,
            implementation=ie_draft.implementation,
            spec_id=ie_draft.spec_id,
            agent_name=ie_draft.agent_name,
            model=ie_draft.model,
            input_tokens=ie_draft.input_tokens,
            output_tokens=ie_draft.output_tokens,
            cost=ie_draft.cost,
            time_ms=ie_draft.time_ms,
            was_truncated=ie_draft.was_truncated,
            truncation_source=ie_draft.truncation_source,
            raw_response=ie_draft.raw_response,
        )

    def _review_draft(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        spec: ImplementationSpec,
        implementation: str,
        pass_threshold: int,
        iteration: int,
        forward_manifest: Optional[Any] = None,
        target_files: Optional[List[str]] = None,
    ) -> ReviewResult:
        """Phase 3: Lead reviews the draft implementation.

        Delegates core review to implementation_engine.reviewer.review_draft().
        Forward manifest validation (Prime-specific) remains here.
        """
        ie_review = _ie_reviewer.review_draft(
            agent=lead_agent,
            task_description=task_description,
            spec=spec,
            implementation=implementation,
            pass_threshold=pass_threshold,
            iteration=iteration,
        )

        # Convert to lead_contractor_models.ReviewResult
        passed = ie_review.passed
        blocking = list(ie_review.blocking_issues)

        # REQ-PC-VAL-003: Validator Hook during Review (Prime-specific)
        if forward_manifest and getattr(forward_manifest, "contracts", None):
            try:
                from startd8.forward_manifest_validator import validate_forward_manifest
                from startd8.utils.manifest_registry import ManifestRegistry
                from startd8.utils.code_extraction import extract_multi_file_code

                t_files = target_files or ["generated_code.py"]
                per_file_code = extract_multi_file_code(implementation, t_files)

                if not per_file_code and len(t_files) == 1:
                    per_file_code[t_files[0]] = implementation

                from pathlib import Path
                from startd8.utils.code_manifest import generate_file_manifest

                manifest_dict = {}
                for rel_path, src in per_file_code.items():
                    try:
                        manifest = generate_file_manifest(
                            file_path=rel_path, source=src, project_root=Path(".")
                        )
                        manifest_dict[rel_path] = manifest
                    except Exception as exc:
                        logger.warning(
                            "Failed to parse dynamically generated file '%s' "
                            "during review validation: %s",
                            rel_path, exc
                        )
                registry = ManifestRegistry(manifests=manifest_dict)
                violations = validate_forward_manifest(forward_manifest, registry)
                error_violations = [v for v in violations if v.severity == "error"]

                if error_violations:
                    passed = False
                    for violation in error_violations:
                        msg = (
                            f"[BLOCKING] {violation.violation_type} violation "
                            f"({violation.contract_id}): Expected {violation.expected}"
                        )
                        if violation.actual:
                            msg += f", but got {violation.actual}"
                        if violation.file_path:
                            msg += f" (in {violation.file_path})"
                        if msg not in blocking:
                            blocking.append(msg)
                    logger.warning(
                        "Lead review validation gate FAILED: %d structural error(s) detected.",
                        len(error_violations)
                    )
            except Exception as exc:
                logger.error(
                    "Failed to run validate_forward_manifest during lead review: %s",
                    exc, exc_info=True,
                )

        review = ReviewResult(
            review_id=ie_review.review_id,
            iteration=ie_review.iteration,
            passed=passed,
            score=ie_review.score,
            review_text=ie_review.review_text,
            issues=list(ie_review.issues),
            blocking_issues=blocking,
            suggestions=list(ie_review.suggestions),
            strengths=list(ie_review.strengths),
            input_tokens=ie_review.input_tokens,
            output_tokens=ie_review.output_tokens,
            cost=ie_review.cost,
            time_ms=ie_review.time_ms,
        )

        return review

    def _integrate_final(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        implementation: str,
        reviews: List[ReviewResult],
        integration_instructions: str,
        target_files: Optional[List[str]] = None,
        existing_files: Optional[Dict[str, str]] = None,
    ) -> IntegrationResult:
        """Phase 5: Lead integrates and finalizes the implementation."""
        integration_id = f"int-{uuid.uuid4().hex[:8]}"

        review_history = "\n\n".join([
            f"### Iteration {r.iteration}\n- Score: {r.score}\n- Passed: {r.passed}\n{r.review_text[:500]}"
            for r in reviews
        ])

        # PCA-607: Build multi-file directive for integration context
        multi_file_directive = self._build_multi_file_directive(
            target_files, existing_files,
        )

        prompt = INTEGRATION_PROMPT_TEMPLATE.format(
            task_description=task_description,
            implementation=implementation,
            review_history=review_history,
            integration_instructions=integration_instructions or "Finalize for production use.",
            multi_file_directive=multi_file_directive,
        )

        response_text, response_time_ms, token_usage = lead_agent.generate(prompt)

        # Extract code from markdown code blocks (removes LLM commentary/notes)
        final_code = self._extract_code_from_response(response_text)

        integration = IntegrationResult(
            integration_id=integration_id,
            final_implementation=final_code,
            input_tokens=token_usage.input if token_usage else 0,
            output_tokens=token_usage.output if token_usage else 0,
            time_ms=response_time_ms,
        )

        integration.cost = self._pricing.calculate_total_cost(
            lead_agent.model,
            integration.input_tokens,
            integration.output_tokens
        )

        return integration

    # =========================================================================
    # Async Execution (FR-150)
    # =========================================================================

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute the Primary Contractor workflow asynchronously (FR-150)."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"lc-{uuid.uuid4().hex[:12]}"

        task_description = config["task_description"]
        context = dict(config.get("context", {}))
        lead_spec = config.get("lead_agent", Models.LEAD_CONTRACTOR_LEAD)
        drafter_spec = config.get("drafter_agent", Models.LEAD_CONTRACTOR_DRAFTER)
        max_iterations = config.get("max_iterations", 3)
        pass_threshold = config.get("pass_threshold", 80)
        output_format = config.get("output_format")
        integration_instructions = config.get("integration_instructions", "")
        # Truncation protection defaults - safe by default
        check_truncation = config.get("check_truncation", True)
        strict_truncation = config.get("strict_truncation", False)

        # Granular truncation failure control
        legacy_fail_on_truncation = config.get("fail_on_truncation")
        if legacy_fail_on_truncation is not None:
            fail_on_api_truncation = config.get("fail_on_api_truncation", legacy_fail_on_truncation)
            fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", legacy_fail_on_truncation)
        else:
            fail_on_api_truncation = config.get("fail_on_api_truncation", True)
            fail_on_heuristic_truncation = config.get("fail_on_heuristic_truncation", False)

        project_context = self._extract_project_context(config)

        # Resolve agents (forward max_tokens and retry config)
        agent_max_tokens = config.get("max_tokens")
        resolve_kwargs: Dict[str, Any] = {}
        if agent_max_tokens:
            resolve_kwargs["max_tokens"] = agent_max_tokens
        # Enable retry by default for transient API errors (429, 529, 5xx)
        resolve_kwargs["retry_config"] = config.get(
            "retry_config",
            RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=60.0,
                retryable_status_codes=(429, 500, 502, 503, 504, 529),
            ),
        )
        try:
            lead_agent = resolve_agent_spec(lead_spec, **resolve_kwargs)
            drafter_agent = resolve_agent_spec(drafter_spec, **resolve_kwargs)
        except Exception as e:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Failed to resolve agents: {e}"
            )

        result = LeadContractorResult(
            workflow_id=workflow_id,
            success=False,
            final_implementation=""
        )

        step_results: List[StepResult] = []
        total_steps = 2 + max_iterations * 2 + 1
        current_step = 0

        self._emit_progress(on_progress, current_step, total_steps, "Starting Primary Contractor workflow")

        try:
            # Phase 1: Spec Creation (Lead)
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, "Creating implementation spec")

            spec = await self._acreate_spec(
                lead_agent=lead_agent,
                task_description=task_description,
                context=context,
                output_format=output_format,
            )
            result.spec = spec

            step_results.append(StepResult(
                step_name="spec_creation",
                agent_name=f"{lead_agent.name}:{lead_agent.model}",
                output=spec.raw_spec[:500] + "..." if len(spec.raw_spec) > 500 else spec.raw_spec,
                time_ms=spec.time_ms,
                input_tokens=spec.input_tokens,
                output_tokens=spec.output_tokens,
                cost=spec.cost,
                metadata={"phase": WorkflowPhase.SPEC_CREATION.value}
            ))

            result.lead_input_tokens += spec.input_tokens
            result.lead_output_tokens += spec.output_tokens
            result.lead_cost += spec.cost

            # Phase 2-4: Draft/Review Loop
            current_implementation = ""
            review_feedback = ""

            for iteration in range(1, max_iterations + 1):
                current_step += 1
                self._emit_progress(
                    on_progress, current_step, total_steps,
                    f"Drafting implementation (iteration {iteration}/{max_iterations})"
                )

                draft = await self._acreate_draft(
                    drafter_agent=drafter_agent,
                    spec=spec,
                    feedback=review_feedback,
                    iteration=iteration,
                    check_truncation=check_truncation,
                    strict_truncation=strict_truncation,
                    target_files=context.get("target_files"),
                    existing_files=context.get("existing_files"),
                    edit_mode=context.get("edit_mode"),
                )
                result.drafts.append(draft)
                current_implementation = draft.implementation

                step_results.append(StepResult(
                    step_name=f"draft_iteration_{iteration}",
                    agent_name=f"{drafter_agent.name}:{drafter_agent.model}",
                    output=draft.implementation[:500] + "..." if len(draft.implementation) > 500 else draft.implementation,
                    time_ms=draft.time_ms,
                    input_tokens=draft.input_tokens,
                    output_tokens=draft.output_tokens,
                    cost=draft.cost,
                    metadata={"phase": WorkflowPhase.DRAFTING.value, "iteration": iteration}
                ))

                result.drafter_input_tokens += draft.input_tokens
                result.drafter_output_tokens += draft.output_tokens
                result.drafter_cost += draft.cost

                # Check for truncation
                if check_truncation and draft.was_truncated:
                    is_api = draft.truncation_source == "api"
                    should_fail = (
                        (is_api and fail_on_api_truncation)
                        or (not is_api and fail_on_heuristic_truncation)
                    )

                    if should_fail and iteration < max_iterations:
                        # Auto-retry: skip review, re-draft with continuation prompt
                        logger.warning(
                            f"Draft truncated at iteration {iteration} "
                            f"(source: {draft.truncation_source}, "
                            f"{draft.output_tokens} tokens). Retrying with continuation prompt."
                        )
                        review_feedback = (
                            "Your previous response was TRUNCATED — it was cut off before "
                            "the code was complete. You MUST output the COMPLETE file in a "
                            "single response. Do not add commentary — output ONLY the full "
                            "source code for the file."
                        )
                        continue
                    elif should_fail:
                        error_msg = (
                            f"Draft was truncated at iteration {iteration} "
                            f"(source: {draft.truncation_source}). "
                            f"Output tokens: {draft.output_tokens}. "
                        )
                        if is_api:
                            error_msg += (
                                "Consider: (1) increasing max_tokens, (2) decomposing the task, "
                                "or (3) setting fail_on_api_truncation=False to continue anyway."
                            )
                        else:
                            error_msg += (
                                "Heuristic detection flagged incomplete code structure. "
                                "Consider setting fail_on_heuristic_truncation=False if this is a false positive."
                            )
                        logger.error(error_msg)
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            error_msg,
                            steps=step_results,
                        )
                    else:
                        logger.warning(
                            f"Draft truncation detected at iteration {iteration} "
                            f"(source: {draft.truncation_source}), continuing anyway."
                        )

                # Review phase
                current_step += 1
                self._emit_progress(
                    on_progress, current_step, total_steps,
                    f"Reviewing implementation (iteration {iteration}/{max_iterations})"
                )

                review = await self._areview_draft(
                    lead_agent=lead_agent,
                    task_description=task_description,
                    spec=spec,
                    implementation=current_implementation,
                    pass_threshold=pass_threshold,
                    iteration=iteration,
                )
                result.reviews.append(review)

                step_results.append(StepResult(
                    step_name=f"review_iteration_{iteration}",
                    agent_name=f"{lead_agent.name}:{lead_agent.model}",
                    output=review.review_text[:500] + "..." if len(review.review_text) > 500 else review.review_text,
                    time_ms=review.time_ms,
                    input_tokens=review.input_tokens,
                    output_tokens=review.output_tokens,
                    cost=review.cost,
                    metadata={
                        "phase": WorkflowPhase.REVIEW.value,
                        "iteration": iteration,
                        "score": review.score,
                        "passed": review.passed
                    }
                ))

                result.lead_input_tokens += review.input_tokens
                result.lead_output_tokens += review.output_tokens
                result.lead_cost += review.cost

                if review.passed:
                    logger.info(f"Review passed on iteration {iteration} with score {review.score}")
                    break

                review_feedback = self._format_review_feedback(review)

                if iteration == max_iterations:
                    logger.warning(f"Max iterations ({max_iterations}) reached without passing review")

            result.total_iterations = len(result.drafts)

            # Phase 5: Integration (Lead)
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, "Integrating final implementation")

            integration = await self._aintegrate_final(
                lead_agent=lead_agent,
                task_description=task_description,
                implementation=current_implementation,
                reviews=result.reviews,
                integration_instructions=integration_instructions,
                target_files=context.get("target_files"),
                existing_files=context.get("existing_files"),
            )
            result.integration = integration

            step_results.append(StepResult(
                step_name="integration",
                agent_name=f"{lead_agent.name}:{lead_agent.model}",
                output=integration.final_implementation[:500] + "..." if len(integration.final_implementation) > 500 else integration.final_implementation,
                time_ms=integration.time_ms,
                input_tokens=integration.input_tokens,
                output_tokens=integration.output_tokens,
                cost=integration.cost,
                metadata={"phase": WorkflowPhase.INTEGRATION.value}
            ))

            result.lead_input_tokens += integration.input_tokens
            result.lead_output_tokens += integration.output_tokens
            result.lead_cost += integration.cost

            result.success = True
            result.final_implementation = integration.final_implementation
            result.final_phase = WorkflowPhase.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
            result.total_cost = result.lead_cost + result.drafter_cost
            result.total_time_ms = sum(s.time_ms for s in step_results)

        except Exception as e:
            logger.error(f"Primary Contractor workflow failed: {e}", exc_info=True)
            result.success = False
            result.error = str(e)
            result.final_phase = WorkflowPhase.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.total_cost = result.lead_cost + result.drafter_cost
            result.total_time_ms = sum(s.time_ms for s in step_results)

        metrics = WorkflowMetrics(
            total_time_ms=result.total_time_ms,
            input_tokens=result.lead_input_tokens + result.drafter_input_tokens,
            output_tokens=result.lead_output_tokens + result.drafter_output_tokens,
            total_cost=result.total_cost,
            step_count=len(step_results),
            model=lead_spec,
        )

        completed_at = datetime.now(timezone.utc)

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=result.success,
            output={
                "final_implementation": result.final_implementation,
                "summary": result.to_summary(),
                # PCA-607: Raw drafter response for multi-file extraction
                "last_draft_raw_response": result.drafts[-1].raw_response if result.drafts else "",
            },
            metrics=metrics,
            steps=step_results,
            error=result.error,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "lead_contractor_result": result.to_summary(),
                "lead_agent": lead_spec,
                "drafter_agent": drafter_spec,
                "total_iterations": result.total_iterations,
                "lead_cost": result.lead_cost,
                "drafter_cost": result.drafter_cost,
                "cost_efficiency_ratio": result.get_cost_efficiency_ratio(),
            },
            project_context=project_context if not project_context.is_empty() else None,
        )

    async def _acreate_spec(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        context: Dict[str, Any],
        output_format: Optional[str],
    ) -> ImplementationSpec:
        """Phase 1 (async): Lead creates implementation specification."""
        spec_id = f"spec-{uuid.uuid4().hex[:8]}"

        # Avoid mutating the caller's dict (R1)
        context = dict(context)

        prompt = self._build_spec_prompt(task_description, context, output_format)

        response_text, response_time_ms, token_usage = await lead_agent.agenerate(prompt)

        requirements = self._parse_list_section(response_text, "Requirements")
        acceptance_criteria = self._parse_list_section(response_text, "Acceptance Criteria")
        edge_cases = self._parse_list_section(response_text, "Edge Cases")
        constraints = self._parse_list_section(response_text, "Constraints")
        technical_approach = self._parse_section_content(response_text, "Technical Approach")
        code_structure = self._parse_section_content(response_text, "Code Structure")

        spec = ImplementationSpec(
            spec_id=spec_id,
            task_summary=task_description,
            requirements=requirements,
            technical_approach=technical_approach,
            acceptance_criteria=acceptance_criteria,
            code_structure=code_structure if code_structure else None,
            edge_cases=edge_cases,
            constraints=constraints,
            raw_spec=response_text,
            input_tokens=token_usage.input if token_usage else 0,
            output_tokens=token_usage.output if token_usage else 0,
            time_ms=response_time_ms,
        )

        spec.cost = self._pricing.calculate_total_cost(
            lead_agent.model,
            spec.input_tokens,
            spec.output_tokens
        )

        return spec

    async def _acreate_draft(
        self,
        drafter_agent: BaseAgent,
        spec: ImplementationSpec,
        feedback: str,
        iteration: int,
        check_truncation: bool = True,
        strict_truncation: bool = False,
        target_files: Optional[List[str]] = None,
        existing_files: Optional[Dict[str, str]] = None,
        edit_mode: Optional[Dict] = None,
    ) -> DraftResult:
        """Phase 2/4 (async): Drafter creates implementation from spec.

        Uses shared prompt builders from implementation_engine but calls
        ``agent.agenerate()`` directly for async execution.
        """
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"

        output_format = _ie_drafter.build_output_format(
            target_files, existing_files=existing_files,
        )
        existing_files_section = _ie_drafter.build_existing_files_section(
            existing_files, edit_mode,
        )

        from ...implementation_engine.prompts import get_template as _ie_get_template
        if existing_files:
            draft_template = _ie_get_template("draft_edit")
        else:
            draft_template = _ie_get_template("draft")
        prompt = draft_template.format(
            spec=spec.raw_spec,
            feedback=feedback if feedback else "This is the initial implementation attempt.",
            output_format=output_format,
            existing_files_section=existing_files_section,
        )

        sys_prompt, draft_mode = _ie_drafter.get_drafter_system_prompt(existing_files)
        logger.info("Async drafter system prompt mode: %s", draft_mode)
        response_text, response_time_ms, token_usage = await drafter_agent.agenerate(
            prompt, system_prompt=sys_prompt
        )

        implementation_code = self._extract_code_from_response(response_text)

        api_truncated = token_usage.was_truncated if token_usage else False
        truncation_source = "api" if api_truncated else None

        heuristic_truncated = False
        if check_truncation and not api_truncated and implementation_code:
            confidence_threshold = CONFIDENCE_IS_TRUNCATED if strict_truncation else CONFIDENCE_HIGH
            expected = get_expected_sections_for_code(implementation_code)
            truncation_result = detect_truncation(
                implementation_code,
                expected_sections=expected,
                strict_mode=strict_truncation,
            )
            if truncation_result.is_truncated and truncation_result.confidence >= confidence_threshold:
                heuristic_truncated = True
                truncation_source = "heuristic"
                logger.warning(
                    "Draft appears truncated (heuristic, confidence=%.0f%%): %s",
                    truncation_result.confidence * 100,
                    truncation_result.indicators[:3],
                )

        was_truncated = api_truncated or heuristic_truncated

        size_regression_detected = _ie_drafter.detect_size_regression(
            existing_files, implementation_code,
        )
        was_truncated = was_truncated or size_regression_detected
        if size_regression_detected and not truncation_source:
            truncation_source = "size_regression"

        draft = DraftResult(
            draft_id=draft_id,
            iteration=iteration,
            implementation=implementation_code,
            spec_id=spec.spec_id,
            agent_name=drafter_agent.name,
            model=drafter_agent.model,
            input_tokens=token_usage.input if token_usage else 0,
            output_tokens=token_usage.output if token_usage else 0,
            time_ms=response_time_ms,
            was_truncated=was_truncated,
            truncation_source=truncation_source,
            raw_response=response_text,
        )

        draft.cost = self._pricing.calculate_total_cost(
            drafter_agent.model,
            draft.input_tokens,
            draft.output_tokens
        )

        return draft

    async def _areview_draft(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        spec: ImplementationSpec,
        implementation: str,
        pass_threshold: int,
        iteration: int,
    ) -> ReviewResult:
        """Phase 3 (async): Lead reviews the draft implementation."""
        review_id = f"review-{uuid.uuid4().hex[:8]}"

        prompt = REVIEW_PROMPT_TEMPLATE.format(
            task_description=task_description,
            spec=spec.raw_spec,
            implementation=implementation,
            pass_threshold=pass_threshold
        )

        response_text, response_time_ms, token_usage = await lead_agent.agenerate(prompt)

        review_text = response_text
        score = self._parse_score(review_text)
        has_pass_verdict = bool(re.search(r'\bPASS\b', review_text, re.IGNORECASE))
        passed = score >= pass_threshold and has_pass_verdict

        issues = self._parse_list_section(review_text, "Issues")
        blocking = self._parse_list_section(review_text, "Blocking Issues")
        suggestions = self._parse_list_section(review_text, "Suggestions")
        strengths = self._parse_list_section(review_text, "Strengths")

        review = ReviewResult(
            review_id=review_id,
            iteration=iteration,
            passed=passed,
            score=score,
            review_text=review_text,
            issues=issues,
            blocking_issues=blocking,
            suggestions=suggestions,
            strengths=strengths,
            input_tokens=token_usage.input if token_usage else 0,
            output_tokens=token_usage.output if token_usage else 0,
            time_ms=response_time_ms,
        )

        review.cost = self._pricing.calculate_total_cost(
            lead_agent.model,
            review.input_tokens,
            review.output_tokens
        )

        return review

    async def _aintegrate_final(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        implementation: str,
        reviews: List[ReviewResult],
        integration_instructions: str,
        target_files: Optional[List[str]] = None,
        existing_files: Optional[Dict[str, str]] = None,
    ) -> IntegrationResult:
        """Phase 5 (async): Lead integrates and finalizes the implementation."""
        integration_id = f"int-{uuid.uuid4().hex[:8]}"

        review_history = "\n\n".join([
            f"### Iteration {r.iteration}\n- Score: {r.score}\n- Passed: {r.passed}\n{r.review_text[:500]}"
            for r in reviews
        ])

        # PCA-607: Build multi-file directive for integration context
        multi_file_directive = self._build_multi_file_directive(
            target_files, existing_files,
        )

        prompt = INTEGRATION_PROMPT_TEMPLATE.format(
            task_description=task_description,
            implementation=implementation,
            review_history=review_history,
            integration_instructions=integration_instructions or "Finalize for production use.",
            multi_file_directive=multi_file_directive,
        )

        response_text, response_time_ms, token_usage = await lead_agent.agenerate(prompt)

        final_code = self._extract_code_from_response(response_text)

        integration = IntegrationResult(
            integration_id=integration_id,
            final_implementation=final_code,
            input_tokens=token_usage.input if token_usage else 0,
            output_tokens=token_usage.output if token_usage else 0,
            time_ms=response_time_ms,
        )

        integration.cost = self._pricing.calculate_total_cost(
            lead_agent.model,
            integration.input_tokens,
            integration.output_tokens
        )

        return integration

    def _format_review_feedback(self, review: ReviewResult) -> str:
        """Format review into feedback. Delegates to implementation_engine.reviewer."""
        # Convert lead_contractor_models.ReviewResult to engine ReviewResult
        engine_review = _IEReviewResult(
            review_id=review.review_id,
            iteration=review.iteration,
            passed=review.passed,
            score=review.score,
            issues=review.issues,
            blocking_issues=review.blocking_issues,
            suggestions=review.suggestions,
            strengths=review.strengths,
            review_text=review.review_text,
        )
        return _ie_reviewer.format_review_feedback(engine_review)

    def _parse_score(self, review_text: str) -> int:
        """Parse score from review text. Delegates to implementation_engine.parsers."""
        return _ie_parsers.parse_score(review_text)

    def _parse_list_section(self, text: str, section_name: str) -> List[str]:
        """Parse a bulleted list section. Delegates to implementation_engine.parsers."""
        return _ie_parsers.parse_list_section(text, section_name)

    def _parse_section_content(self, text: str, section_name: str) -> str:
        """Parse section content. Delegates to implementation_engine.parsers."""
        return _ie_parsers.parse_section_content(text, section_name)

    def _extract_code_from_response(self, response: str) -> str:
        """
        Extract code from markdown code blocks in LLM response.

        Delegates to the public utility ``extract_code_from_response``
        in ``startd8.utils.code_extraction``.
        """
        return extract_code_from_response(response)

    @staticmethod
    def _build_multi_file_directive(
        target_files: Optional[List[str]] = None,
        existing_files: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build a multi-file directive for the integration prompt (PCA-607).

        When the task targets multiple files *and* existing files are present,
        returns explicit instructions listing required output files, per-file
        fencing rules, and a preservation warning. Otherwise returns empty
        string so the placeholder collapses to nothing.
        """
        if not target_files or len(target_files) <= 1:
            return ""
        if not existing_files:
            return ""

        file_list = "\n".join(f"  - `{f}`" for f in target_files)
        per_file_lines = []
        for fpath, content in existing_files.items():
            line_count = len(content.splitlines())
            per_file_lines.append(f"  - `{fpath}`: {line_count} lines (existing)")

        return (
            "\n## Multi-File Edit Directive\n"
            "This task modifies MULTIPLE existing files. Your finalized output "
            "MUST contain a SEPARATE fenced code block for EACH file:\n"
            f"{file_list}\n\n"
            "Per-file sizes:\n"
            f"{chr(10).join(per_file_lines) if per_file_lines else '  (no size data)'}\n\n"
            "Each block must begin with `# <full path>` as the first line.\n"
            "PRESERVE all existing code — do not summarize or abbreviate."
        )

    # =========================================================================
    # Test Plan Generation Methods
    # =========================================================================

    def generate_test_plan_json(self, result: LeadContractorResult) -> TestPlanJSON:
        """Generate machine-parseable JSON test plan from workflow result."""
        test_cases = []

        # Generate test cases from spec acceptance criteria
        if result.spec and result.spec.acceptance_criteria:
            for i, criterion in enumerate(result.spec.acceptance_criteria):
                test_cases.append(TestCase(
                    id=f"TC-{i+1:03d}",
                    name=f"Verify: {criterion[:50]}",
                    description=criterion,
                    priority="P1",
                    category="unit",
                    steps=[f"Execute test for: {criterion}"],
                    expected_result="Criterion is satisfied"
                ))

        # Generate test cases from edge cases
        if result.spec and result.spec.edge_cases:
            for i, edge_case in enumerate(result.spec.edge_cases):
                test_cases.append(TestCase(
                    id=f"TC-E{i+1:03d}",
                    name=f"Edge case: {edge_case[:50]}",
                    description=edge_case,
                    priority="P2",
                    category="unit",
                    steps=[f"Test edge case: {edge_case}"],
                    expected_result="Edge case is handled correctly"
                ))

        # Count by priority and category
        by_priority: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for tc in test_cases:
            by_priority[tc.priority] = by_priority.get(tc.priority, 0) + 1
            by_category[tc.category] = by_category.get(tc.category, 0) + 1

        return TestPlanJSON(
            plan_id=f"test-{result.workflow_id}",
            task_description=result.spec.task_summary if result.spec else "",
            created_at=datetime.now(timezone.utc),
            workflow_id=result.workflow_id,
            test_cases=test_cases,
            total_tests=len(test_cases),
            by_priority=by_priority,
            by_category=by_category,
            coverage_notes=["Generated from acceptance criteria and edge cases"],
            gaps_identified=["Integration tests not generated", "Performance tests not included"]
        )

    def generate_test_plan_markdown(self, result: LeadContractorResult) -> str:
        """Generate human-readable Markdown test plan."""
        final_score = result.reviews[-1].score if result.reviews else "N/A"

        # Build test cases table
        test_cases_rows = []
        if result.spec and result.spec.acceptance_criteria:
            for i, criterion in enumerate(result.spec.acceptance_criteria):
                test_cases_rows.append(f"| TC-{i+1:03d} | {criterion[:60]} | P1 | unit |")

        test_cases_table = "\n".join(test_cases_rows) if test_cases_rows else "| - | No criteria found | - | - |"

        md = f"""# Test Plan: {result.workflow_id}

## Overview
- **Task**: {result.spec.task_summary if result.spec else 'N/A'}
- **Iterations**: {result.total_iterations}
- **Final Score**: {final_score}
- **Total Cost**: ${result.total_cost:.4f}

## Test Strategy

### Unit Tests
- Test each acceptance criterion individually
- Verify edge case handling
- Test error conditions

### Integration Tests
- Test component interactions
- Verify data flow

### End-to-End Tests
- Test complete workflows
- Verify user scenarios

## Test Cases

| ID | Description | Priority | Category |
|----|-------------|----------|----------|
{test_cases_table}

## Execution Plan
1. Run unit tests (`pytest tests/unit/`)
2. Run integration tests (`pytest tests/integration/`)
3. Perform manual validation

## Coverage Analysis

### Requirements Covered
{chr(10).join('- ' + c for c in (result.spec.acceptance_criteria or [])) if result.spec else '- N/A'}

### Gaps Identified
- Integration testing with external services not covered
- Performance testing not included
- Security testing needs manual review
"""
        return md


# Backward-compat alias (Phase 4 rename: Lead → Primary)
LeadContractorWorkflow = PrimaryContractorWorkflow
