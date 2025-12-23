"""
Provider registry for managing agent providers
"""

from typing import Dict, Optional, List, Type, Any
import logging
import sys

from .protocol import AgentProvider
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Central registry for agent providers.
    
    Supports both programmatic registration and auto-discovery
    via Python entry points.
    
    Example entry_points configuration in pyproject.toml:
    
        [project.entry-points."startd8.providers"]
        anthropic = "startd8.providers.anthropic:AnthropicProvider"
        openai = "startd8.providers.openai:OpenAIProvider"
        custom = "my_package.providers:CustomProvider"
    
    Usage:
        # Auto-discover and register all providers
        ProviderRegistry.discover()
        
        # List available providers
        providers = ProviderRegistry.list_providers()
        
        # Get a specific provider
        provider = ProviderRegistry.get_provider("anthropic")
        
        # Create an agent from a provider
        agent = ProviderRegistry.create_agent(
            provider_name="anthropic",
            model="claude-3-opus-20240229",
            api_key="..."
        )
    """
    
    _instance: Optional['ProviderRegistry'] = None
    _providers: Dict[str, AgentProvider] = {}
    _discovered: bool = False
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, provider: Any) -> None:
        """
        Register a provider instance.
        
        Args:
            provider: Provider instance implementing AgentProvider protocol
            
        Raises:
            TypeError: If provider doesn't implement AgentProvider
            ValueError: If provider name is already registered (unless force=True)
        
        Example:
            provider = MyProvider()
            ProviderRegistry.register(provider)
        """
        # Use permissive duck-typing checks rather than strict Protocol checks.
        # This keeps it easy for users to register lightweight custom providers.
        required_attrs = (
            "name",
            "display_name",
            "supported_models",
            "create_agent",
            "validate_config",
            "get_required_env_vars",
        )
        if not all(hasattr(provider, attr) for attr in required_attrs):
            raise TypeError(
                f"{provider} does not implement AgentProvider protocol. "
                f"Required: name, display_name, supported_models, create_agent, "
                f"validate_config, get_required_env_vars"
            )
        
        name = provider.name.lower()
        if name in cls._providers:
            logger.warning(f"Overwriting existing provider: {name}")
        
        cls._providers[name] = provider
        logger.info(
            f"Registered provider: {name} ({provider.display_name}) "
            f"with {len(provider.supported_models)} models"
        )
    
    @classmethod
    def discover(cls, force: bool = False) -> None:
        """
        Auto-discover providers via entry points.
        
        Providers can be registered via setuptools entry points in pyproject.toml
        or setup.py. This method loads all registered providers.
        
        Args:
            force: Re-discover even if already discovered
        
        Example entry_points in pyproject.toml:
            [project.entry-points."startd8.providers"]
            anthropic = "startd8.providers.anthropic:AnthropicProvider"
        """
        if cls._discovered and not force:
            logger.debug("Providers already discovered, skipping")
            return
        
        discovered_count = 0
        
        # Try Python 3.10+ importlib.metadata
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                
                try:
                    eps = entry_points(group='startd8.providers')
                except TypeError:
                    # Fallback for older interface
                    eps = entry_points().get('startd8.providers', [])
            else:
                # Python 3.9 fallback
                try:
                    from importlib_metadata import entry_points
                    eps = entry_points().get('startd8.providers', [])
                except ImportError:
                    logger.warning(
                        "importlib_metadata not available. "
                        "Install with: pip install importlib-metadata"
                    )
                    eps = []
            
            for ep in eps:
                try:
                    logger.debug(f"Loading provider from entry point: {ep.name}")
                    provider_class = ep.load()
                    provider = provider_class()
                    cls.register(provider)
                    discovered_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to load provider {ep.name}: {e}",
                        exc_info=True
                    )
        
        except Exception as e:
            logger.debug(f"Entry point discovery failed: {e}")
        
        # Also register built-in providers
        cls._register_builtin_providers()
        
        cls._discovered = True
        logger.info(
            f"Provider discovery complete. "
            f"Discovered {discovered_count} external providers, "
            f"total {len(cls._providers)} providers registered"
        )
    
    @classmethod
    def _register_builtin_providers(cls) -> None:
        """Register built-in providers that ship with the SDK"""
        try:
            from .anthropic import AnthropicProvider
            cls.register(AnthropicProvider())
            logger.debug("Registered built-in Anthropic provider")
        except ImportError as e:
            logger.debug(f"Anthropic provider not available: {e}")
        
        try:
            from .openai import OpenAIProvider
            cls.register(OpenAIProvider())
            logger.debug("Registered built-in OpenAI provider")
        except ImportError as e:
            logger.debug(f"OpenAI provider not available: {e}")

        try:
            from .openai import OllamaProvider
            cls.register(OllamaProvider())
            logger.debug("Registered built-in Ollama provider")
        except ImportError as e:
            logger.debug(f"Ollama provider not available: {e}")
        
        try:
            from .mock import MockProvider
            cls.register(MockProvider())
            logger.debug("Registered built-in Mock provider")
        except ImportError as e:
            logger.debug(f"Mock provider not available: {e}")

        try:
            from .gemini import GeminiProvider
            cls.register(GeminiProvider())
            logger.debug("Registered built-in Gemini provider")
        except ImportError as e:
            logger.debug(f"Gemini provider not available: {e}")
    
    @classmethod
    def get_provider(cls, name: str) -> Optional[AgentProvider]:
        """
        Get provider by name.
        
        Args:
            name: Provider identifier (case-insensitive)
            
        Returns:
            Provider instance or None if not found
        
        Example:
            provider = ProviderRegistry.get_provider("anthropic")
            if provider:
                agent = provider.create_agent("claude-3-opus-20240229")
        """
        cls.discover()
        return cls._providers.get(name.lower())
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """
        List all registered provider names.
        
        Returns:
            List of provider identifiers
        
        Example:
            providers = ProviderRegistry.list_providers()
            # ['anthropic', 'openai', 'mock']
        """
        cls.discover()
        return list(cls._providers.keys())
    
    @classmethod
    def list_all_models(cls) -> Dict[str, List[str]]:
        """
        List all models grouped by provider.
        
        Returns:
            Dictionary mapping provider names to lists of model IDs
        
        Example:
            models = ProviderRegistry.list_all_models()
            # {
            #     'anthropic': ['claude-3-opus-20240229', ...],
            #     'openai': ['gpt-4', 'gpt-3.5-turbo', ...]
            # }
        """
        cls.discover()
        return {
            name: provider.supported_models 
            for name, provider in cls._providers.items()
        }
    
    @classmethod
    def find_provider_for_model(cls, model: str) -> Optional[AgentProvider]:
        """
        Find which provider supports a given model.
        
        Args:
            model: Model identifier
            
        Returns:
            Provider that supports the model, or None
        
        Example:
            provider = ProviderRegistry.find_provider_for_model("gpt-4")
            # Returns OpenAIProvider
        """
        cls.discover()
        model_lower = model.lower()
        
        for provider in cls._providers.values():
            if model_lower in [m.lower() for m in provider.supported_models]:
                return provider
        
        return None
    
    @classmethod
    def create_agent(
        cls, 
        provider_name: str, 
        model: str, 
        **config
    ) -> 'BaseAgent':
        """
        Convenience method to create an agent.
        
        Args:
            provider_name: Provider identifier
            model: Model identifier
            **config: Provider-specific configuration
            
        Returns:
            Configured agent instance
            
        Raises:
            ConfigurationError: If provider not found or config invalid
        
        Example:
            agent = ProviderRegistry.create_agent(
                provider_name="anthropic",
                model="claude-3-opus-20240229",
                api_key="...",
                max_tokens=4096
            )
        """
        provider = cls.get_provider(provider_name)
        if provider is None:
            available = cls.list_providers()
            raise ConfigurationError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {', '.join(available)}"
            )
        
        try:
            return provider.create_agent(model, **config)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to create agent from provider {provider_name}: {e}"
            ) from e
    
    @classmethod
    def get_provider_info(
        cls,
        provider_name: str,
        model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a provider.
        
        Args:
            provider_name: Provider identifier
            
        Returns:
            Dictionary with provider information or None
        
        Example:
            info = ProviderRegistry.get_provider_info("anthropic")
            # {
            #     'name': 'anthropic',
            #     'display_name': 'Anthropic Claude',
            #     'models': [...],
            #     'env_vars': ['ANTHROPIC_API_KEY']
            # }
        """
        provider = cls.get_provider(provider_name)
        if provider is None:
            return None
        
        # Capabilities are optionally model-specific. Prefer passing model when available.
        try:
            capabilities = provider.get_capabilities(model)  # type: ignore[arg-type]
        except TypeError:
            capabilities = provider.get_capabilities()

        info: Dict[str, Any] = {
            'name': provider.name,
            'display_name': provider.display_name,
            'models': provider.supported_models,
            'env_vars': provider.get_required_env_vars(),
            'capabilities': capabilities,
            'streaming': provider.supports_streaming()
        }

        if model:
            info["model"] = model

        return info
    
    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered providers (useful for testing).
        
        Example:
            ProviderRegistry.clear()
            ProviderRegistry.register(MyTestProvider())
        """
        cls._providers.clear()
        cls._discovered = False
        logger.debug("Cleared provider registry")
