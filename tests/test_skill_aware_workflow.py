"""
Unit tests for SkillAwareWorkflow.
"""

from startd8.agents import BaseAgent
from startd8.models import AgentResponse, TokenUsage
from startd8.workflows import (
    SkillAwareWorkflow,
    SkillWorkflowResult,
)


class FakeSkillAgent(BaseAgent):
    """Minimal skill-like agent for testing without MCP dependencies."""

    def __init__(self, name: str, skill_id: str, response: str):
        super().__init__(name=name, model="fake-model")
        self.skill_id = skill_id
        self._response = response
        self.agent_name = name

    async def agenerate(self, prompt: str):
        """Async implementation required by BaseAgent; returns tuple."""
        return self._response, 5, TokenUsage(input=10, output=5, total=15)

    def generate(self, prompt: str) -> AgentResponse:
        """Return AgentResponse to satisfy IterativeDevWorkflow expectations."""
        return AgentResponse(
            id="resp-1",
            prompt_id="prompt-1",
            agent_name=self.name,
            model=self.model,
            response=self._response,
            response_time_ms=12,
            token_usage=TokenUsage(input=10, output=5, total=15),
            metadata={},
        )

    def is_healthy(self) -> bool:  # pragma: no cover - simple hook
        return True


def test_skill_aware_workflow_collects_skill_metadata():
    """Workflow returns skill-aware result with metrics populated."""
    dev_agent = FakeSkillAgent(
        name="dev-skill",
        skill_id="skill-dev",
        response="print('hello world')",
    )
    review_agent = FakeSkillAgent(
        name="review-skill",
        skill_id="skill-review",
        response="PASS/FAIL: PASS\nSCORE: 95\nISSUES:\nSUGGESTIONS:\nREVIEW: OK",
    )

    workflow = SkillAwareWorkflow(
        developer_agent=dev_agent,
        reviewer_agent=review_agent,
        max_iterations=1,
    )

    result = workflow.run("Add greeting")

    assert isinstance(result, SkillWorkflowResult)
    assert result.successful is True
    assert result.developer_skill_id == "skill-dev"
    assert result.reviewer_skill_id == "skill-review"
    # Metrics are collected for both agents
    per_skill = result.skill_metrics.skill_metrics
    assert per_skill["skill-dev"]["executions"] == 1
    assert per_skill["skill-review"]["executions"] == 1
    # Cache hits are unknown so miss counters increase
    assert result.skill_metrics.cache_misses == 2


def test_get_agent_status_reports_skill_ids():
    """Status exposes skill ids and health flags."""
    dev_agent = FakeSkillAgent(
        name="dev-skill",
        skill_id="skill-dev",
        response="print('hi')",
    )
    review_agent = FakeSkillAgent(
        name="review-skill",
        skill_id="skill-review",
        response="PASS/FAIL: PASS\nSCORE: 100\nISSUES:\nSUGGESTIONS:\nREVIEW: OK",
    )

    workflow = SkillAwareWorkflow(dev_agent, review_agent)
    status = workflow.get_agent_status()

    assert status["developer"]["skill_id"] == "skill-dev"
    assert status["reviewer"]["skill_id"] == "skill-review"
    assert status["developer"]["healthy"] is True
    assert status["reviewer"]["healthy"] is True

