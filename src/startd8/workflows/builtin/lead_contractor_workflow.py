"""
LeadContractorWorkflow - Cost-efficient multi-agent implementation pattern.

Claude acts as "lead contractor" (architect, spec writer, reviewer, integrator)
while cheaper models handle the actual drafting work.

Pattern:
1. Claude creates detailed implementation spec
2. Drafter (Gemini Flash, GPT-4.1-nano, etc.) implements from spec
3. Claude reviews implementation
4. If not approved, loop back to step 2 (max 3 iterations)
5. Claude integrates/finalizes

Cost Structure (January 2026):
Lead Contractors (Claude 4.5 family - recommended):
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
import json
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
    ProjectContext,
)
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agent_spec
from ...utils.code_extraction import extract_code_from_response
from ...logging_config import get_logger
from ...costs.pricing import PricingService
from ...truncation_detection import TruncationResult, detect_truncation, get_expected_sections_for_code

from .lead_contractor_models import (
    LeadContractorConfig,
    ImplementationSpec,
    DraftResult,
    ReviewResult,
    IntegrationResult,
    LeadContractorResult,
    PhaseMetrics,
    WorkflowPhase,
    TestPlanJSON,
    TestPlanMarkdown,
    TestCase,
)

logger = get_logger(__name__)


# ============================================================================
# Prompt Templates
# ============================================================================

SPEC_PROMPT_TEMPLATE = """You are a senior software architect acting as the Lead Contractor for this implementation task.

## Task Description
{task_description}

## Context
{context}

## Your Role
Create a detailed implementation specification that a junior developer (or AI model) can follow precisely.
Be explicit, thorough, and leave no ambiguity.

## Required Output Format

Provide your specification in the following structure:

### Task Summary
[One paragraph summary of what needs to be built]

### Requirements
1. [Requirement 1]
2. [Requirement 2]
...

### Technical Approach
[Detailed technical approach with architecture decisions]

### Code Structure
[Expected files, classes, functions with signatures]

### Acceptance Criteria
1. [Criterion 1]
2. [Criterion 2]
...

### Edge Cases
- [Edge case 1]
- [Edge case 2]
...

### Constraints
- [Constraint 1]
- [Constraint 2]
...

### Examples
[Code examples or pseudocode if helpful]

Be thorough - the implementer will follow your spec exactly.
"""

DRAFT_PROMPT_TEMPLATE = """You are implementing code based on a detailed specification from a senior architect.

## Implementation Specification
{spec}

## Previous Feedback (if any)
{feedback}

## Instructions
1. Follow the specification EXACTLY
2. Implement all requirements listed
3. Handle all edge cases mentioned
4. Write clean, well-documented code
5. Include inline comments explaining key decisions

## Output Format
Provide your complete implementation followed by a brief explanation of your approach.

```
[Your implementation code here]
```

## Explanation
[Brief notes on your implementation approach]
"""

REVIEW_PROMPT_TEMPLATE = """You are reviewing an implementation as the Lead Contractor.

## Original Task
{task_description}

## Your Specification
{spec}

## Implementation to Review
{implementation}

## Review Instructions
Evaluate the implementation against your specification. Be thorough but fair.

## Required Output Format

### Score: [0-100]
[Single number representing overall quality]

### Verdict: [PASS/FAIL]
[PASS if score >= {pass_threshold} and no blocking issues, otherwise FAIL]

### Strengths
- [What was done well]

### Issues
- [Problems found, with severity: BLOCKING, MAJOR, MINOR]

### Suggestions
- [Specific improvements for next iteration if FAIL]

### Blocking Issues (if any)
- [Issues that MUST be fixed before passing]

### Full Review
[Detailed analysis of the implementation]
"""

INTEGRATION_PROMPT_TEMPLATE = """You are the Lead Contractor finalizing the implementation.

## Original Task
{task_description}

## Final Implementation
{implementation}

## Review History
{review_history}

## Integration Instructions
{integration_instructions}

## Your Role
1. Review the final implementation one last time
2. Make any minor polish or adjustments needed
3. Ensure the code is production-ready
4. Add any final documentation or comments

