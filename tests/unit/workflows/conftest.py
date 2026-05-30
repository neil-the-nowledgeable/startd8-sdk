"""Shared fixtures for prime prompt externalization tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def lead_workflow():
    """Create a LeadContractorWorkflow instance for testing."""
    from startd8.workflows.builtin.primary_contractor_workflow import (
        LeadContractorWorkflow,
    )
    return LeadContractorWorkflow()


@pytest.fixture()
def mock_agent():
    """Create a mock agent that returns a canned spec response."""
    agent = MagicMock()
    token_usage = MagicMock()
    token_usage.input = 100
    token_usage.output = 200
    agent.generate.return_value = ("## Task Summary\nTest spec", 500, token_usage)
    agent.model = "test-model"
    agent.name = "test-agent"
    return agent
