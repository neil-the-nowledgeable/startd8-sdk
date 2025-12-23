"""
Orchestration module for sequential LLM workflows

Combines benchmarking capabilities with LangChain-style pipelines
for multi-step agent workflows with full metrics tracking.
"""

import time
import asyncio
import uuid
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass

from .models import TokenUsage, AgentResponse
from .agents import BaseAgent
from .events import EventBus, EventType, Event
from .exceptions import AgentError, APIError, ConfigurationError


@dataclass
class PipelineStep:
    """A single step in a pipeline"""
    name: str
    agent: BaseAgent
    transform: Optional[Callable[[str], str]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PipelineResult:
    """Result from running a pipeline"""
    steps: List[Dict[str, Any]]
    final_output: str
    total_time_ms: int
    total_tokens: int
    total_cost: float
    pipeline_id: str
    timestamp: datetime


class Pipeline:
    """
    Sequential agent pipeline with metrics tracking
    
    Inspired by LangChain's sequential chains but with full
    benchmarking and metrics support from startd8.
    
    Example:
        ```python
        pipeline = Pipeline(name="design-implement")
        
        # Add steps
        pipeline.add_step(
            name="planner",
            agent=ClaudeAgent(),
            transform=None
        )
        
        pipeline.add_step(
            name="implementer",
            agent=GPT4Agent(),
            transform=lambda spec: f"Implement this design:\\n\\n{spec}"
        )
        
        # Run with tracking
        result = pipeline.run("Design a new feature")
        print(f"Total cost: ${result.total_cost:.4f}")
        print(f"Total time: {result.total_time_ms}ms")
        ```
    """
    
    def __init__(self, name: str = "pipeline", framework=None):
        """
        Initialize pipeline
        
        Args:
            name: Pipeline name
            framework: Optional AgentFramework for storage
        """
        self.name = name
        self.framework = framework
        self.steps: List[PipelineStep] = []
        
    def add_step(
        self,
        name: str,
        agent: BaseAgent,
        transform: Optional[Callable[[str], str]] = None,
        metadata: Optional[Dict[str, Any]] = None  # Can contain arbitrary fields, filtered when passed to agent
    ) -> 'Pipeline':
        """
        Add a step to the pipeline
        
        Args:
            name: Step name (e.g., "planner", "implementer")
            agent: Agent to use for this step
            transform: Optional function to transform input before sending to agent
            metadata: Optional step metadata
            
        Returns:
            Self for chaining
        """
        step = PipelineStep(
            name=name,
            agent=agent,
            transform=transform,
            metadata=metadata or {}
        )
        self.steps.append(step)
        return self
    
    async def arun(self, initial_input: str, store: bool = True) -> PipelineResult:
        """
        Run the pipeline asynchronously
        
        Args:
            initial_input: Initial input to first agent
            store: Whether to store results in framework (if available)
            
        Returns:
            PipelineResult with all step details
        """
        pipeline_id = f"pipeline-{uuid.uuid4().hex[:12]}"
        start_time = time.time()
        
        # Emit pipeline start event
        EventBus.emit(Event(
            type=EventType.PIPELINE_START,
            source="Pipeline",
            data={
                "pipeline_id": pipeline_id,
                "pipeline_name": self.name,
                "steps": [s.name for s in self.steps]
            },
            correlation_id=pipeline_id
        ))
        
        current_input = initial_input
        step_results = []
        total_tokens = 0
        total_cost = 0.0
        
        # Create a prompt if framework available
        if self.framework and store:
            prompt = self.framework.create_prompt(
                content=initial_input,
                version="1.0.0",
                tags=[self.name, "pipeline"],
                metadata={
                    "pipeline_id": pipeline_id,
                    "pipeline_name": self.name,
                    "steps": [s.name for s in self.steps]
                }
            )
            prompt_id = prompt.id
        else:
            prompt_id = None

        # Always run through BaseAgent.(a)create_response() so budget/cost enforcement
        # and response_id linkage are consistent, even when we aren't storing prompts.
        tracking_prompt_id = prompt_id or f"prompt-{uuid.uuid4().hex[:12]}"
        
        try:
            # Execute each step
            for i, step in enumerate(self.steps):
                # Emit step start event
                EventBus.emit(Event(
                    type=EventType.PIPELINE_STEP_START,
                    source="Pipeline",
                    data={
                        "pipeline_id": pipeline_id,
                        "step_number": i + 1,
                        "step_name": step.name,
                        "agent": step.agent.name
                    },
                    correlation_id=pipeline_id
                ))
                
                # Transform input if needed
                step_input = step.transform(current_input) if step.transform else current_input
                
                # Run agent asynchronously (with cost/budget enforcement if configured)
                # Build step metadata compatible with ResponseMetadata TypedDict
                valid_metadata_fields = set(ResponseMetadata.__annotations__.keys())
                step_metadata: ResponseMetadata = {
                    "pipeline_id": pipeline_id,
                    "step_number": i + 1,
                    "agent_name": step.agent.name,
                    "model": step.agent.model,
                    **{k: v for k, v in step.metadata.items() if k in valid_metadata_fields}
                }
                agent_response = await step.agent.acreate_response(
                    prompt_id=tracking_prompt_id,
                    prompt=step_input,
                    metadata=step_metadata,
                    tags=[self.name, "pipeline", step.name],
                    pipeline_id=pipeline_id
                )
                response_text = agent_response.response
                response_time_ms = agent_response.response_time_ms
                token_usage = agent_response.token_usage
                
                # Track metrics
                total_tokens += token_usage.total if token_usage else 0
                total_cost += token_usage.cost_estimate if token_usage else 0
                
                # Store step result
                step_result = {
                    "step_number": i + 1,
                    "step_name": step.name,
                    "agent": step.agent.name,
                    "model": step.agent.model,
                    "input": step_input[:200] + "..." if len(step_input) > 200 else step_input,
                    "output": response_text,
                    "response_time_ms": response_time_ms,
                    "tokens": token_usage.total if token_usage else 0,
                    "cost": token_usage.cost_estimate if token_usage else 0,
                    "metadata": step.metadata
                }
                step_results.append(step_result)
                
                # Emit step complete event
                EventBus.emit(Event(
                    type=EventType.PIPELINE_STEP_COMPLETE,
                    source="Pipeline",
                    data={
                        "pipeline_id": pipeline_id,
                        "step_number": i + 1,
                        "step_name": step.name,
                        "response_time_ms": response_time_ms,
                        "tokens": token_usage.total if token_usage else 0
                    },
                    correlation_id=pipeline_id
                ))
                
                # Store in framework if available
                if self.framework and store and prompt_id:
                    self.framework.record_response(
                        prompt_id=prompt_id,
                        agent_name=f"{self.name}:{step.name}",
                        model=step.agent.model,
                        response=response_text,
                        response_time_ms=response_time_ms,
                        token_usage=token_usage,
                        metadata={
                            "pipeline_id": pipeline_id,
                            "step_number": i + 1,
                            "step_name": step.name,
                            **step.metadata
                        },
                        response_id=agent_response.id,
                        timestamp=agent_response.timestamp,
                    )
                
                # Output becomes input for next step
                current_input = response_text
            
            end_time = time.time()
            total_time_ms = int((end_time - start_time) * 1000)
            
            result = PipelineResult(
                steps=step_results,
                final_output=current_input,
                total_time_ms=total_time_ms,
                total_tokens=total_tokens,
                total_cost=total_cost,
                pipeline_id=pipeline_id,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Emit pipeline complete event
            EventBus.emit(Event(
                type=EventType.PIPELINE_COMPLETE,
                source="Pipeline",
                data={
                    "pipeline_id": pipeline_id,
                    "total_time_ms": total_time_ms,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost
                },
                correlation_id=pipeline_id
            ))
            
            return result
            
        except (AgentError, APIError, ConfigurationError) as e:
            # Known pipeline errors - log with context and re-raise
            from .logging_config import get_logger
            logger = get_logger(__name__)
            
            logger.error(
                f"Pipeline '{self.name}' failed: {e}",
                exc_info=True,
                extra={
                    "pipeline_id": pipeline_id,
                    "pipeline_name": self.name,
                    "error_type": type(e).__name__,
                    "pipeline_error": str(e)
                }
            )
            # Re-raise known exceptions to allow caller to handle
            raise
        except Exception as e:
            # Unexpected errors during pipeline execution
            from .logging_config import get_logger
            logger = get_logger(__name__)
            
            logger.error(
                f"Unexpected error in pipeline '{self.name}': {e}",
                exc_info=True,
                extra={
                    "pipeline_id": pipeline_id,
                    "pipeline_name": self.name,
                    "error_type": type(e).__name__,
                    "steps": [s.name for s in self.steps]
                }
            )
            
            # Emit pipeline error event
            EventBus.emit(Event(
                type=EventType.PIPELINE_ERROR,
                source="Pipeline",
                data={
                    "pipeline_id": pipeline_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                correlation_id=pipeline_id
            ))
            
            # Wrap unexpected errors in AgentError for consistency
            raise AgentError(
                f"Unexpected error in pipeline '{self.name}': {e}",
                agent_name=getattr(e, 'agent_name', None),
                original_error=e
            ) from e
    
    def run(self, initial_input: str, store: bool = True) -> PipelineResult:
        """
        Run the pipeline (synchronous wrapper)
        
        Args:
            initial_input: Initial input to first agent
            store: Whether to store results in framework (if available)
            
        Returns:
            PipelineResult with all step details
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.arun(initial_input, store))

        # Running inside an existing event loop (e.g. Jupyter/FastAPI).
        # Bridge by running the coroutine in a new thread + event loop.
        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> PipelineResult:
            return asyncio.run(self.arun(initial_input, store))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()
    
    async def arun_parallel_agents(
        self, 
        initial_input: str, 
        agents: List[BaseAgent]
    ) -> List[tuple[str, int, TokenUsage]]:
        """
        Run multiple agents in parallel on the same input.
        
        This is useful for comparing responses from different models
        or getting consensus from multiple agents.
        
        Args:
            initial_input: Input to send to all agents
            agents: List of agents to run in parallel
            
        Returns:
            List of (response_text, response_time_ms, token_usage) tuples
        """
        tasks = [agent.agenerate(initial_input) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                EventBus.emit(Event(
                    type=EventType.AGENT_CALL_ERROR,
                    source="Pipeline",
                    data={
                        "agent_name": agents[i].name,
                        "error": str(result)
                    }
                ))
            else:
                successful_results.append(result)
        
        return successful_results
    
    def to_dict(self) -> Dict[str, Any]:
        """Export pipeline configuration"""
        return {
            "name": self.name,
            "steps": [
                {
                    "name": step.name,
                    "agent": step.agent.name,
                    "model": step.agent.model,
                    "metadata": step.metadata
                }
                for step in self.steps
            ]
        }


class WorkflowTemplates:
    """Pre-built workflow templates"""
    
    @staticmethod
    def planner_implementer(planner_agent: BaseAgent, implementer_agent: BaseAgent) -> Pipeline:
        """
        Classic planner → implementer workflow
        
        Args:
            planner_agent: Agent for design/planning
            implementer_agent: Agent for implementation guidance
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="planner-implementer")
        
        pipeline.add_step(
            name="planner",
            agent=planner_agent,
            metadata={"role": "designer"}
        )
        
        pipeline.add_step(
            name="implementer",
            agent=implementer_agent,
            transform=lambda spec: (
                f"Here is the design spec:\n\n{spec}\n\n"
                f"Now provide implementation guidance for a developer."
            ),
            metadata={"role": "developer"}
        )
        
        return pipeline
    
    @staticmethod
    def code_review(reviewer_agent: BaseAgent, improver_agent: BaseAgent) -> Pipeline:
        """
        Code review → improvement workflow
        
        Args:
            reviewer_agent: Agent for reviewing code
            improver_agent: Agent for suggesting improvements
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="code-review")
        
        pipeline.add_step(
            name="reviewer",
            agent=reviewer_agent,
            transform=lambda code: (
                f"Review this code and identify issues:\n\n{code}"
            ),
            metadata={"role": "reviewer"}
        )
        
        pipeline.add_step(
            name="improver",
            agent=improver_agent,
            transform=lambda review: (
                f"Based on this code review:\n\n{review}\n\n"
                f"Provide specific improvements."
            ),
            metadata={"role": "improver"}
        )
        
        return pipeline
    
    @staticmethod
    def design_review_chain(
        drafter_agent: BaseAgent,
        reviewer_agent: BaseAgent,
        final_reviewer_agent: BaseAgent
    ) -> Pipeline:
        """
        Design document creation chain: Draft → Review → Final Polish
        
        Args:
            drafter_agent: Agent to create the first draft (e.g., Sonnet 4.5)
            reviewer_agent: Agent to review the draft (e.g., GPT-4)
            final_reviewer_agent: Agent for final review/polish (e.g., Composer)
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="design-review-chain")
        
        pipeline.add_step(
            name="drafter",
            agent=drafter_agent,
            metadata={"role": "drafter", "task": "create_initial_draft"}
        )
        
        pipeline.add_step(
            name="reviewer",
            agent=reviewer_agent,
            transform=lambda draft: (
                f"Review the following design document draft. Identify gaps, inconsistencies, "
                f"and areas for improvement. Be critical and constructive.\n\n"
                f"DRAFT:\n{draft}"
            ),
            metadata={"role": "reviewer", "task": "review_draft"}
        )
        
        pipeline.add_step(
            name="final_reviewer",
            agent=final_reviewer_agent,
            transform=lambda review_feedback: (
                f"Based on the previous review, provide a final polished version of the design document. "
                f"incorporate the feedback where appropriate and ensure the document is complete and professional.\n\n"
                f"REVIEW FEEDBACK:\n{review_feedback}"
            ),
            metadata={"role": "final_reviewer", "task": "final_polish"}
        )
        
        return pipeline
    
    @staticmethod
    def design_polish_chain(
        polisher_agent: BaseAgent,
        updater_agent: BaseAgent,
        final_polisher_agent: BaseAgent,
        prompt_instructions: Optional[str] = None
    ) -> Pipeline:
        """
        Design document polish chain: Polish → Suggest Updates → Final Polish
        
        Starts with an existing drafted design document and refines it through
        three stages: initial polish, update suggestions, and final polish.
        
        Args:
            polisher_agent: Agent for initial polish pass (e.g., Claude Sonnet)
            updater_agent: Agent to suggest updates/improvements (e.g., GPT-4)
            final_polisher_agent: Agent for final polish incorporating suggestions (e.g., Claude Opus)
            prompt_instructions: Optional custom instructions from prompt file to use for the first agent (polisher) only
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="design-polish-chain")
        
        # Base instructions for each step
        polish_base = (
            "Review and polish the following design document. Improve clarity, "
            "structure, and professional presentation while maintaining all core content."
        )
        
        updater_base = (
            "Review the polished design document below and suggest specific updates, "
            "improvements, or additions. Be constructive and specific about what should "
            "be changed or added. Focus on:\n"
            "- Missing sections or details\n"
            "- Areas that need clarification\n"
            "- Technical improvements\n"
            "- Better organization or structure"
        )
        
        final_polish_base = (
            "Based on the update suggestions below, create a final polished version "
            "of the design document. Incorporate the suggested improvements while "
            "maintaining professional quality and completeness."
        )
        
        # Incorporate prompt instructions if provided (only for the first agent/polisher)
        if prompt_instructions:
            polish_instructions = f"{polish_base}\n\n## Polishing Instructions\n\n{prompt_instructions}"
        else:
            polish_instructions = polish_base
        
        # Other steps use base instructions only
        updater_instructions = updater_base
        final_polish_instructions = final_polish_base
        
        pipeline.add_step(
            name="polish",
            agent=polisher_agent,
            transform=lambda document: (
                f"{polish_instructions}\n\n"
                f"DOCUMENT:\n{document}"
            ),
            metadata={"role": "polisher", "task": "initial_polish"}
        )
        
        pipeline.add_step(
            name="suggest_updates",
            agent=updater_agent,
            transform=lambda polished_doc: (
                f"{updater_instructions}\n\n"
                f"POLISHED DOCUMENT:\n{polished_doc}\n\n"
                f"Provide your suggestions in a clear, actionable format."
            ),
            metadata={"role": "updater", "task": "suggest_updates"}
        )
        
        pipeline.add_step(
            name="final_polish",
            agent=final_polisher_agent,
            transform=lambda suggestions: (
                f"{final_polish_instructions}\n\n"
                f"UPDATE SUGGESTIONS:\n{suggestions}\n\n"
                f"Provide the complete, final polished design document."
            ),
            metadata={"role": "final_polisher", "task": "final_polish"}
        )
        
        return pipeline
    
    @staticmethod
    def error_analysis_chain(analyzer_agent: BaseAgent) -> Pipeline:
        """
        Error analysis chain: Analyzes error and generates prompt with solution.
        
        Takes error information and uses an agent to:
        1. Analyze and isolate the issue
        2. Generate a prompt describing the understanding
        3. Suggest a solution
        
        Args:
            analyzer_agent: Agent for analyzing the error
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="error-analysis-chain")
        
        pipeline.add_step(
            name="analyze_error",
            agent=analyzer_agent,
            transform=lambda error_text: (
                f"Analyze the following error from a log file. Your task is to:\n\n"
                f"1. Identify the root cause of the error\n"
                f"2. Isolate the specific issue (what went wrong and why)\n"
                f"3. Understand the context and impact\n"
                f"4. Suggest a concrete solution to fix the issue\n\n"
                f"ERROR INFORMATION:\n{error_text}\n\n"
                f"Provide a comprehensive analysis that includes:\n"
                f"- Clear identification of the root cause\n"
                f"- Explanation of why this error occurred\n"
                f"- Specific steps to resolve the issue\n"
                f"- Prevention strategies if applicable"
            ),
            metadata={"role": "error_analyzer", "task": "analyze_and_suggest"}
        )
        
        return pipeline

    @staticmethod
    def agent_config_error_analysis_chain(analyzer_agent: BaseAgent) -> Pipeline:
        """
        Agent configuration error analysis workflow
        
        Analyzes agent configuration errors to:
        1. Identify the root cause of configuration failures
        2. Understand what's wrong with the agent setup
        3. Suggest specific fixes
        
        Args:
            analyzer_agent: Agent for analyzing the configuration errors
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="agent-config-error-analysis-chain")
        
        pipeline.add_step(
            name="analyze_config_error",
            agent=analyzer_agent,
            transform=lambda error_info: (
                f"Analyze the following agent configuration error. Your task is to:\n\n"
                f"1. Identify why the agent configuration is invalid or failing\n"
                f"2. Determine what specific configuration issue is causing the problem\n"
                f"3. Understand the relationship between the error and the agent configuration\n"
                f"4. Provide specific, actionable steps to fix the configuration\n\n"
                f"AGENT CONFIGURATION ERROR:\n{error_info}\n\n"
                f"Provide a comprehensive analysis that includes:\n"
                f"- Clear identification of the configuration problem\n"
                f"- Explanation of why this configuration is invalid\n"
                f"- Specific steps to correct the agent configuration\n"
                f"- Verification steps to ensure the fix works\n"
                f"- Prevention tips for avoiding similar issues in the future"
            ),
            metadata={"role": "config_error_analyzer", "task": "analyze_and_fix"}
        )
        
        return pipeline

    @staticmethod
    def iterative_refinement(
        agents: List[BaseAgent],
        iterations: int = 2
    ) -> Pipeline:
        """
        Iterative refinement workflow
        
        Args:
            agents: List of agents to cycle through
            iterations: Number of iterations
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="iterative-refinement")
        
        for i in range(iterations):
            for j, agent in enumerate(agents):
                pipeline.add_step(
                    name=f"iteration-{i+1}-agent-{j+1}",
                    agent=agent,
                    transform=lambda x: f"Refine this further:\n\n{x}",
                    metadata={
                        "iteration": i + 1,
                        "agent_index": j + 1
                    }
                )
        
        return pipeline


