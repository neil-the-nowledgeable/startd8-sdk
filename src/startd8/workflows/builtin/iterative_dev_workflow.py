"""
IterativeDevWorkflowWrapper - Wrapper for IterativeDevWorkflow.

Exposes the iterative development workflow through the unified Workflow interface.
"""

from datetime import datetime
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
from ...iterative_workflow import IterativeDevWorkflow, IterativeWorkflowResult
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agents


class IterativeDevWorkflowWrapper(WorkflowBase):
    """
    Iterative development workflow with code review feedback loop.

    Wraps the IterativeDevWorkflow to provide a dev-review-fix cycle
    through the unified workflow interface.

    The workflow follows this pattern:
    1. Developer agent implements the task
    2. Reviewer agent reviews the code
    3. If issues found, sends feedback back to developer
    4. Developer fixes issues based on feedback
    5. Repeat until passed or max iterations reached

    Config Schema:
        {
            "task": "string - Task description to implement",
            "developer_agent": "provider:model - Developer agent spec",
            "reviewer_agent": "provider:model - Reviewer agent spec",
            "max_iterations": int - Maximum iterations (default: 3),
            "agents": ["dev_spec", "reviewer_spec"] - Alternative to individual specs
        }

    Example:
        result = workflow.run(
            config={
                "task": "Implement a function to validate email addresses",
                "developer_agent": "anthropic:claude-sonnet-4-20250514",
                "reviewer_agent": "openai:gpt-4o"
            }
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="iterative-dev",
            name="Iterative Development Workflow",
            description="Dev-review-fix loop with feedback until code passes review",
            version="1.0.0",
            capabilities=["development", "code-review", "iterative", "feedback-loop"],
            tags=["development", "review", "iterative"],
            requires_agents=True,
            agent_count=AgentCount.MULTIPLE,
            min_agents=2,
            max_agents=2,
            inputs=[
                WorkflowInput(
                    name="task",
                    type="text",
                    required=True,
                    description="Task description for the developer to implement"
                ),
                WorkflowInput(
                    name="developer_agent",
                    type="agent_spec",
                    required=False,
                    description="Developer agent specification (provider:model)"
                ),
                WorkflowInput(
                    name="reviewer_agent",
                    type="agent_spec",
                    required=False,
                    description="Reviewer agent specification (provider:model)"
                ),
                WorkflowInput(
                    name="max_iterations",
                    type="number",
                    required=False,
                    default=3,
                    description="Maximum number of dev-review iterations"
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="[developer, reviewer] agent specs (alternative to individual)"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate iterative dev configuration."""
        errors = []

        if "task" not in config:
            errors.append("Missing required input: task")

        # Check agents - need exactly 2 (developer and reviewer)
        has_individual = "developer_agent" in config and "reviewer_agent" in config
        has_list = "agents" in config and len(config.get("agents", [])) >= 2

        if not has_individual and not has_list:
            errors.append(
                "Must provide either (developer_agent, reviewer_agent) or agents list with 2 agents"
            )

        # Validate max_iterations
        max_iter = config.get("max_iterations", 3)
        if not isinstance(max_iter, int) or max_iter < 1:
            errors.append("max_iterations must be a positive integer")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute iterative dev workflow synchronously."""
        started_at = datetime.now()

        # Resolve agents
        if agents and len(agents) >= 2:
            developer_agent = agents[0]
            reviewer_agent = agents[1]
        elif "developer_agent" in config and "reviewer_agent" in config:
            developer_agent = resolve_agents([config["developer_agent"]])[0]
            reviewer_agent = resolve_agents([config["reviewer_agent"]])[0]
        elif "agents" in config and len(config["agents"]) >= 2:
            resolved = resolve_agents(config["agents"][:2])
            developer_agent = resolved[0]
            reviewer_agent = resolved[1]
        else:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "Need exactly 2 agents: developer and reviewer"
            )

        # Get config values
        task = config["task"]
        max_iterations = config.get("max_iterations", 3)

        # Create the underlying workflow
        workflow = IterativeDevWorkflow(
            developer_agent=developer_agent,
            reviewer_agent=reviewer_agent,
            max_iterations=max_iterations,
        )

        # Report progress
        self._emit_progress(on_progress, 0, max_iterations, "Starting development")

        # Progress tracking via callback
        iteration_count = [0]  # Use list to allow modification in closure

        def on_iteration_complete(iteration):
            iteration_count[0] = iteration.iteration_number
            status = "passed" if iteration.feedback and iteration.feedback.passed else "needs revision"
            self._emit_progress(
                on_progress,
                iteration.iteration_number,
                max_iterations,
                f"Iteration {iteration.iteration_number}: {status}"
            )

        # Add callback if workflow supports it
        if hasattr(workflow, 'on_iteration_complete'):
            workflow.on_iteration_complete = on_iteration_complete

        # Run workflow
        try:
            result: IterativeWorkflowResult = workflow.run(
                task_description=task,
            )
        except Exception as e:
            return WorkflowResult.from_error(self.metadata.workflow_id, str(e))

        completed_at = datetime.now()

        # Build step results from iterations
        step_results = []
        for iteration in result.iterations:
            # Dev step
            step_results.append(StepResult(
                step_name=f"iteration-{iteration.iteration_number}-dev",
                agent_name=iteration.dev_agent_name,
                output=iteration.dev_response[:500] + "..." if len(iteration.dev_response) > 500 else iteration.dev_response,
                time_ms=iteration.dev_time_ms,
                input_tokens=iteration.dev_tokens.input if iteration.dev_tokens else 0,
                output_tokens=iteration.dev_tokens.output if iteration.dev_tokens else 0,
            ))

            # Review step
            feedback_info = ""
            if iteration.feedback:
                feedback_info = f" (passed={iteration.feedback.passed}, score={iteration.feedback.score})"
            step_results.append(StepResult(
                step_name=f"iteration-{iteration.iteration_number}-review",
                agent_name=iteration.review_agent_name,
                output=iteration.review_response[:500] + "..." if len(iteration.review_response) > 500 else iteration.review_response,
                time_ms=iteration.review_time_ms,
                input_tokens=iteration.review_tokens.input if iteration.review_tokens else 0,
                output_tokens=iteration.review_tokens.output if iteration.review_tokens else 0,
                metadata={"feedback": feedback_info}
            ))

        # Build metrics
        metrics = WorkflowMetrics(
            total_time_ms=result.total_time_ms,
            input_tokens=result.total_dev_tokens + result.total_review_tokens,
            output_tokens=0,  # Breakdown not available
            total_cost=result.total_cost,
            step_count=len(step_results),
        )

        # Determine success
        success = result.successful

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output=result.final_code,
            metrics=metrics,
            steps=step_results,
            error=None if success else f"Completed with status: {result.status.value}",
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "workflow_id": result.workflow_id,
                "status": result.status.value,
                "total_iterations": result.total_iterations,
                "final_review_passed": result.final_review.passed if result.final_review else None,
                "final_review_score": result.final_review.score if result.final_review else None,
            }
        )
