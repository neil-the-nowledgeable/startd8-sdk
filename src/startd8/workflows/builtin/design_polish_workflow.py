"""
DesignPolishWorkflow - Wrapper for design_polish_chain Pipeline.

A 3-stage design document refinement workflow:
Polish → Suggest Updates → Final Polish
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
from ...orchestration import WorkflowTemplates
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agents


class DesignPolishWorkflow(WorkflowBase):
    """
    Design document polish workflow using exactly 3 agents.

    Wraps the design_polish_chain Pipeline to provide 3-stage document
    refinement through the unified workflow interface.

    Stages:
        1. Polish: Initial polish for clarity and structure
        2. Suggest Updates: Review and suggest improvements
        3. Final Polish: Incorporate suggestions into final version

    Config Schema:
        {
            "document": "string - Design document content to polish",
            "agents": ["provider:model", ...] - Exactly 3 agents [polisher, updater, final_polisher]
            "prompt_instructions": "string - Custom instructions for polisher (optional)"
        }

    Example:
        result = workflow.run(
            config={
                "document": "# API Design\\n...",
                "agents": [
                    "anthropic:claude-sonnet-4-20250514",
                    "openai:gpt-4o",
                    "anthropic:claude-opus-4-5-20251101"
                ]
            }
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="design-polish",
            name="Design Polish Workflow",
            description="3-stage design document refinement: Polish → Suggest Updates → Final Polish",
            version="1.0.0",
            capabilities=["document-polish", "multi-agent", "design-refinement"],
            tags=["design", "polish", "document", "refinement"],
            requires_agents=True,
            agent_count=AgentCount.MULTIPLE,
            min_agents=3,
            max_agents=3,
            inputs=[
                WorkflowInput(
                    name="document",
                    type="text",
                    required=True,
                    description="Design document content to polish"
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=True,
                    description="Exactly 3 agents: [polisher, updater, final_polisher]"
                ),
                WorkflowInput(
                    name="prompt_instructions",
                    type="text",
                    required=False,
                    description="Custom polishing instructions for the first agent"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate design polish configuration."""
        errors = []

        if "document" not in config:
            errors.append("Missing required input: document")
        elif not config["document"] or not config["document"].strip():
            errors.append("Document cannot be empty")

        # Check agents - exactly 3 required
        agents = config.get("agents", [])
        if not agents:
            errors.append("Agents are required: [polisher, updater, final_polisher]")
        elif len(agents) != 3:
            errors.append(f"Exactly 3 agents required, got {len(agents)}")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute design polish workflow synchronously."""
        started_at = datetime.now()

        # Resolve agents
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        if len(resolved_agents) != 3:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Exactly 3 agents required, got {len(resolved_agents)}"
            )

        polisher_agent = resolved_agents[0]
        updater_agent = resolved_agents[1]
        final_polisher_agent = resolved_agents[2]

        # Get document and optional instructions
        document = config["document"]
        prompt_instructions = config.get("prompt_instructions")

        # Create the pipeline using WorkflowTemplates factory
        pipeline = WorkflowTemplates.design_polish_chain(
            polisher_agent=polisher_agent,
            updater_agent=updater_agent,
            final_polisher_agent=final_polisher_agent,
            prompt_instructions=prompt_instructions
        )

        # Report progress
        total_steps = 3
        self._emit_progress(on_progress, 0, total_steps, "Starting design polish")

        # Track step progress
        step_results: List[StepResult] = []
        current_step = 0

        def step_callback(step_name: str, output: str, metadata: Dict[str, Any]):
            nonlocal current_step
            current_step += 1
            self._emit_progress(
                on_progress,
                current_step,
                total_steps,
                f"Completed {step_name}"
            )

        # Run pipeline
        try:
            pipeline_result = pipeline.run(
                initial_input=document,
                on_step_complete=step_callback
            )
        except Exception as e:
            return WorkflowResult.from_error(self.metadata.workflow_id, str(e))

        completed_at = datetime.now()

        # Build step results from pipeline
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0

        for step in pipeline_result.steps:
            input_tokens = step.token_usage.input_tokens if step.token_usage else 0
            output_tokens = step.token_usage.output_tokens if step.token_usage else 0
            cost = step.token_usage.cost if step.token_usage else 0.0

            step_results.append(StepResult(
                step_name=step.step_name,
                agent_name=step.agent_name,
                output=step.output[:500] + "..." if len(step.output) > 500 else step.output,
                time_ms=step.time_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                error=step.error,
            ))

            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            total_cost += cost
            total_time_ms += step.time_ms

        # Build metrics
        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=pipeline_result.success,
            output=pipeline_result.final_output,
            metrics=metrics,
            steps=step_results,
            error=pipeline_result.error,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "pipeline_name": pipeline_result.pipeline_name,
                "polisher": f"{polisher_agent.name}:{polisher_agent.model}",
                "updater": f"{updater_agent.name}:{updater_agent.model}",
                "final_polisher": f"{final_polisher_agent.name}:{final_polisher_agent.model}",
            }
        )
