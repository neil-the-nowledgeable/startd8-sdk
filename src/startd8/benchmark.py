"""
Benchmark runner and comparison tools
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import asyncio
from datetime import datetime, timezone

from .framework import AgentFramework
from .models import Prompt, AgentResponse, ComparisonMetrics
from .agents import BaseAgent
from .events import EventBus, EventType, Event


class BenchmarkRunner:
    """Run benchmarks across multiple agents"""
    
    def __init__(self, framework: AgentFramework):
        """
        Initialize benchmark runner
        
        Args:
            framework: AgentFramework instance
        """
        self.framework = framework
    
    async def arun_benchmark(
        self,
        prompt_content: str,
        agents: List[BaseAgent],
        benchmark_name: str,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Run a benchmark across multiple agents asynchronously
        
        Args:
            prompt_content: The prompt to send to all agents
            agents: List of agents to test
            benchmark_name: Name for the benchmark
            version: Prompt version
            tags: Optional tags
            parallel: If True, run agents in parallel; if False, run sequentially
            
        Returns:
            Dictionary with benchmark results
        """
        # Create prompt
        prompt = self.framework.create_prompt(
            content=prompt_content,
            version=version,
            tags=tags or []
        )
        
        # Create benchmark
        benchmark = self.framework.create_benchmark(
            name=benchmark_name,
            prompt_id=prompt.id
        )
        
        # Emit benchmark created event
        EventBus.emit(Event(
            type=EventType.BENCHMARK_CREATED,
            source="BenchmarkRunner",
            data={
                "benchmark_id": benchmark.id,
                "benchmark_name": benchmark_name,
                "agent_count": len(agents)
            },
            correlation_id=benchmark.id
        ))
        
        # Run agents
        from .logging_config import get_logger
        
        logger = get_logger(__name__)
        responses = []
        
        async def run_single_agent(agent: BaseAgent) -> Optional[AgentResponse]:
            """Helper to run a single agent and handle errors"""
            try:
                response = await agent.acreate_response(
                    prompt_id=prompt.id,
                    prompt=prompt_content,
                    metadata={"benchmark_id": benchmark.id}
                )
                self.framework.storage.save_response(response)
                logger.info(
                    f"Agent {agent.name} completed benchmark",
                    extra={"agent_name": agent.name, "benchmark_id": benchmark.id}
                )
                return response
            except Exception as e:
                logger.error(
                    f"Error running agent {agent.name}: {e}",
                    exc_info=True,
                    extra={"agent_name": agent.name, "benchmark_id": benchmark.id}
                )
                return None
        
        if parallel:
            # Run all agents in parallel
            results = await asyncio.gather(
                *[run_single_agent(agent) for agent in agents],
                return_exceptions=True
            )
            responses = []
            for r in results:
                if isinstance(r, BaseException) and not isinstance(r, Exception):
                    raise r
                if r is not None and not isinstance(r, Exception):
                    responses.append(r)
        else:
            # Run agents sequentially
            for agent in agents:
                response = await run_single_agent(agent)
                if response:
                    responses.append(response)
        
        # Complete benchmark
        summary = f"Tested {len(agents)} agents on prompt '{benchmark_name}'. {len(responses)} responses collected."
        self.framework.complete_benchmark(benchmark.id, summary=summary)
        
        # Emit benchmark completed event
        EventBus.emit(Event(
            type=EventType.BENCHMARK_COMPLETED,
            source="BenchmarkRunner",
            data={
                "benchmark_id": benchmark.id,
                "benchmark_name": benchmark_name,
                "response_count": len(responses)
            },
            correlation_id=benchmark.id
        ))
        
        # Generate comparison
        comparison = self.framework.compare_responses(prompt.id)
        
        return {
            "benchmark": benchmark.model_dump(),
            "prompt": prompt.model_dump(),
            "responses": [r.model_dump() for r in responses],
            "comparison": comparison
        }
    
    def run_benchmark(
        self,
        prompt_content: str,
        agents: List[BaseAgent],
        benchmark_name: str,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a benchmark across multiple agents (synchronous wrapper)
        
        Args:
            prompt_content: The prompt to send to all agents
            agents: List of agents to test
            benchmark_name: Name for the benchmark
            version: Prompt version
            tags: Optional tags
            
        Returns:
            Dictionary with benchmark results
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.arun_benchmark(
                prompt_content=prompt_content,
                agents=agents,
                benchmark_name=benchmark_name,
                version=version,
                tags=tags,
                parallel=True
            ))

        # Running inside an existing event loop (e.g. Jupyter/FastAPI).
        # Bridge by running the coroutine in a new thread + event loop.
        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> Dict[str, Any]:
            return asyncio.run(self.arun_benchmark(
                prompt_content=prompt_content,
                agents=agents,
                benchmark_name=benchmark_name,
                version=version,
                tags=tags,
                parallel=True
            ))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()


