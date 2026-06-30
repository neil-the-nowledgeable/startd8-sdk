"""Flagship single-source-of-truth tests (FLAGSHIP_DEFAULT_AGENT_REQUIREMENTS).

Enforces, by test rather than metadata (FR-3), that each vendor's flagship is the
agreed newest-STABLE model and is never a preview/experimental build.
"""
import re

import pytest

from startd8.model_catalog import canonical_provider, get_flagship, get_latest_model

# FR-9 / D-1 / D-2: the agreed flagship per cloud vendor.
EXPECTED_FLAGSHIP = {
    "anthropic": "anthropic:claude-opus-4-8",   # D-2: Opus, NOT Fable-5
    "openai": "openai:gpt-5.5",
    "gemini": "gemini:gemini-2.5-pro",           # D-1: stable, NOT 3.x-*-preview
    "mistral": "mistral:mistral-large-latest",
    "deepseek": "deepseek:deepseek-chat",
}

PREVIEW_MARKER = re.compile(r"preview|exp|-pre|alpha|beta", re.IGNORECASE)


@pytest.mark.unit
@pytest.mark.parametrize("provider,expected", EXPECTED_FLAGSHIP.items())
def test_flagship_matches_agreed_set(provider, expected):
    assert get_flagship(provider) == expected


@pytest.mark.unit
@pytest.mark.parametrize("provider", list(EXPECTED_FLAGSHIP))
def test_flagship_is_not_a_preview(provider):
    spec = get_flagship(provider)
    assert spec is not None
    model = spec.split(":", 1)[1]
    assert not PREVIEW_MARKER.search(model), f"{provider} flagship '{model}' looks like a preview"


@pytest.mark.unit
def test_get_flagship_wraps_get_latest_model():
    # FR-1: get_flagship is the named wrapper over get_latest_model(tier='flagship').
    for provider in EXPECTED_FLAGSHIP:
        assert get_flagship(provider) == get_latest_model(provider, tier="flagship")


@pytest.mark.unit
def test_get_flagship_normalizes_aliases():
    # FR-10: agent aliases resolve to the same flagship as the provider name.
    assert get_flagship("claude") == EXPECTED_FLAGSHIP["anthropic"]
    assert get_flagship("gpt4") == EXPECTED_FLAGSHIP["openai"]


@pytest.mark.unit
def test_get_flagship_unknown_is_none():
    # FR-4: unknown provider -> None (callers must handle explicitly).
    assert get_flagship("totally-unknown-vendor") is None


@pytest.mark.unit
def test_canonical_provider_mapping():
    # FR-10: aliases + identity + unknown.
    assert canonical_provider("claude") == "anthropic"
    assert canonical_provider("gpt4") == "openai"
    assert canonical_provider("GPT-4") == "openai"
    assert canonical_provider("gemini") == "gemini"
    assert canonical_provider("anthropic") == "anthropic"
    assert canonical_provider("nope") is None
    assert canonical_provider("") is None
