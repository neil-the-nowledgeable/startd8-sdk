"""
Agent resolution utilities for the StartD8 SDK.

Provides functions to resolve agent specifications (strings like "anthropic:claude-sonnet-4-20250514")
into BaseAgent instances. Used by workflows, CLI, and other SDK components.
"""

from typing import List, Optional, Union

from ..agents import BaseAgent
from ..providers import ProviderRegistry
from ..exceptions import ConfigurationError


# Backwards-compatible CLI shorthands
_AGENT_ALIASES = {
    # "claude" used to mean "an Anthropic default model"
    "claude": ("anthropic", None),
    # "gpt4" shorthand - now maps to gpt-4o (flagship model)
    "gpt4": ("openai", "gpt-4o"),
}


def _available_providers_hint() -> str:
    """Generate hint text listing available providers."""
    providers = ProviderRegistry.list_providers()
    if not providers:
        return "No providers discovered."
    return "Available providers: " + ", ".join(sorted(providers))


def resolve_agent_spec(
    spec: str,
    *,
    name: Optional[str] = None,
    validate: bool = True,
    **agent_config,
) -> BaseAgent:
    """
    Resolve an agent specification string into a BaseAgent instance.

    Supports multiple formats:
    - Provider name: "openai", "anthropic", "mock", "gemini", "ollama"
    - Model ID: "gpt-4", "claude-sonnet-4-20250514", "mock-model"
    - Provider:model format: "anthropic:claude-sonnet-4-20250514"
    - Legacy aliases: "claude", "gpt4"

    Args:
        spec: Agent specification string
        name: Optional custom name for the agent
        validate: Whether to validate provider config (default True)

    Returns:
        BaseAgent instance

    Raises:
        ConfigurationError: If spec cannot be resolved

    Example:
        # By provider name (uses default model)
        agent = resolve_agent_spec("anthropic")

        # By provider:model
        agent = resolve_agent_spec("anthropic:claude-sonnet-4-20250514")

        # By model ID (auto-detects provider)
        agent = resolve_agent_spec("gpt-4")

        # With custom name
        agent = resolve_agent_spec("mock", name="test-agent")
    """
    ProviderRegistry.discover()

    spec_raw = spec.strip()
    spec_lower = spec_raw.lower()

    # Back-compat aliases
    if spec_lower in _AGENT_ALIASES:
        provider_name, model_override = _AGENT_ALIASES[spec_lower]
        provider = ProviderRegistry.get_provider(provider_name)
        if not provider:
            raise ConfigurationError(
                f"Provider '{provider_name}' not available for alias '{spec_raw}'. "
                f"{_available_providers_hint()}"
            )
        model = model_override or (
            provider.supported_models[0] if provider.supported_models else None
        )
        if not model:
            raise ConfigurationError(
                f"Provider '{provider.name}' has no supported models."
            )
        if validate:
            provider.validate_config({})
        return provider.create_agent(model, name=name, **agent_config)

    # Explicit provider:model format
    if ":" in spec_raw:
        provider_name, model = spec_raw.split(":", 1)
        provider = ProviderRegistry.get_provider(provider_name.lower())
        if not provider:
            raise ConfigurationError(
                f"Unknown provider '{provider_name}' in '{spec_raw}'. "
                f"{_available_providers_hint()}"
            )
        if validate:
            provider.validate_config({})
        return provider.create_agent(model, name=name, **agent_config)

    # Provider name only (use default model)
    provider = ProviderRegistry.get_provider(spec_lower)
    if provider:
        model = provider.supported_models[0] if provider.supported_models else None
        if not model:
            raise ConfigurationError(
                f"Provider '{provider.name}' has no supported models."
            )
        if validate:
            provider.validate_config({})
        return provider.create_agent(model, name=name, **agent_config)

    # Model ID (auto-detect provider)
    provider = ProviderRegistry.find_provider_for_model(spec_lower)
    if provider:
        if validate:
            provider.validate_config({})
        return provider.create_agent(spec_lower, name=name, **agent_config)

    raise ConfigurationError(
        f"Unknown agent/model '{spec_raw}'. "
        f"Pass a provider name (e.g. 'openai'), a model id (e.g. 'gpt-4'), "
        f"or 'provider:model' format (e.g. 'anthropic:claude-sonnet-4-20250514'). "
        f"{_available_providers_hint()}"
    )


def resolve_agent_specs(
    specs: List[str],
    *,
    validate: bool = True,
    **agent_config,
) -> List[BaseAgent]:
    """
    Resolve multiple agent specifications into BaseAgent instances.

    Args:
        specs: List of agent specification strings
        validate: Whether to validate provider configs
        **agent_config: Additional config forwarded to provider.create_agent()

    Returns:
        List of BaseAgent instances

    Raises:
        ConfigurationError: If any spec cannot be resolved

    Example:
        agents = resolve_agent_specs([
            "anthropic:claude-sonnet-4-20250514",
            "openai:gpt-4",
            "mock"
        ])
    """
    return [
        resolve_agent_spec(spec, validate=validate, **agent_config)
        for spec in specs
    ]


def resolve_agents(
    agents_or_specs: Union[List[str], List[BaseAgent], None],
    *,
    validate: bool = True,
    **agent_config,
) -> List[BaseAgent]:
    """
    Resolve a mixed list of agent specs or instances into BaseAgent instances.

    This is useful for workflows that accept either pre-resolved agents
    or spec strings.

    Args:
        agents_or_specs: List of strings or BaseAgent instances, or None
        validate: Whether to validate provider configs for string specs
        **agent_config: Additional config forwarded to provider.create_agent()

    Returns:
        List of BaseAgent instances (empty list if input is None)

    Example:
        # Mixed input
        agents = resolve_agents([
            "anthropic:claude-sonnet-4-20250514",  # String spec
            existing_gpt_agent,                    # Pre-resolved agent
        ])
    """
    if agents_or_specs is None:
        return []

    result = []
    for item in agents_or_specs:
        if isinstance(item, str):
            result.append(resolve_agent_spec(item, validate=validate, **agent_config))
        elif isinstance(item, BaseAgent):
            result.append(item)
        else:
            raise ConfigurationError(
                f"Expected agent spec string or BaseAgent instance, got {type(item)}"
            )

    return result