class ComparisonReport:
    """Generate detailed comparison reports"""
    
    def __init__(self, framework: AgentFramework):
        """
        Initialize comparison report generator
        
        Args:
            framework: AgentFramework instance
        """
        self.framework = framework
    
    def generate_markdown_report(
        self,
        prompt_id: str,
        output_file: Optional[Path] = None
    ) -> str:
        """
        Generate a markdown report comparing responses
        
        Args:
            prompt_id: ID of prompt to compare
            output_file: Optional file to write report to
            
        Returns:
            Markdown report string
        """
        comparison = self.framework.compare_responses(prompt_id)
        # Convert ResponseComparison to dict for backward compatibility
        if hasattr(comparison, 'model_dump'):
            comparison = comparison.model_dump()
        prompt = self.framework.get_prompt(prompt_id)
        responses = self.framework.list_responses(prompt_id=prompt_id)
        
        # Build markdown
        lines = [
            "# Agent Response Comparison Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Prompt",
            "",
            f"**ID:** `{prompt_id}`",
            f"**Version:** {prompt.version if prompt else 'N/A'}",
            f"**Tags:** {', '.join(prompt.tags) if prompt and prompt.tags else 'None'}",
            "",
            "```",
            prompt.content if prompt else "Prompt not found",
            "```",
            "",
            "## Statistics",
            "",
            f"- **Total Responses:** {comparison['total_responses']}",
            f"- **Average Response Time:** {comparison['avg_response_time_ms']:.2f}ms",
            f"- **Total Tokens Used:** {comparison['total_tokens']}",
            "",
            "## Rankings",
            "",
            "### By Speed",
            "",
        ]
        
        for i, entry in enumerate(comparison['rankings']['by_speed'], 1):
            lines.append(f"{i}. **{entry['agent']}** - {entry['time_ms']}ms")
        
        lines.extend([
            "",
            "### By Token Efficiency",
            "",
        ])
        
        for i, entry in enumerate(comparison['rankings']['by_token_efficiency'], 1):
            lines.append(f"{i}. **{entry['agent']}** - {entry['tokens']} tokens")
        
        lines.extend([
            "",
            "## Detailed Responses",
            "",
        ])
        
        for response in responses:
            lines.extend([
                f"### {response.agent_name} ({response.model})",
                "",
                f"- **Response Time:** {response.response_time_ms}ms",
                f"- **Tokens:** {response.token_usage.total if response.token_usage else 'N/A'}",
                f"- **Cost Estimate:** ${response.token_usage.cost_estimate:.4f}" if response.token_usage else "- **Cost:** N/A",
                "",
                "#### Response",
                "",
                "```",
                response.response,
                "```",
                "",
            ])
        
        report = "\n".join(lines)
        
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                f.write(report)
        
        return report
    
    def generate_metrics(self, prompt_id: str) -> ComparisonMetrics:
        """
        Generate comparison metrics for a prompt
        
        Args:
            prompt_id: ID of prompt
            
        Returns:
            ComparisonMetrics object
        """
        responses = self.framework.list_responses(prompt_id=prompt_id)
        
        if not responses:
            return ComparisonMetrics(
                total_responses=0,
                avg_response_time_ms=0.0,
                avg_tokens_per_second=0.0,
                total_tokens=0,
                total_cost_estimate=0.0,
                models_used=[]
            )
        
        total_response_time = sum(r.response_time_ms for r in responses)
        total_tokens = sum(r.token_usage.total if r.token_usage else 0 for r in responses)
        total_cost = sum(r.token_usage.cost_estimate if r.token_usage else 0 for r in responses)
        
        # Calculate tokens per second
        tokens_per_sec = [r.tokens_per_second for r in responses if r.token_usage]
        avg_tokens_per_sec = sum(tokens_per_sec) / len(tokens_per_sec) if tokens_per_sec else 0.0
        
        # Find fastest, most efficient, cheapest
        fastest = min(responses, key=lambda r: r.response_time_ms)
        responses_with_tokens = [r for r in responses if r.token_usage]
        most_efficient = min(responses_with_tokens, key=lambda r: r.token_usage.total) if responses_with_tokens else None
        cheapest = min(responses_with_tokens, key=lambda r: r.token_usage.cost_estimate) if responses_with_tokens else None
        
        return ComparisonMetrics(
            total_responses=len(responses),
            avg_response_time_ms=total_response_time / len(responses),
            avg_tokens_per_second=avg_tokens_per_sec,
            total_tokens=total_tokens,
            total_cost_estimate=total_cost,
            models_used=list(set(r.model for r in responses)),
            fastest_agent=fastest.agent_name,
            most_efficient_agent=most_efficient.agent_name if most_efficient else None,
            cheapest_agent=cheapest.agent_name if cheapest else None
        )

