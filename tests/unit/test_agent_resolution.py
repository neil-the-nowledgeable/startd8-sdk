"""
Tests for resolve_agent_spec() timeout_config and retry_config forwarding.

Verifies that timeout and retry configuration can be passed through
resolve_agent_spec(), resolve_agent_specs(), and resolve_agents()
to the underlying provider.create_agent() call, and that backward
compatibility is preserved when these parameters are omitted.
"""

import pytest

from startd8.agents.pool import TimeoutConfig
from startd8.utils.retry import RetryConfig
from startd8.utils.agent_resolution import (
    resolve_agent_spec,
    resolve_agent_specs,
    resolve_agents,
)
from startd8.providers import ProviderRegistry


@pytest.fixture(autouse=True)
def _discover_providers():
    """Ensure providers are discovered before each test."""
    ProviderRegistry.discover()


# ---------------------------------------------------------------------------
# resolve_agent_spec
# ---------------------------------------------------------------------------


class TestResolveAgentSpecTimeoutConfig:
    """timeout_config is forwarded to the created agent."""

    def test_timeout_config_forwarded_provider_colon_model(self):
        tc = TimeoutConfig(read=600.0)
        agent = resolve_agent_spec("mock:mock-model", timeout_config=tc)
        assert agent.timeout_config is tc
        assert agent.timeout_config.read == 600.0

    def test_timeout_config_forwarded_provider_name_only(self):
        tc = TimeoutConfig(connect=2.0, read=120.0, write=15.0, pool=5.0)
        agent = resolve_agent_spec("mock", timeout_config=tc)
        assert agent.timeout_config is tc
        assert agent.timeout_config.connect == 2.0

    def test_timeout_config_none_by_default(self):
        agent = resolve_agent_spec("mock:mock-model")
        assert agent.timeout_config is None


class TestResolveAgentSpecRetryConfig:
    """retry_config is forwarded to the created agent."""

    def test_retry_config_forwarded(self):
        rc = RetryConfig(max_attempts=5, base_delay=2.0)
        agent = resolve_agent_spec("mock:mock-model", retry_config=rc)
        assert agent.retry_config is rc
        assert agent.retry_config.max_attempts == 5
        assert agent.retry_config.base_delay == 2.0

    def test_retry_config_none_by_default(self):
        agent = resolve_agent_spec("mock:mock-model")
        assert agent.retry_config is None


class TestResolveAgentSpecBothConfigs:
    """Both timeout_config and retry_config can be passed together."""

    def test_both_forwarded(self):
        tc = TimeoutConfig(read=600.0)
        rc = RetryConfig(max_attempts=7)
        agent = resolve_agent_spec(
            "mock:mock-model", timeout_config=tc, retry_config=rc
        )
        assert agent.timeout_config is tc
        assert agent.retry_config is rc


class TestResolveAgentSpecBackwardCompat:
    """Existing callers without timeout/retry params still work."""

    def test_basic_provider_colon_model(self):
        agent = resolve_agent_spec("mock:mock-model")
        assert agent.model == "mock-model"

    def test_basic_provider_name(self):
        agent = resolve_agent_spec("mock")
        assert agent.model == "mock-model"  # first supported model

    def test_with_custom_name(self):
        agent = resolve_agent_spec("mock:mock-model", name="my-agent")
        assert agent.name == "my-agent"

    def test_extra_kwargs_still_work(self):
        """Verify that arbitrary **agent_config kwargs are not broken."""
        # MockAgent accepts **kwargs, so unknown keys don't crash
        agent = resolve_agent_spec("mock:mock-model", some_custom_key="value")
        assert agent.model == "mock-model"


# ---------------------------------------------------------------------------
# resolve_agent_specs  (batch helper)
# ---------------------------------------------------------------------------


class TestResolveAgentSpecs:
    """Batch resolution forwards timeout/retry to every agent."""

    def test_timeout_config_applied_to_all(self):
        tc = TimeoutConfig(read=999.0)
        agents = resolve_agent_specs(
            ["mock:mock-model", "mock:mock-fast"],
            timeout_config=tc,
        )
        assert len(agents) == 2
        for agent in agents:
            assert agent.timeout_config is tc

    def test_retry_config_applied_to_all(self):
        rc = RetryConfig(max_attempts=10)
        agents = resolve_agent_specs(
            ["mock:mock-model", "mock:mock-fast"],
            retry_config=rc,
        )
        assert len(agents) == 2
        for agent in agents:
            assert agent.retry_config is rc

    def test_no_configs_backward_compat(self):
        agents = resolve_agent_specs(["mock:mock-model"])
        assert len(agents) == 1
        assert agents[0].timeout_config is None
        assert agents[0].retry_config is None


# ---------------------------------------------------------------------------
# resolve_agents  (mixed-input helper)
# ---------------------------------------------------------------------------


class TestResolveAgents:
    """Mixed-input resolution forwards timeout/retry for string specs."""

    def test_string_specs_get_configs(self):
        tc = TimeoutConfig(read=500.0)
        rc = RetryConfig(max_attempts=3)
        agents = resolve_agents(
            ["mock:mock-model"],
            timeout_config=tc,
            retry_config=rc,
        )
        assert len(agents) == 1
        assert agents[0].timeout_config is tc
        assert agents[0].retry_config is rc

    def test_pre_resolved_agents_pass_through(self):
        """Pre-resolved BaseAgent instances are returned as-is."""
        from startd8.agents import MockAgent

        existing = MockAgent(name="pre-existing", model="mock-model")
        agents = resolve_agents(
            [existing],
            timeout_config=TimeoutConfig(read=999.0),
        )
        assert len(agents) == 1
        assert agents[0] is existing
        # Pre-resolved agent retains its original config (None here)
        assert agents[0].timeout_config is None

    def test_none_input_returns_empty(self):
        agents = resolve_agents(None, timeout_config=TimeoutConfig(read=1.0))
        assert agents == []
