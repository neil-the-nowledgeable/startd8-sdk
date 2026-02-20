"""
Convergent Review Workflow - Orchestrates a two-step review process:
1. Review and refine requirements.
2. Review and refine the plan/design (considering the requirements).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from ...utils.agent_resolution import resolve_agents
from .architectural_review_log_workflow import ArchitecturalReviewLogWorkflow


class ConvergentReviewWorkflow(WorkflowBase):
    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="convergent-review",
            name="Convergent Review Protocol",
            description=(
                "Orchestrates a sequential convergent review: first refines the requirements document, "
                "then refines the plan/design document while referencing the requirements."
            ),
            version="1.0.0",
            capabilities=["document-review", "orchestration", "multi-step"],
            tags=["review", "requirements", "design", "sequential"],
            requires_agents=False,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="requirements_path",
                    type="string",
                    required=True,
                    description="Path to the requirements markdown document",
                ),
                WorkflowInput(
                    name="plan_path",
                    type="string",
                    required=True,
                    description="Path to the plan or design markdown document",
                ),
                WorkflowInput(
                    name="requirements_profile",
                    type="string",
                    required=False,
                    default="requirements",
                    description="Review profile for the requirements step (e.g., requirements, custom)",
                ),
                WorkflowInput(
                    name="plan_profile",
                    type="string",
                    required=False,
                    default="design",
                    description="Review profile for the plan step (e.g., design, architecture, custom)",
                ),
                WorkflowInput(
                    name="reviewer_count",
                    type="number",
                    required=False,
                    default=2,
                    description="Number of reviewers per step",
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Optional agents to use for both steps",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors = []
        req_path = config.get("requirements_path")
        plan_path = config.get("plan_path")

        if not req_path:
            errors.append("requirements_path is required")
        if not plan_path:
            errors.append("plan_path is required")
            
        if req_path and not Path(req_path).exists():
             errors.append(f"requirements_path does not exist: {req_path}")
        if plan_path and not Path(plan_path).exists():
             errors.append(f"plan_path does not exist: {plan_path}")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)
        
        req_path = str(Path(config["requirements_path"]).expanduser().resolve())
        plan_path = str(Path(config["plan_path"]).expanduser().resolve())
        
        req_profile = config.get("requirements_profile", "requirements")
        plan_profile = config.get("plan_profile", "design")
        reviewer_count = config.get("reviewer_count", 2)
        
        # Instantiate the inner workflow
        arc_review = ArchitecturalReviewLogWorkflow()
        
        total_steps = 2
        step_results: List[StepResult] = []
        total_time_ms = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        # ------------------------------------------------------------------
        # Step 1: Requirements Review
        # ------------------------------------------------------------------
        self._emit_progress(on_progress, 0, total_steps, "Step 1/2: Running Convergent Review on Requirements")
        
        req_config = {
            "document_path": req_path,
            "review_profile": req_profile,
            "reviewer_count": reviewer_count,
            "agents": config.get("agents"),
            # Don't pass feature_requirements here; we are reviewing the requirements themselves
        }
        
        # Pass through other optional configs if needed (e.g. costs, safety settings)
        for key in ["warn_cost_usd", "max_cost_usd", "quality_tier", "providers", "enable_apply", "enable_prompt_caching"]:
            if key in config:
                req_config[key] = config[key]

        req_result = arc_review._execute(req_config, agents, on_progress)
        
        # Collect metrics from step 1
        if req_result.metrics:
            total_time_ms += req_result.metrics.total_time_ms
            total_input_tokens += req_result.metrics.input_tokens
            total_output_tokens += req_result.metrics.output_tokens
            total_cost += req_result.metrics.total_cost
        
        step_results.extend(req_result.steps)
        
        if not req_result.success:
            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=False,
                output={},
                metrics=WorkflowMetrics(
                    total_time_ms=total_time_ms,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_cost=total_cost,
                    step_count=len(step_results),
                ),
                steps=step_results,
                error=f"Requirements review failed: {req_result.error}",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        # ------------------------------------------------------------------
        # Step 2: Plan Review (considering Requirements)
        # ------------------------------------------------------------------
        self._emit_progress(on_progress, 1, total_steps, "Step 2/2: Running Convergent Review on Plan (with Requirements context)")
        
        plan_config = {
            "document_path": plan_path,
            "review_profile": plan_profile,
            "reviewer_count": reviewer_count,
            "agents": config.get("agents"),
            "feature_requirements": [req_path], # Pass the refined requirements
        }
        
        # Pass through optional configs
        for key in ["warn_cost_usd", "max_cost_usd", "quality_tier", "providers", "enable_apply", "enable_prompt_caching"]:
            if key in config:
                plan_config[key] = config[key]

        plan_result = arc_review._execute(plan_config, agents, on_progress)

        # Collect metrics from step 2
        if plan_result.metrics:
            total_time_ms += plan_result.metrics.total_time_ms
            total_input_tokens += plan_result.metrics.input_tokens
            total_output_tokens += plan_result.metrics.output_tokens
            total_cost += plan_result.metrics.total_cost
            
        step_results.extend(plan_result.steps)

        completed_at = datetime.now(timezone.utc)
        success = plan_result.success

        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "requirements_review": req_result.output,
                "plan_review": plan_result.output,
            },
            metrics=metrics,
            steps=step_results,
            error=plan_result.error if not success else None,
            started_at=started_at,
            completed_at=completed_at,
        )
