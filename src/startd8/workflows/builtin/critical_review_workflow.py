"""
CriticalReviewWorkflow - Multi-agent document review workflow.

Multiple agents independently review design documents and create
detailed analysis reports covering strengths, weaknesses, and suggestions.
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


# Default review prompt template
REVIEW_PROMPT_TEMPLATE = """You are an expert technical reviewer and software architect. Your task is to critically review the following design document.

# Design Document

{document_content}

# Review Requirements

Please provide a comprehensive critical review that includes:

## 1. What is Good
Identify and highlight the strengths of this design document. What aspects are well thought out, clear, or innovative?

## 2. What is Bad
Identify weaknesses, gaps, ambiguities, or problematic aspects of the design. Be specific and constructive.

## 3. What Needs More or Less Of
- What areas need more detail, explanation, or coverage?
- What areas are too verbose or could be condensed?
- What topics are missing entirely?

## 4. Suggestions for Improvement
Provide specific, actionable suggestions for how to improve the design document. Include:
- Structural improvements
- Content additions or modifications
- Clarity enhancements
- Technical recommendations

Please be thorough, constructive, and specific in your analysis."""


class CriticalReviewWorkflow(WorkflowBase):
    """
    Critical Review workflow using multiple agents.

    Each agent independently reviews each document, creating detailed
    analysis reports. Reviews are saved as markdown files.

    Config Schema:
        {
            "documents": ["path/to/doc.md", ...] or ["content1", "content2"],
            "agents": ["provider:model", ...] - One or more agents
            "output_dir": "string - Output directory for review files",
            "review_template": "string - Custom review prompt template (optional)"
        }

    Example:
        result = workflow.run(
            config={
                "documents": ["design.md", "architecture.md"],
                "agents": ["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"],
                "output_dir": "./reviews"
            }
        )
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="critical-review",
            name="Critical Review Workflow",
            description="Multi-agent document review with detailed analysis reports",
            version="1.0.0",
            capabilities=["document-review", "multi-agent", "analysis"],
            tags=["review", "analysis", "document", "quality"],
            requires_agents=True,
            agent_count=AgentCount.CONFIGURABLE,
            min_agents=1,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="documents",
                    type="string_list",
                    required=True,
                    description="List of document paths or content strings to review"
                ),
                WorkflowInput(
                    name="agents",
                    type="agent_spec_list",
                    required=True,
                    description="One or more agents to perform reviews"
                ),
                WorkflowInput(
                    name="output_dir",
                    type="string",
                    required=False,
                    default="./critical_reviews",
                    description="Output directory for review files"
                ),
                WorkflowInput(
                    name="review_template",
                    type="text",
                    required=False,
                    description="Custom review prompt template (use {document_content} placeholder)"
                ),
            ]
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate critical review configuration."""
        errors = []

        # Check documents
        documents = config.get("documents", [])
        if not documents:
            errors.append("At least one document is required")
        elif not isinstance(documents, list):
            errors.append("Documents must be a list")

        # Check agents
        agents = config.get("agents", [])
        if not agents:
            errors.append("At least one agent is required")

        # Check custom template if provided
        template = config.get("review_template")
        if template and "{document_content}" not in template:
            errors.append("Custom review_template must contain {document_content} placeholder")

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute critical review workflow synchronously."""
        started_at = datetime.now()

        # Resolve agents
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        if not resolved_agents:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "No agents provided for critical review"
            )

        # Get documents
        documents = config.get("documents", [])
        if not documents:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "No documents provided for review"
            )

        # Get output directory
        output_dir_str = config.get("output_dir", "./critical_reviews")
        output_dir = Path(output_dir_str).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get review template
        review_template = config.get("review_template", REVIEW_PROMPT_TEMPLATE)

        # Calculate total reviews
        total_reviews = len(documents) * len(resolved_agents)
        current_review = 0

        self._emit_progress(on_progress, 0, total_reviews, "Starting critical reviews")

        # Track results
        step_results: List[StepResult] = []
        all_reviews: List[Dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0
        successful_reviews = 0
        failed_reviews = 0

        # Process each document with each agent
        for doc_idx, doc_input in enumerate(documents):
            # Determine if input is a path or content
            doc_path = None
            doc_content = None
            doc_name = f"document_{doc_idx + 1}"

            if isinstance(doc_input, str):
                potential_path = Path(doc_input).expanduser()
                if potential_path.exists() and potential_path.is_file():
                    doc_path = potential_path
                    doc_name = potential_path.stem
                    try:
                        doc_content = potential_path.read_text(encoding='utf-8')
                    except Exception as e:
                        # Record error and continue
                        for agent in resolved_agents:
                            current_review += 1
                            step_results.append(StepResult(
                                step_name=f"review_{doc_name}_{agent.name}",
                                agent_name=agent.name,
                                output="",
                                time_ms=0,
                                error=f"Failed to read document: {e}"
                            ))
                            failed_reviews += 1
                        continue
                else:
                    # Treat as content
                    doc_content = doc_input

            for agent in resolved_agents:
                current_review += 1
                step_name = f"review_{doc_name}_{agent.name}"

                self._emit_progress(
                    on_progress,
                    current_review,
                    total_reviews,
                    f"Reviewing {doc_name} with {agent.name}"
                )

                try:
                    # Generate review
                    review_prompt = review_template.format(document_content=doc_content)
                    response_text, time_ms, token_usage = agent.generate(review_prompt)

                    # Extract token info
                    input_tokens = token_usage.input_tokens if token_usage else 0
                    output_tokens = token_usage.output_tokens if token_usage else 0
                    cost = token_usage.cost if token_usage else 0.0

                    # Save review to file
                    safe_agent_name = agent.name.replace(" ", "_").replace("/", "_")
                    output_filename = f"{doc_name}_review_{safe_agent_name}.md"
                    output_path = output_dir / output_filename

                    # Build review content
                    review_content = f"# Critical Review: {doc_name}\n\n"
                    review_content += f"**Reviewed by:** {agent.name} ({agent.model})\n"
                    if doc_path:
                        review_content += f"**Original Document:** {doc_path}\n"
                    review_content += f"**Review Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                    review_content += "---\n\n"
                    review_content += response_text

                    # Write file (with simple versioning)
                    final_path = self._save_with_versioning(output_path, review_content)

                    step_results.append(StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{agent.model}",
                        output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        error=None
                    ))

                    all_reviews.append({
                        "document": doc_name,
                        "agent": agent.name,
                        "model": agent.model,
                        "output_path": str(final_path),
                        "success": True
                    })

                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    total_cost += cost
                    total_time_ms += time_ms
                    successful_reviews += 1

                except Exception as e:
                    step_results.append(StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{agent.model}",
                        output="",
                        time_ms=0,
                        error=str(e)
                    ))

                    all_reviews.append({
                        "document": doc_name,
                        "agent": agent.name,
                        "model": agent.model,
                        "error": str(e),
                        "success": False
                    })

                    failed_reviews += 1

        completed_at = datetime.now()

        # Build metrics
        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        # Determine success
        success = successful_reviews > 0

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "reviews": all_reviews,
                "successful": successful_reviews,
                "failed": failed_reviews,
                "output_dir": str(output_dir)
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "All reviews failed",
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "documents_count": len(documents),
                "agents_count": len(resolved_agents),
                "total_reviews": total_reviews,
                "successful_reviews": successful_reviews,
                "failed_reviews": failed_reviews,
                "output_dir": str(output_dir)
            }
        )

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """Execute critical review workflow asynchronously (FR-150)."""
        started_at = datetime.now()

        # Resolve agents
        resolved_agents = agents or []
        if not resolved_agents and "agents" in config:
            resolved_agents = resolve_agents(config["agents"])

        if not resolved_agents:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "No agents provided for critical review"
            )

        # Get documents
        documents = config.get("documents", [])
        if not documents:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                "No documents provided for review"
            )

        # Get output directory
        output_dir_str = config.get("output_dir", "./critical_reviews")
        output_dir = Path(output_dir_str).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get review template
        review_template = config.get("review_template", REVIEW_PROMPT_TEMPLATE)

        # Calculate total reviews
        total_reviews = len(documents) * len(resolved_agents)
        current_review = 0

        self._emit_progress(on_progress, 0, total_reviews, "Starting critical reviews")

        # Track results
        step_results: List[StepResult] = []
        all_reviews: List[Dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        total_time_ms = 0
        successful_reviews = 0
        failed_reviews = 0

        # Process each document with each agent
        for doc_idx, doc_input in enumerate(documents):
            doc_path = None
            doc_content = None
            doc_name = f"document_{doc_idx + 1}"

            if isinstance(doc_input, str):
                potential_path = Path(doc_input).expanduser()
                if potential_path.exists() and potential_path.is_file():
                    doc_path = potential_path
                    doc_name = potential_path.stem
                    try:
                        doc_content = potential_path.read_text(encoding='utf-8')
                    except Exception as e:
                        for agent in resolved_agents:
                            current_review += 1
                            step_results.append(StepResult(
                                step_name=f"review_{doc_name}_{agent.name}",
                                agent_name=agent.name,
                                output="",
                                time_ms=0,
                                error=f"Failed to read document: {e}"
                            ))
                            failed_reviews += 1
                        continue
                else:
                    doc_content = doc_input

            for agent in resolved_agents:
                current_review += 1
                step_name = f"review_{doc_name}_{agent.name}"

                self._emit_progress(
                    on_progress,
                    current_review,
                    total_reviews,
                    f"Reviewing {doc_name} with {agent.name}"
                )

                try:
                    review_prompt = review_template.format(document_content=doc_content)
                    # Async agent call (FR-150)
                    response_text, time_ms, token_usage = await agent.agenerate(review_prompt)

                    input_tokens = token_usage.input_tokens if token_usage else 0
                    output_tokens = token_usage.output_tokens if token_usage else 0
                    cost = token_usage.cost if token_usage else 0.0

                    safe_agent_name = agent.name.replace(" ", "_").replace("/", "_")
                    output_filename = f"{doc_name}_review_{safe_agent_name}.md"
                    output_path = output_dir / output_filename

                    review_content = f"# Critical Review: {doc_name}\n\n"
                    review_content += f"**Reviewed by:** {agent.name} ({agent.model})\n"
                    if doc_path:
                        review_content += f"**Original Document:** {doc_path}\n"
                    review_content += f"**Review Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                    review_content += "---\n\n"
                    review_content += response_text

                    final_path = self._save_with_versioning(output_path, review_content)

                    step_results.append(StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{agent.model}",
                        output=response_text[:500] + "..." if len(response_text) > 500 else response_text,
                        time_ms=time_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        error=None
                    ))

                    all_reviews.append({
                        "document": doc_name,
                        "agent": agent.name,
                        "model": agent.model,
                        "output_path": str(final_path),
                        "success": True
                    })

                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    total_cost += cost
                    total_time_ms += time_ms
                    successful_reviews += 1

                except Exception as e:
                    step_results.append(StepResult(
                        step_name=step_name,
                        agent_name=f"{agent.name}:{agent.model}",
                        output="",
                        time_ms=0,
                        error=str(e)
                    ))

                    all_reviews.append({
                        "document": doc_name,
                        "agent": agent.name,
                        "model": agent.model,
                        "error": str(e),
                        "success": False
                    })

                    failed_reviews += 1

        completed_at = datetime.now()

        metrics = WorkflowMetrics(
            total_time_ms=total_time_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_cost=total_cost,
            step_count=len(step_results),
        )

        success = successful_reviews > 0

        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=success,
            output={
                "reviews": all_reviews,
                "successful": successful_reviews,
                "failed": failed_reviews,
                "output_dir": str(output_dir)
            },
            metrics=metrics,
            steps=step_results,
            error=None if success else "All reviews failed",
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "documents_count": len(documents),
                "agents_count": len(resolved_agents),
                "total_reviews": total_reviews,
                "successful_reviews": successful_reviews,
                "failed_reviews": failed_reviews,
                "output_dir": str(output_dir)
            }
        )

    def _save_with_versioning(self, path: Path, content: str) -> Path:
        """Save content to file, adding version number if file exists."""
        if not path.exists():
            path.write_text(content, encoding='utf-8')
            return path

        # File exists, add version number
        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        version = 1
        while True:
            versioned_path = parent / f"{stem}_v{version}{suffix}"
            if not versioned_path.exists():
                versioned_path.write_text(content, encoding='utf-8')
                return versioned_path
            version += 1
