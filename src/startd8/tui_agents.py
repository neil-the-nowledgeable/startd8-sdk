"""Shared TUI helpers for workflow-aware agent discovery."""

from __future__ import annotations

from typing import Any, Dict, List

from .tui_improved import AgentConfigTester
from .workflows.registry import WorkflowDescriptor


def get_ready_agents_for_workflow(desc: WorkflowDescriptor) -> List[Dict[str, Any]]:
    """
    Return agents that appear ready for the requested workflow.

    The current implementation reuses AgentConfigTester for a consistent
    readiness signal across TUI surfaces. Future capability gating can
    filter on desc.supports_multi_agent or tags.
    """
    try:
        readiness = AgentConfigTester.test_all()
    except Exception:
        return []

    ready_agents: List[Dict[str, Any]] = []
    for agent_id, report in readiness.items():
        if not report.get("configured") or not report.get("working"):
            continue
        ready_agents.append(
            {
                "id": agent_id,
                "name": report.get("name", agent_id),
                "provider": agent_id,
                "supports_stream": report.get("supports_stream", False),
                "supports_multi_agent": desc.supports_multi_agent,
            }
        )
    return ready_agents


def validate_agent_support(desc: WorkflowDescriptor, agent_info: Dict[str, Any]) -> None:
    """Basic capability guardrails for workflow-agent compatibility."""
    if not desc.supports_multi_agent and agent_info.get("mode") == "multi":
        raise ValueError(f"{desc.id} does not support multi-agent runs")


__all__ = ["get_ready_agents_for_workflow", "validate_agent_support"]
