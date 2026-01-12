"""
DocEnhancementWorkflow - Wrapper for DocumentEnhancementChain.

Exposes document enhancement functionality through the unified Workflow interface.
"""

from datetime import datetime
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
from ...document_enhancement import DocumentEnhancementChain
from ...models import DocumentEnhancementConfig, AgentConfig
from ...agents import BaseAgent
from ...utils.agent_resolution import resolve_agents


class DocEnhancementWorkflow(WorkflowBase):
    """
    Document enhancement workflow using multiple agents.

    Wraps the DocumentEnhancementChain to provide sequential document
    refinement through the unified workflow interface.

    Config Schema:
        {
            "document": "string - Document content or file path",
            "instructions": "string - Enhancement instructions",
            "agents": ["provider:model", ...] - Agents to use
            "save_intermediate": bool - Whether to save intermediate results
            "output_dir": "string - Output directory path (optional)"
        }

    Example:
        result = workflow.run(
            config={
                "document": "# My Design\\n...",
                "instructions": "Add accessibility considerations",
                "agents": ["openai:gpt-4", "anthropic:claude-sonnet-4-20250514"]
            }
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="doc-enhancement",
            name="Document Enhancement Workflow",
            description="Sequential multi-agent document enhancement and refinement",
            version="1.0.0",
            capabilities=["document-enhancement", "multi-agent", "refinement"],
            tags=["document", "enhancement", "writing"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=1,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="document",
                    type="text",
                    required=True,
                    description="Document content or file path to enhance"
                ),
                WorkflowInput(
                    name="instructions",
                    type="text",
                    required=False,
                    default="Improve clarity, completeness, and technical accuracy",
                    description="Enhancement instructions for the agents"
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=False,
                    description="Agent specifications (provider:model format)"
                ),
                WorkflowInput(
                    name="save_intermediate",
                    type="boolean",
                    required=False,
                    default=False,
                    description="Whether to save intermediate results"
                ),
                WorkflowInput(
                    name="output_dir",
                    type="string",
                    required=False,
                    description="Output directory for enhanced document"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate document enhancement configuration."""
        errors = []

        if "document" not in config:
            errors.append("Missing required input: document")

        # Check if document is a file path that exists
        doc = config.get("document", "")
        if doc and not doc.startswith("#") and not "\n" in doc:
            # Looks like a path
            path = Path(doc)
            if not path.exists():
                errors.append(f"Document file not found: {doc}")

        # Check agents
        agents = config.get("agents", [])
        if not agents:
            errors.append("At least one agent is required")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute document enhancement synchronously."""
        started_at = datetime.now()

        # Resolve agents
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        if not resolved_agents:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "No agents provided for document enhancement"
            )

        # Get document content
        doc_input = config["document"]
        if Path(doc_input).exists():
            source_document = Path(doc_input)
            document_content = source_document.read_text()
        else:
            # Assume it's document content directly
            source_document = None
            document_content = doc_input

        # Get instructions
        instructions = config.get(
            "instructions",
            "Improve clarity, completeness, and technical accuracy"
        )

        # Build agent configs
        agent_configs = []
        for i, agent in enumerate(resolved_agents):
            agent_configs.append(AgentConfig(
                agent_name=f"{agent.name}:{agent.model}",
                agent_instance=agent,
                step_name=f"{agent.name}-step-{i+1}",
                order=i
            ))

        # Build enhancement config
        # Create a temporary file if document is content-only
        if source_document is None:
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.md',
                delete=False
            ) as f:
                f.write(document_content)
                source_document = Path(f.name)

        output_dir = config.get("output_dir")
        if output_dir:
            output_path = Path(output_dir)
        else:
            output_path = None

        enhancement_config = DocumentEnhancementConfig(
            source_document=source_document,
            enhancement_instructions=instructions,
            agents=agent_configs,
            save_intermediate=config.get("save_intermediate", False),
            output_path=output_path,
        )

        # Create chain
        chain = DocumentEnhancementChain(enhancement_config)

        # Report progress
        total_steps = len(resolved_agents)
        self._emit_progress(on_progress, 0, total_steps, "Starting enhancement")

        # Progress callback adapter
        def progress_adapter(current: int, total: int):
            self._emit_progress(
                on_progress,
                current,
                total,
                f"Completed step {current}/{total}"
            )

        # Run chain
        try:
            chain_result = chain.run(
                on_progress=progress_adapter
            )
        except Exception as e:
            return WorkflowResult.from_error(self.metadata.workflow_id, str(e))

        completed_at = datetime.now()

        # Build step results
        step_results = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        for step in chain_result.steps:
            step_results.append(StepResult(
                step_name=step.step_name,
                agent_name=step.agent_name,
                output=step.output[:500] + "..." if len(step.output) > 500 else step.output,
                time_ms=step.response_time_ms,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                cost=step.cost,
                error=step.error,
            ))
            total_input_tokens += step.input_tokens
            total_output_tokens += step.output_tokens
            total_cost += step.cost

        # Build metrics
        metrics = WorkflowMetrics(
            total_time_ms=chain_result.total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=chain_result.success,
            output=chain_result.final_document,
            metrics=metrics,
            steps=step_results,
            error=None if chain_result.success else "Enhancement failed",
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "chain_id": chain_result.chain_id,
                "output_path": str(chain_result.output_path) if chain_result.output_path else None,
            }
        )
