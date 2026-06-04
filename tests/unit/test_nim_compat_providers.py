"""nim / openai-compatible providers (previously stale entry points → AttributeError on discover).

`pyproject.toml` registered `nim`/`openai-compatible` entry points but the classes were never
written, so `ProviderRegistry.discover()` logged an AttributeError for each. These were created as
thin wrappers over OpenAICompatibleAgent (mirroring MistralProvider/OllamaProvider).
"""

import pytest

from startd8.agents import OpenAICompatibleAgent
from startd8.exceptions import ConfigurationError
from startd8.providers import ProviderRegistry
from startd8.providers.openai import NIMProvider, OpenAICompatibleProvider


def test_entry_points_resolve_via_discovery():
    ProviderRegistry.discover()
    names = ProviderRegistry.list_providers()
    # both formerly-broken entry points now load (no AttributeError) and register
    assert "nim" in names
    assert "openai-compatible" in names
    assert ProviderRegistry.get_provider("nim") is not None
    assert ProviderRegistry.get_provider("openai-compatible") is not None


def test_nim_creates_openai_compatible_agent():
    agent = NIMProvider().create_agent("nvidia/nemotron-3-nano-30b-a3b", api_key="k")
    assert isinstance(agent, OpenAICompatibleAgent)


def test_nim_requires_api_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        NIMProvider().validate_config({})
    assert NIMProvider().validate_config({"api_key": "k"}) is True


def test_compat_requires_base_url(monkeypatch):
    monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
    with pytest.raises(ConfigurationError):
        OpenAICompatibleProvider().validate_config({})
    assert OpenAICompatibleProvider().validate_config({"base_url": "http://x/v1"}) is True