class PipelineComparison:
    """Compare different pipeline configurations"""
    
    def __init__(self, framework=None):
        """
        Initialize pipeline comparison
        
        Args:
            framework: Optional AgentFramework for storage
        """
        self.framework = framework
        self.results: List[PipelineResult] = []
    
    def add_result(self, result: PipelineResult):
        """Add a pipeline result to comparison"""
        self.results.append(result)
    
    def compare(self) -> Dict[str, Any]:
        """
        Compare pipeline results
        
        Returns:
            Comparison dictionary
        """
        if not self.results:
            return {"error": "No results to compare"}
        
        comparisons = []
        for result in self.results:
            comparisons.append({
                "pipeline_id": result.pipeline_id,
                "steps": len(result.steps),
                "total_time_ms": result.total_time_ms,
                "total_tokens": result.total_tokens,
                "total_cost": result.total_cost,
                "timestamp": result.timestamp.isoformat()
            })
        
        # Rankings
        by_speed = sorted(comparisons, key=lambda x: x["total_time_ms"])
        by_cost = sorted(comparisons, key=lambda x: x["total_cost"])
        by_tokens = sorted(comparisons, key=lambda x: x["total_tokens"])
        
        return {
            "total_pipelines": len(self.results),
            "comparisons": comparisons,
            "rankings": {
                "by_speed": by_speed,
                "by_cost": by_cost,
                "by_tokens": by_tokens
            },
            "averages": {
                "time_ms": sum(c["total_time_ms"] for c in comparisons) / len(comparisons),
                "tokens": sum(c["total_tokens"] for c in comparisons) / len(comparisons),
                "cost": sum(c["total_cost"] for c in comparisons) / len(comparisons)
            }
        }
    
    def generate_report(self) -> str:
        """Generate markdown report"""
        comparison = self.compare()
        
        if "error" in comparison:
            return comparison["error"]
        
        lines = [
            "# Pipeline Comparison Report",
            "",
            f"**Total Pipelines**: {comparison['total_pipelines']}",
            "",
            "## Averages",
            "",
            f"- **Time**: {comparison['averages']['time_ms']:.2f}ms",
            f"- **Tokens**: {comparison['averages']['tokens']:.0f}",
            f"- **Cost**: ${comparison['averages']['cost']:.4f}",
            "",
            "## Rankings",
            "",
            "### By Speed",
            ""
        ]
        
        for i, p in enumerate(comparison['rankings']['by_speed'][:5], 1):
            lines.append(f"{i}. Pipeline `{p['pipeline_id']}` - {p['total_time_ms']}ms")
        
        lines.extend([
            "",
            "### By Cost",
            ""
        ])
        
        for i, p in enumerate(comparison['rankings']['by_cost'][:5], 1):
            lines.append(f"{i}. Pipeline `{p['pipeline_id']}` - ${p['total_cost']:.4f}")
        
        return "\n".join(lines)