## Output Format
Provide the finalized, production-ready implementation:

```
[Final implementation code]
```

## Integration Notes
[Any notes about the final version]
"""


class LeadContractorWorkflow(WorkflowBase):
    """
    Lead Contractor workflow for cost-efficient multi-agent implementation.

    Uses Claude as the architect/reviewer while cheaper models draft code.

    Config Schema:
        {
            "task_description": "string - What to implement",
            "context": {...} - Optional additional context,
            "lead_agent": "anthropic:claude-sonnet-4-20250514" - Lead contractor (Sonnet 4),
            "drafter_agent": "gemini:gemini-2.5-flash-lite" - Drafter agent (best value),
            "max_iterations": 3 - Max review cycles,
            "pass_threshold": 80 - Minimum score to pass (0-100),
            "output_format": "string - Expected output format (optional)",
            "integration_instructions": "string - Final integration notes (optional)",
            "check_truncation": true - Enable truncation detection (default: true),
            "fail_on_truncation": true - Fail workflow if truncation detected (default: true),
            "strict_truncation": false - Use strict detection threshold (default: false)
        }

    Truncation Protection:
        By default, the workflow detects and fails on truncated drafter output.
        This prevents incomplete implementations from being silently accepted.

        - check_truncation (default: True): Enable/disable truncation detection
        - fail_on_truncation (default: True): Raise error vs. warn on truncation
        - strict_truncation (default: False): Lower confidence threshold for detection

        To disable truncation protection (not recommended):
            config={"check_truncation": False}

        To warn but continue on truncation:
            config={"fail_on_truncation": False}

    Recommended Lead Agents:
        - anthropic:claude-sonnet-4-20250514 (default - best for coding/agents)
        - anthropic:claude-opus-4-5-20251101 (most intelligent)
        - anthropic:claude-haiku-4-5-20251008 (fastest, near-frontier)

    Recommended Drafter Agents:
        - gemini:gemini-2.5-flash-lite (default - $0.075/$0.30, best value)
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
            name="Lead Contractor Workflow",
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
                    default="anthropic:claude-sonnet-4-20250514",
                    description="Lead contractor agent (Claude 4 recommended: sonnet-4, opus-4-5, haiku-4-5)"
                ),
                WorkflowInput(
                    name="drafter_agent",
                    type="agent_spec",
                    required=False,
                    default="gemini:gemini-2.5-flash-lite",
                    description="Drafter agent (cost-efficient: gemini-2.5-flash-lite, gpt-4.1-nano, gpt-4o-mini)"
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
                    name="fail_on_truncation",
                    type="boolean",
                    required=False,
                    default=True,
                    description="Fail workflow if truncation detected (default: True). If False, logs warning and continues."
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
        """Execute the Lead Contractor workflow synchronously."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"lc-{uuid.uuid4().hex[:12]}"

        # Parse configuration
        task_description = config["task_description"]
        context = config.get("context", {})
        lead_spec = config.get("lead_agent", "anthropic:claude-sonnet-4-20250514")
        drafter_spec = config.get("drafter_agent", "gemini:gemini-2.5-flash")
        max_iterations = config.get("max_iterations", 3)
        pass_threshold = config.get("pass_threshold", 80)
        output_format = config.get("output_format")
        integration_instructions = config.get("integration_instructions", "")
        # Truncation protection defaults - safe by default
        check_truncation = config.get("check_truncation", True)
        fail_on_truncation = config.get("fail_on_truncation", True)
        strict_truncation = config.get("strict_truncation", False)
        
        # Extract ContextCore project context
        project_context = self._extract_project_context(config)

        # Resolve agents (forward max_tokens if configured)
        agent_max_tokens = config.get("max_tokens")
        resolve_kwargs = {"max_tokens": agent_max_tokens} if agent_max_tokens else {}
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

        self._emit_progress(on_progress, current_step, total_steps, "Starting Lead Contractor workflow")

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
            # Phase 2-4: Draft/Review Loop
            # =================================================================
            current_implementation = ""
            review_feedback = ""
            final_review: Optional[ReviewResult] = None

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
                )
                result.drafts.append(draft)
                current_implementation = draft.implementation

                # Check for truncation - fail fast if enabled
                if check_truncation and draft.was_truncated:
                    if fail_on_truncation:
                        error_msg = (
                            f"Draft was truncated at iteration {iteration}. "
                            f"Output tokens: {draft.output_tokens}. "
                            "Consider: (1) increasing max_tokens, (2) decomposing the task, "
                            "or (3) setting fail_on_truncation=False to continue anyway."
                        )
                        logger.error(error_msg)
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            error_msg,
                            steps=step_results,
                        )
                    else:
                        logger.warning(
                            f"Draft was truncated at iteration {iteration}, continuing anyway. "
                            f"Set fail_on_truncation=True to fail on truncation."
                        )

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
                )
                result.reviews.append(review)
                final_review = review

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
            logger.error(f"Lead Contractor workflow failed: {e}", exc_info=True)
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

    def _create_spec(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        context: Dict[str, Any],
        output_format: Optional[str],
    ) -> ImplementationSpec:
        """Phase 1: Lead creates implementation specification."""
        spec_id = f"spec-{uuid.uuid4().hex[:8]}"

        context_str = json.dumps(context, indent=2) if context else "No additional context provided."
        if output_format:
            context_str += f"\n\nExpected Output Format:\n{output_format}"

        prompt = SPEC_PROMPT_TEMPLATE.format(
            task_description=task_description,
            context=context_str
        )

        response_text, response_time_ms, token_usage = lead_agent.generate(prompt)

        # Parse structured data from the spec response
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

        # Calculate cost
        spec.cost = self._pricing.calculate_total_cost(
            lead_agent.model,
            spec.input_tokens,
            spec.output_tokens
        )

        return spec

    def _create_draft(
        self,
        drafter_agent: BaseAgent,
        spec: ImplementationSpec,
        feedback: str,
        iteration: int,
        check_truncation: bool = True,
        strict_truncation: bool = False,
    ) -> DraftResult:
        """Phase 2/4: Drafter creates implementation from spec.

        Args:
            drafter_agent: The agent to use for drafting
            spec: The implementation specification
            feedback: Review feedback from previous iteration (if any)
            iteration: Current iteration number
            check_truncation: Whether to run heuristic truncation detection (default: True)
            strict_truncation: Use lower confidence threshold for detection (default: False)
        """
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"

        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec=spec.raw_spec,
            feedback=feedback if feedback else "This is the initial implementation attempt."
        )

        response_text, response_time_ms, token_usage = drafter_agent.generate(prompt)

        # Extract code from markdown code blocks (removes LLM commentary)
        implementation_code = self._extract_code_from_response(response_text)

        # Check for truncation (API-level detection)
        was_truncated = token_usage.was_truncated if token_usage else False

        # Also run heuristic detection for incomplete code (if enabled)
        if check_truncation and not was_truncated and implementation_code:
            # Use 0.5 threshold for strict mode, 0.7 for normal mode
            confidence_threshold = 0.5 if strict_truncation else 0.7
            # Infer language-appropriate structure markers (None skips the check)
            expected = get_expected_sections_for_code(implementation_code)
            truncation_result = detect_truncation(
                implementation_code,
                original_input=prompt,
                expected_sections=expected,
                strict_mode=strict_truncation,
            )
            if truncation_result.is_truncated and truncation_result.confidence >= confidence_threshold:
                was_truncated = True
                logger.warning(
                    f"Draft appears truncated (heuristic, confidence={truncation_result.confidence:.0%}): "
                    f"{truncation_result.indicators[:3]}"
                )

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
            was_truncated=was_truncated,  # Track truncation status
        )

        draft.cost = self._pricing.calculate_total_cost(
            drafter_agent.model,
            draft.input_tokens,
            draft.output_tokens
        )

        return draft

    def _review_draft(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        spec: ImplementationSpec,
        implementation: str,
        pass_threshold: int,
        iteration: int,
    ) -> ReviewResult:
        """Phase 3: Lead reviews the draft implementation."""
        review_id = f"review-{uuid.uuid4().hex[:8]}"

        prompt = REVIEW_PROMPT_TEMPLATE.format(
            task_description=task_description,
            spec=spec.raw_spec,
            implementation=implementation,
            pass_threshold=pass_threshold
        )

        response_text, response_time_ms, token_usage = lead_agent.generate(prompt)

        # Parse review
        review_text = response_text
        score = self._parse_score(review_text)
        # Use word boundary regex to avoid false positives (e.g., "BYPASS", "PASSPORT")
        has_pass_verdict = bool(re.search(r'\bPASS\b', review_text, re.IGNORECASE))
        passed = score >= pass_threshold and has_pass_verdict

        # Parse issues
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

    def _integrate_final(
        self,
        lead_agent: BaseAgent,
        task_description: str,
        implementation: str,
        reviews: List[ReviewResult],
        integration_instructions: str,
    ) -> IntegrationResult:
        """Phase 5: Lead integrates and finalizes the implementation."""
        integration_id = f"int-{uuid.uuid4().hex[:8]}"

        review_history = "\n\n".join([
            f"### Iteration {r.iteration}\n- Score: {r.score}\n- Passed: {r.passed}\n{r.review_text[:500]}"
            for r in reviews
        ])

        prompt = INTEGRATION_PROMPT_TEMPLATE.format(
            task_description=task_description,
            implementation=implementation,
            review_history=review_history,
            integration_instructions=integration_instructions or "Finalize for production use."
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
        """Execute the Lead Contractor workflow asynchronously (FR-150)."""
        started_at = datetime.now(timezone.utc)
        workflow_id = f"lc-{uuid.uuid4().hex[:12]}"

        task_description = config["task_description"]
        context = config.get("context", {})
        lead_spec = config.get("lead_agent", "anthropic:claude-sonnet-4-20250514")
        drafter_spec = config.get("drafter_agent", "gemini:gemini-2.5-flash")
        max_iterations = config.get("max_iterations", 3)
        pass_threshold = config.get("pass_threshold", 80)
        output_format = config.get("output_format")
        integration_instructions = config.get("integration_instructions", "")
        # Truncation protection defaults - safe by default
        check_truncation = config.get("check_truncation", True)
        fail_on_truncation = config.get("fail_on_truncation", True)
        strict_truncation = config.get("strict_truncation", False)

        project_context = self._extract_project_context(config)

        # Resolve agents (forward max_tokens if configured)
        agent_max_tokens = config.get("max_tokens")
        resolve_kwargs = {"max_tokens": agent_max_tokens} if agent_max_tokens else {}
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

        self._emit_progress(on_progress, current_step, total_steps, "Starting Lead Contractor workflow")

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
            final_review: Optional[ReviewResult] = None

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
                )
                result.drafts.append(draft)
                current_implementation = draft.implementation

                if check_truncation and draft.was_truncated:
                    if fail_on_truncation:
                        error_msg = (
                            f"Draft was truncated at iteration {iteration}. "
                            f"Output tokens: {draft.output_tokens}. "
                            "Consider: (1) increasing max_tokens, (2) decomposing the task, "
                            "or (3) setting fail_on_truncation=False to continue anyway."
                        )
                        logger.error(error_msg)
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            error_msg,
                            steps=step_results,
                        )
                    else:
                        logger.warning(
                            f"Draft was truncated at iteration {iteration}, continuing anyway. "
                            f"Set fail_on_truncation=True to fail on truncation."
                        )

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
                final_review = review

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
            logger.error(f"Lead Contractor workflow failed: {e}", exc_info=True)
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

        context_str = json.dumps(context, indent=2) if context else "No additional context provided."
        if output_format:
            context_str += f"\n\nExpected Output Format:\n{output_format}"

        prompt = SPEC_PROMPT_TEMPLATE.format(
            task_description=task_description,
            context=context_str
        )

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
    ) -> DraftResult:
        """Phase 2/4 (async): Drafter creates implementation from spec.

        Args:
            drafter_agent: The agent to use for drafting
            spec: The implementation specification
            feedback: Review feedback from previous iteration (if any)
            iteration: Current iteration number
            check_truncation: Whether to run heuristic truncation detection (default: True)
            strict_truncation: Use lower confidence threshold for detection (default: False)
        """
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"

        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec=spec.raw_spec,
            feedback=feedback if feedback else "This is the initial implementation attempt."
        )

        response_text, response_time_ms, token_usage = await drafter_agent.agenerate(prompt)

        implementation_code = self._extract_code_from_response(response_text)

        was_truncated = token_usage.was_truncated if token_usage else False

        # Also run heuristic detection for incomplete code (if enabled)
        if check_truncation and not was_truncated and implementation_code:
            # Use 0.5 threshold for strict mode, 0.7 for normal mode
            confidence_threshold = 0.5 if strict_truncation else 0.7
            truncation_result = detect_truncation(
                implementation_code,
                original_input=prompt,
                expected_sections=["def ", "class "],
                strict_mode=strict_truncation,
            )
            if truncation_result.is_truncated and truncation_result.confidence >= confidence_threshold:
                was_truncated = True
                logger.warning(
                    f"Draft appears truncated (heuristic, confidence={truncation_result.confidence:.0%}): "
                    f"{truncation_result.indicators[:3]}"
                )

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
    ) -> IntegrationResult:
        """Phase 5 (async): Lead integrates and finalizes the implementation."""
        integration_id = f"int-{uuid.uuid4().hex[:8]}"

        review_history = "\n\n".join([
            f"### Iteration {r.iteration}\n- Score: {r.score}\n- Passed: {r.passed}\n{r.review_text[:500]}"
            for r in reviews
        ])

        prompt = INTEGRATION_PROMPT_TEMPLATE.format(
            task_description=task_description,
            implementation=implementation,
            review_history=review_history,
            integration_instructions=integration_instructions or "Finalize for production use."
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
        """Format review into feedback for next draft iteration."""
        issues_str = '\n'.join(f'- {issue}' for issue in review.issues) if review.issues else '- None listed'
        blocking_str = '\n'.join(f'- {b}' for b in review.blocking_issues) if review.blocking_issues else '- None'
        suggestions_str = '\n'.join(f'- {s}' for s in review.suggestions) if review.suggestions else '- None listed'

        feedback = f"""## Review Feedback (Score: {review.score}/100)

### Issues to Address:
{issues_str}

### Blocking Issues (MUST FIX):
{blocking_str}

### Suggestions:
{suggestions_str}

### Full Feedback:
{review.review_text}
"""
        return feedback

    def _parse_score(self, review_text: str) -> int:
        """Parse score from review text."""
        # Look for "Score: X" pattern
        match = re.search(r'Score:\s*(\d+)', review_text, re.IGNORECASE)
        if match:
            return min(100, max(0, int(match.group(1))))
        return 0

    def _parse_list_section(self, text: str, section_name: str) -> List[str]:
        """Parse a bulleted list section from review text."""
        # Look for section header followed by bulleted items
        pattern = rf'###?\s*{section_name}[^\n]*\n((?:\s*[-*]\s*[^\n]+\n?)+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            items_text = match.group(1)
            items = re.findall(r'[-*]\s*(.+)', items_text)
            return [item.strip() for item in items if item.strip()]
        return []

    def _parse_section_content(self, text: str, section_name: str) -> str:
        """Parse the content of a section (non-list) from spec text."""
        # Look for section header and capture until next section or end
        pattern = rf'###?\s*{section_name}[^\n]*\n(.*?)(?=###|\Z)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Remove any leading bullet points if present
            content = re.sub(r'^[-*]\s*', '', content, flags=re.MULTILINE)
            return content.strip()
        return ""

    def _extract_code_from_response(self, response: str) -> str:
        """
        Extract code from markdown code blocks in LLM response.

        Delegates to the public utility ``extract_code_from_response``
        in ``startd8.utils.code_extraction``.
        """
        return extract_code_from_response(response)

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
