"""
Skill-aware iterative workflow with enhanced metrics and controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from ..agents import BaseAgent
from ..iterative_workflow import (
    IterativeDevWorkflow,
    IterativeWorkflowResult,
)
from ..logging_config import get_logger
from ..skills import SkillAgent

logger = get_logger(__name__)


@dataclass
class SkillWorkflowMetrics:
    """Extended metrics for skill-based workflows."""

    total_time_ms: int = 0
    total_iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    circuit_breaker_events: int = 0
    skill_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_skill_execution(
        self,
        skill_id: str,
        time_ms: int,
        input_tokens: int,
        output_tokens: int,
        cache_hit: bool,
        circuit_state: Optional[str] = None,
    ) -> None:
        """Record metrics for a single skill execution."""
        if skill_id not in self.skill_metrics:
            self.skill_metrics[skill_id] = {
                "executions": 0,
                "total_time_ms": 0,
                "total_tokens": 0,
                "cache_hits": 0,
            }

        self.skill_metrics[skill_id]["executions"] += 1
        self.skill_metrics[skill_id]["total_time_ms"] += time_ms
        self.skill_metrics[skill_id]["total_tokens"] += input_tokens + output_tokens

        if cache_hit:
            self.skill_metrics[skill_id]["cache_hits"] += 1
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        if circuit_state and circuit_state.lower() != "closed":
            self.circuit_breaker_events += 1


@dataclass
class SkillWorkflowResult(IterativeWorkflowResult):
    """Extended result with skill-specific metrics."""

    skill_metrics: SkillWorkflowMetrics = field(default_factory=SkillWorkflowMetrics)
    developer_skill_id: Optional[str] = None
    reviewer_skill_id: Optional[str] = None

    def get_summary(self) -> Dict[str, Any]:
        """Get extended workflow summary."""
        base_summary = super().get_summary()
        base_summary["skill_metrics"] = {
            "cache_hit_rate": (
                self.skill_metrics.cache_hits
                / (self.skill_metrics.cache_hits + self.skill_metrics.cache_misses)
                if (self.skill_metrics.cache_hits + self.skill_metrics.cache_misses) > 0
                else 0
            ),
            "circuit_breaker_events": self.skill_metrics.circuit_breaker_events,
            "per_skill": self.skill_metrics.skill_metrics,
        }
        base_summary["agents"] = {
            "developer": self.developer_skill_id or "traditional",
            "reviewer": self.reviewer_skill_id or "traditional",
        }
        return base_summary


class SkillAwareWorkflow(IterativeDevWorkflow):
    """
    Enhanced iterative workflow with skill-specific features.

    Extends IterativeDevWorkflow with:
    - Skill detection and specialized handling
    - Enhanced metrics collection
    - Circuit breaker monitoring hooks (placeholder)
    - Cache utilization tracking
    """

    def __init__(
        self,
        developer_agent: BaseAgent,
        reviewer_agent: BaseAgent,
        max_iterations: int = 3,
        dev_prompt_template: Optional[str] = None,
        review_prompt_template: Optional[str] = None,
        on_iteration_complete: Optional[callable] = None,
        enable_skill_metrics: bool = True,
        fallback_on_circuit_open: bool = True,
    ):
        super().__init__(
            developer_agent=developer_agent,
            reviewer_agent=reviewer_agent,
            max_iterations=max_iterations,
            dev_prompt_template=dev_prompt_template,
            review_prompt_template=review_prompt_template,
            on_iteration_complete=on_iteration_complete,
        )

        self.enable_skill_metrics = enable_skill_metrics
        self.fallback_on_circuit_open = fallback_on_circuit_open

        self._developer_is_skill, self._developer_skill_id = self._detect_skill_agent(
            developer_agent
        )
        self._reviewer_is_skill, self._reviewer_skill_id = self._detect_skill_agent(
            reviewer_agent
        )

        logger.info(
            "SkillAwareWorkflow initialized",
            extra={
                "developer_is_skill": self._developer_is_skill,
                "reviewer_is_skill": self._reviewer_is_skill,
                "developer_skill": self._developer_skill_id,
                "reviewer_skill": self._reviewer_skill_id,
            },
        )

    def run(
        self, task_description: str, context: Optional[Dict[str, Any]] = None
    ) -> SkillWorkflowResult:
        """Run the skill-aware workflow and attach skill metrics."""
        base_result = super().run(task_description, context)
        skill_metrics = SkillWorkflowMetrics(
            total_time_ms=base_result.total_time_ms,
            total_iterations=base_result.total_iterations,
            total_input_tokens=base_result.total_dev_tokens,
            total_output_tokens=base_result.total_review_tokens,
            estimated_cost=base_result.total_cost,
        )

        result = SkillWorkflowResult(
            workflow_id=base_result.workflow_id,
            task_description=base_result.task_description,
            status=base_result.status,
            iterations=base_result.iterations,
            final_code=base_result.final_code,
            final_review=base_result.final_review,
            total_iterations=base_result.total_iterations,
            successful=base_result.successful,
            created_at=base_result.created_at,
            completed_at=base_result.completed_at,
            total_time_ms=base_result.total_time_ms,
            total_dev_tokens=base_result.total_dev_tokens,
            total_review_tokens=base_result.total_review_tokens,
            total_cost=base_result.total_cost,
            skill_metrics=skill_metrics,
            developer_skill_id=self._developer_skill_id,
            reviewer_skill_id=self._reviewer_skill_id,
        )

        if self.enable_skill_metrics:
            self._collect_skill_metrics(result)

        return result

    def _collect_skill_metrics(self, result: SkillWorkflowResult) -> None:
        """Collect skill-specific metrics from iterations."""
        for iteration in result.iterations:
            cache_hit = False
            circuit_state = "closed"
            if self._developer_is_skill:
                cache_hit = bool(getattr(self.developer_agent, "_last_cache_hit", False))
                circuit_state = getattr(
                    getattr(self.developer_agent, "mcp_gateway", None),
                    "get_circuit_state",
                    lambda _sid: circuit_state,
                )(self._developer_skill_id) if self._developer_skill_id else circuit_state

            if self._developer_is_skill and iteration.dev_tokens:
                result.skill_metrics.add_skill_execution(
                    skill_id=self._developer_skill_id or "developer",
                    time_ms=iteration.dev_time_ms,
                    input_tokens=iteration.dev_tokens.input,
                    output_tokens=iteration.dev_tokens.output,
                    cache_hit=cache_hit,
                    circuit_state=circuit_state,
                )

            if self._reviewer_is_skill and iteration.review_tokens:
                cache_hit_review = bool(
                    getattr(self.reviewer_agent, "_last_cache_hit", False)
                )
                circuit_state_review = getattr(
                    getattr(self.reviewer_agent, "mcp_gateway", None),
                    "get_circuit_state",
                    lambda _sid: circuit_state,
                )(self._reviewer_skill_id) if self._reviewer_skill_id else circuit_state

                result.skill_metrics.add_skill_execution(
                    skill_id=self._reviewer_skill_id or "reviewer",
                    time_ms=iteration.review_time_ms,
                    input_tokens=iteration.review_tokens.input,
                    output_tokens=iteration.review_tokens.output,
                    cache_hit=cache_hit_review,
                    circuit_state=circuit_state_review,
                )

    def _detect_skill_agent(self, agent: BaseAgent) -> tuple[bool, Optional[str]]:
        """
        Detect whether an agent is skill-based.

        Treats true SkillAgent instances and agents exposing a skill_id attribute
        as skill-enabled for forward compatibility with stubs/mocks.
        """
        if isinstance(agent, SkillAgent):
            return True, getattr(agent, "skill_id", None)
        if hasattr(agent, "skill_id"):
            return True, getattr(agent, "skill_id")
        return False, None

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents in the workflow."""
        status = {
            "developer": {
                "name": getattr(self.developer_agent, "name", "developer"),
                "type": "skill" if self._developer_is_skill else "traditional",
            },
            "reviewer": {
                "name": getattr(self.reviewer_agent, "name", "reviewer"),
                "type": "skill" if self._reviewer_is_skill else "traditional",
            },
        }

        if self._developer_is_skill:
            status["developer"]["skill_id"] = self._developer_skill_id
            status["developer"]["healthy"] = self._get_health(self.developer_agent)
            status["developer"]["gateway"] = self._get_gateway_health(self.developer_agent)

        if self._reviewer_is_skill:
            status["reviewer"]["skill_id"] = self._reviewer_skill_id
            status["reviewer"]["healthy"] = self._get_health(self.reviewer_agent)
            status["reviewer"]["gateway"] = self._get_gateway_health(self.reviewer_agent)

        return status

    @staticmethod
    def _get_health(agent: BaseAgent) -> bool:
        """Best-effort health signal for agents that expose an is_healthy hook."""
        is_healthy = getattr(agent, "is_healthy", None)
        if callable(is_healthy):
            try:
                return bool(is_healthy())
            except Exception:  # pragma: no cover - defensive
                return False
        return True

    @staticmethod
    def _get_gateway_health(agent: BaseAgent) -> Dict[str, Any]:
        """Best-effort gateway health using get_stats if available."""
        gw = getattr(agent, "mcp_gateway", None)
        if gw and hasattr(gw, "get_stats"):
            try:
                stats = gw.get_stats()
                return {
                    "initialized": stats.get("initialized"),
                    "global_circuit": stats.get("global_circuit_state"),
                    "skills_registered": stats.get("skills_registered"),
                }
            except Exception:  # pragma: no cover - defensive
                return {"initialized": False, "global_circuit": "unknown"}
        return {}

