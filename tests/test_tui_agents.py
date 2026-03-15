from startd8.tui_agents import get_ready_agents_for_workflow
from startd8.workflows.registry import WORKFLOW_CATALOG


class _DummyTester:
    @staticmethod
    def test_all():
        return {
            "ready-agent": {"configured": True, "working": True, "name": "Ready"},
            "not-configured": {"configured": False, "working": False, "name": "Nope"},
        }


def test_get_ready_agents_handles_basic_readiness(monkeypatch):
    desc = WORKFLOW_CATALOG["iterative-dev"]
    monkeypatch.setattr("startd8.tui_agents.AgentConfigTester", _DummyTester)

    ready = get_ready_agents_for_workflow(desc)

    assert len(ready) == 1
    assert ready[0]["id"] == "ready-agent"
    assert ready[0]["supports_multi_agent"] is desc.supports_multi_agent
