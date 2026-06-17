"""Regression: localhost/no-auth endpoints must get a non-empty sentinel api_key.

The installed `openai` client rejects api_key=None ("api_key must be set"), so a keyless
localhost endpoint (Ollama, llama.cpp, LM Studio) must receive a sentinel the server ignores.
Constructing the client does NOT make a network call, so these are offline-safe.
"""

from unittest.mock import patch

from startd8.agents import OpenAICompatibleAgent
from startd8.providers import ProviderRegistry


def test_localhost_gets_sentinel_key_not_none():
    agent = OpenAICompatibleAgent(
        name="local", model="m", api_key=None, base_url="http://localhost:11434/v1",
    )
    assert agent.client.api_key  # non-empty (sentinel), not None → no OpenAIError
    assert agent.client.api_key == "not-needed"


def test_127_0_0_1_also_sentinel():
    agent = OpenAICompatibleAgent(
        name="local", model="m", api_key=None, base_url="http://127.0.0.1:8080/v1",
    )
    assert agent.client.api_key == "not-needed"


def test_ollama_provider_create_agent_does_not_raise():
    """FR/bug: create_agent('ollama', ...) used to raise OpenAIError(api_key) for localhost."""
    with patch.dict("os.environ", {}, clear=True):
        ProviderRegistry.discover()
        provider = ProviderRegistry.get_provider("ollama")
        agent = provider.create_agent("qwen2.5-coder:7b")
    assert agent.base_url.startswith("http://localhost:11434")
    assert agent.client.api_key  # sentinel applied, construction succeeded


def test_explicit_key_on_localhost_is_kept():
    """The sentinel path is guarded by `not actual_api_key`, so an explicitly provided key is
    KEPT (the sentinel only fills in when no key was given)."""
    agent = OpenAICompatibleAgent(
        name="local", model="m", api_key="sk-real", base_url="http://localhost:1234/v1",
    )
    assert agent.client.api_key == "sk-real"
