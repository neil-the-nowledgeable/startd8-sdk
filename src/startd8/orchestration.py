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
        metadata: Optional[Dict[str, Any]] = None
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
                
                # Run agent asynchronously
                step_start = time.time()
                response_text, response_time_ms, token_usage = await step.agent.agenerate(step_input)
                step_end = time.time()
                
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
                        }
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
            
        except Exception as e:
            # Emit pipeline error event
            EventBus.emit(Event(
                type=EventType.PIPELINE_ERROR,
                source="Pipeline",
                data={
                    "pipeline_id": pipeline_id,
                    "error": str(e)
                },
                correlation_id=pipeline_id
            ))
            raise
    
    def run(self, initial_input: str, store: bool = True) -> PipelineResult:
        """
        Run the pipeline (synchronous wrapper)
        
        Args:
            initial_input: Initial input to first agent
            store: Whether to store results in framework (if available)
            
        Returns:
            PipelineResult with all step details
        """
        return asyncio.run(self.arun(initial_input, store))
    
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

