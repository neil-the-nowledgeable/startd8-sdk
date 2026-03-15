"""Shared runner utilities for cataloged workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List

if TYPE_CHECKING:
    from .registry import WorkflowDescriptor


def run_for_agents(
    desc: "WorkflowDescriptor",
    agents: Iterable[str],
    *,
    framework: Any = None,
    agent_registry: Any = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    Execute a workflow for each agent name and return structured results.

    Args:
        desc: Workflow descriptor from the catalog.
        agents: Agent identifiers to execute.
        framework: Optional shared framework for workflows that need it.
        agent_registry: Optional registry used by the runner wrappers.
        kwargs: Additional inputs forwarded to the workflow runner.
    """
    results: List[Dict[str, Any]] = []
    for agent_name in agents:
        runner_kwargs = dict(kwargs)
        runner_kwargs.setdefault("developer", agent_name)
        result = desc.runner(
            agent_registry=agent_registry,
            framework=framework,
            **runner_kwargs,
        )
        results.append({"agent": agent_name, "result": result})
    return results


__all__ = ["run_for_agents"]
