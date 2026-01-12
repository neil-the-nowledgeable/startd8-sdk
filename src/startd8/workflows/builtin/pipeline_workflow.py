"""
PipelineWorkflow - Wrapper for the Pipeline orchestration class.

Exposes the Pipeline functionality through the unified Workflow interface.
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
from ...orchestration import Pipeline, PipelineResult
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agents


class PipelineWorkflow(WorkflowBase):
    """
    Sequential agent pipeline workflow.

    Wraps the Pipeline orchestration class to provide a unified workflow
    interface for agent-accessible execution.

    Config Schema:
        {
            "initial_input": "string - The input to start the pipeline",
            "steps": [
                {
                    "name": "step-name",
                    "agent": "provider:model or agent index",
                    "transform_prefix": "optional prefix to add before input"
                }
            ],
            "agents": ["provider:model", ...] - Optional list of agents to use
        }

    Example:
        result = workflow.run(
            config={
                "initial_input": "Write a function to calculate fibonacci",
                "steps": [
                    {"name": "planner", "agent": 0},
                    {"name": "implementer", "agent": 1, "transform_prefix": "Implement: "}
                ]
            },
            agents=[claude_agent, gpt_agent]
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="pipeline",
            name="Pipeline Workflow",
            description="Sequential multi-agent pipeline with metrics tracking",
            version="1.0.0",
            capabilities=["sequential", "multi-agent", "transform"],
            tags=["orchestration", "pipeline"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=1,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="initial_input",
                    type="text",
                    required=True,
                    description="The input to start the pipeline"
                ),
                WorkflowInput(
                    name="steps",
                    type="string",  # JSON array
                    required=False,
                    description="Step configurations [{name, agent, transform_prefix}]"
                ),
                WorkflowInput(
                    name="pipeline_name",
                    type="string",
                    required=False,
                    default="pipeline",
                    description="Name for the pipeline"
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Agent specifications (provider:model format)"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate pipeline configuration."""
        errors = []

        # Check required input
        if "initial_input" not in config:
            errors.append("Missing required input: initial_input")

        # Check agents
        agents = config.get("agents", [])
        if not agents and "steps" in config:
            # Steps defined but no agents - check if steps reference agent specs
            for step in config.get("steps", []):
                if isinstance(step.get("agent"), str) and ":" in step.get("agent", ""):
                    # Looks like an agent spec in step, that's ok
                    pass
                elif isinstance(step.get("agent"), int):
                    errors.append(
                        f"Step '{step.get('name', '?')}' references agent by index "
                        f"but no agents list provided"
                    )

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute the pipeline synchronously."""
        started_at = datetime.now()

        # Resolve agents from config or parameter
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        # Build pipeline
        pipeline_name = config.get("pipeline_name", "pipeline")
        pipeline = Pipeline(name=pipeline_name)

        # Configure steps
        steps_config = config.get("steps", [])
        if steps_config:
            for step_cfg in steps_config:
                step_name = step_cfg.get("name", f"step-{len(pipeline.steps)+1}")

                # Resolve agent for this step
                agent_ref = step_cfg.get("agent", 0)
                if isinstance(agent_ref, int):
                    if agent_ref >= len(resolved_agents):
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            f"Step '{step_name}' references agent index {agent_ref} "
                            f"but only {len(resolved_agents)} agents available"
                        )
                    step_agent = resolved_agents[agent_ref]
                elif isinstance(agent_ref, str):
                    step_agent = resolve_agents([agent_ref])[0]
                else:
                    step_agent = resolved_agents[0]

                # Build transform function
                transform = None
                if "transform_prefix" in step_cfg:
                    prefix = step_cfg["transform_prefix"]
                    transform = lambda x, p=prefix: f"{p}{x}"

                pipeline.add_step(
                    name=step_name,
                    agent=step_agent,
                    transform=transform,
                    metadata=step_cfg.get("metadata", {})
                )
        else:
            # No steps defined - create one step per agent
            for i, agent in enumerate(resolved_agents):
                pipeline.add_step(
                    name=f"step-{i+1}",
                    agent=agent,
                )

        # Report progress
        total_steps = len(pipeline.steps)
        self._emit_progress(on_progress, 0, total_steps, "Starting pipeline")

        # Run pipeline
        try:
            pipeline_result: PipelineResult = pipeline.run(
                config["initial_input"],
                store=False  # Don't store in framework - workflow manages this
            )
        except Exception as e:
            return WorkflowResult.from_error(self.metadata.workflow_id, str(e))

        # Convert pipeline result to workflow result
        completed_at = datetime.now()

        # Build step results
        step_results = []
        for i, step_data in enumerate(pipeline_result.steps):
            step_results.append(StepResult(
                step_name=step_data.get("step_name", f"step-{i+1}"),
                agent_name=step_data.get("agent_name"),
                output=step_data.get("output", ""),
                time_ms=step_data.get("response_time_ms", 0),
                input_tokens=step_data.get("tokens", {}).get("input", 0),
                output_tokens=step_data.get("tokens", {}).get("output", 0),
                cost=step_data.get("cost", 0.0),
            ))

            # Report progress
            self._emit_progress(
                on_progress,
                i + 1,
                total_steps,
                f"Completed {step_data.get('step_name', f'step-{i+1}')}"
            )

        # Build metrics
        metrics = WorkflowMetrics(
            total_time_ms=pipeline_result.total_time_ms,
            input_tokens=sum(s.input_tokens for s in step_results),
            output_tokens=sum(s.output_tokens for s in step_results),
            total_cost=pipeline_result.total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=True,
            output=pipeline_result.final_output,
            metrics=metrics,
            steps=step_results,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "pipeline_id": pipeline_result.pipeline_id,
                "pipeline_name": pipeline_name,
            }
        )

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute the pipeline asynchronously."""
        started_at = datetime.now()

        # Resolve agents from config or parameter
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        # Build pipeline
        pipeline_name = config.get("pipeline_name", "pipeline")
        pipeline = Pipeline(name=pipeline_name)

        # Configure steps
        steps_config = config.get("steps", [])
        if steps_config:
            for step_cfg in steps_config:
                step_name = step_cfg.get("name", f"step-{len(pipeline.steps)+1}")

                agent_ref = step_cfg.get("agent", 0)
                if isinstance(agent_ref, int):
                    if agent_ref >= len(resolved_agents):
                        return WorkflowResult.from_error(
                            self.metadata.workflow_id,
                            f"Step '{step_name}' references agent index {agent_ref} "
                            f"but only {len(resolved_agents)} agents available"
                        )
                    step_agent = resolved_agents[agent_ref]
                elif isinstance(agent_ref, str):
                    step_agent = resolve_agents([agent_ref])[0]
                else:
                    step_agent = resolved_agents[0]

                transform = None
                if "transform_prefix" in step_cfg:
                    prefix = step_cfg["transform_prefix"]
                    transform = lambda x, p=prefix: f"{p}{x}"

                pipeline.add_step(
                    name=step_name,
                    agent=step_agent,
                    transform=transform,
                    metadata=step_cfg.get("metadata", {})
                )
        else:
            for i, agent in enumerate(resolved_agents):
                pipeline.add_step(name=f"step-{i+1}", agent=agent)

        total_steps = len(pipeline.steps)
        self._emit_progress(on_progress, 0, total_steps, "Starting pipeline")

        try:
            pipeline_result: PipelineResult = await pipeline.arun(
                config["initial_input"],
                store=False
            )
        except Exception as e:
            return WorkflowResult.from_error(self.metadata.workflow_id, str(e))

        completed_at = datetime.now()

        step_results = []
        for i, step_data in enumerate(pipeline_result.steps):
            step_results.append(StepResult(
                step_name=step_data.get("step_name", f"step-{i+1}"),
                agent_name=step_data.get("agent_name"),
                output=step_data.get("output", ""),
                time_ms=step_data.get("response_time_ms", 0),
                input_tokens=step_data.get("tokens", {}).get("input", 0),
                output_tokens=step_data.get("tokens", {}).get("output", 0),
                cost=step_data.get("cost", 0.0),
            ))
            self._emit_progress(
                on_progress, i + 1, total_steps,
                f"Completed {step_data.get('step_name', f'step-{i+1}')}"
            )

        metrics = WorkflowMetrics(
            total_time_ms=pipeline_result.total_time_ms,
            input_tokens=sum(s.input_tokens for s in step_results),
            output_tokens=sum(s.output_tokens for s in step_results),
            total_cost=pipeline_result.total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=True,
            output=pipeline_result.final_output,
            metrics=metrics,
            steps=step_results,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "pipeline_id": pipeline_result.pipeline_id,
                "pipeline_name": pipeline_name,
            }
        )
