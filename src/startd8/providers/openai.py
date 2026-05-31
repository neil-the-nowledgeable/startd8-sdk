"""
OpenAI-family provider implementations.

This module provides:
- OpenAIProvider: OpenAI's hosted API, with optional delegation to a
  compatible endpoint when ``base_url`` is provided
- OpenAICompatibleProvider: generic provider for arbitrary OpenAI-compatible
  endpoints (Together, Groq, self-hosted gateways, etc.)
- NIMProvider: NVIDIA NIM-specific OpenAI-compatible provider
- OllamaProvider: local Ollama runtime provider
"""

from typing import List, Dict, Any, Optional
import ipaddress
import os
import logging
from pathlib import Path
from urllib.parse import urlparse

from ..agents import GPT4Agent, OpenAICompatibleAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Provider for OpenAI GPT models"""
    
    # Official OpenAI models (hardcoded baseline)
    HARDCODED_MODELS = [
        # GPT-5.x family (Latest)
        "gpt-5.5-pro",          # Most capable flagship
        "gpt-5.5",              # Standard flagship
        "gpt-5.4-mini",         # Fast, cost-efficient
        "gpt-5.4-nano",         # Ultra-fast, lowest cost
        "gpt-5.3-codex",        # Coding-optimized
        # GPT-4.1 family (April 2025, 1M context)
        "gpt-4.1",              # Best for coding and instruction following
        "gpt-4.1-mini",         # Fast, cost-efficient
        "gpt-4.1-nano",         # Ultra-fast, lowest cost
        # o-series reasoning models
        "o3",                   # Most powerful reasoning model
        "o3-mini",              # Small reasoning model
        "o3-pro",               # Extended thinking for complex problems
        "o4-mini",              # Fast, cost-efficient reasoning (best on AIME)
        # GPT-4o family (flagship)
        "gpt-4o",               # Latest flagship, versatile
        "gpt-4o-mini",          # Fast, affordable
        # Legacy models (still functional but outdated)
        "gpt-4-turbo",          # Previous generation
        "gpt-4-turbo-preview",  # Preview version
        "gpt-4",                # Original GPT-4 (retired from ChatGPT April 2025)
        "gpt-3.5-turbo",        # Budget option
    ]
    
    @classmethod
    def _get_models(cls) -> List[str]:
        """Get merged list of hardcoded and discovered models"""
        try:
            from ..model_discovery import ModelDiscoveryService
            # Use default config dir
            discovery = ModelDiscoveryService()
            return discovery.merge_models('openai', cls.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to load discovered models (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "openai", "operation": "model_discovery"}
            )
            return cls.HARDCODED_MODELS.copy()
        except Exception as e:
            logger.warning(
                f"Unexpected error loading discovered models: {e}",
                exc_info=True,
                extra={"provider": "openai", "operation": "model_discovery"}
            )
            return cls.HARDCODED_MODELS.copy()
    
    @classmethod
    def _get_models_instance(cls) -> List[str]:
        """Get models for an instance"""
        return cls._get_models()
    
    @property
    def MODELS(self) -> List[str]:
        """Dynamic models list that includes discovered models"""
        return self._get_models_instance()
    
    # Model metadata
    MODEL_INFO = {
        # GPT-4.1 family (1M context)
        "gpt-4.1": {
            "name": "GPT-4.1",
            "context_window": 1000000,
            "max_output_tokens": 32768,
            "cost_per_1m_input": 2.00,
            "cost_per_1m_output": 8.00,
        },
        "gpt-4.1-mini": {
            "name": "GPT-4.1 Mini",
            "context_window": 1000000,
            "max_output_tokens": 32768,
            "cost_per_1m_input": 0.40,
            "cost_per_1m_output": 1.60,
        },
        "gpt-4.1-nano": {
            "name": "GPT-4.1 Nano",
            "context_window": 1000000,
            "max_output_tokens": 32768,
            "cost_per_1m_input": 0.10,
            "cost_per_1m_output": 0.40,
        },
        # o-series reasoning models
        "o3": {
            "name": "o3",
            "context_window": 200000,
            "max_output_tokens": 100000,
            "cost_per_1m_input": 10.00,
            "cost_per_1m_output": 40.00,
        },
        "o3-mini": {
            "name": "o3-mini",
            "context_window": 200000,
            "max_output_tokens": 100000,
            "cost_per_1m_input": 1.10,
            "cost_per_1m_output": 4.40,
        },
        "o3-pro": {
            "name": "o3-pro",
            "context_window": 200000,
            "max_output_tokens": 100000,
            "cost_per_1m_input": 20.00,
            "cost_per_1m_output": 80.00,
        },
        "o4-mini": {
            "name": "o4-mini",
            "context_window": 200000,
            "max_output_tokens": 100000,
            "cost_per_1m_input": 1.10,
            "cost_per_1m_output": 4.40,
        },
        # GPT-4o family
        "gpt-4o": {
            "name": "GPT-4o",
            "context_window": 128000,
            "max_output_tokens": 16384,
            "cost_per_1m_input": 2.50,
            "cost_per_1m_output": 10.00,
        },
        "gpt-4o-mini": {
            "name": "GPT-4o Mini",
            "context_window": 128000,
            "max_output_tokens": 16384,
            "cost_per_1m_input": 0.15,
            "cost_per_1m_output": 0.60,
        },
        # Legacy models
        "gpt-4-turbo": {
            "name": "GPT-4 Turbo",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 10.00,
            "cost_per_1m_output": 30.00,
            "deprecated": True,
            "replacement": "gpt-4o",
        },
        "gpt-4-turbo-preview": {
            "name": "GPT-4 Turbo Preview",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 10.00,
            "cost_per_1m_output": 30.00,
            "deprecated": True,
            "replacement": "gpt-4o",
        },
        "gpt-4": {
            "name": "GPT-4 (legacy)",
            "context_window": 8192,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 30.00,
            "cost_per_1m_output": 60.00,
            "deprecated": True,
            "replacement": "gpt-4o",
        },
        "gpt-3.5-turbo": {
            "name": "GPT-3.5 Turbo",
            "context_window": 16384,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 0.50,
            "cost_per_1m_output": 1.50,
        },
    }
    
    @property
    def name(self) -> str:
        return "openai"
    
    @property
    def display_name(self) -> str:
        return "OpenAI GPT"
    
    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()
    
    def is_model_new(self, model: str) -> bool:
        """Check if a model is newly discovered (not in hardcoded list)"""
        try:
            from ..model_discovery import ModelDiscoveryService
            discovery = ModelDiscoveryService()
            return discovery.is_model_new('openai', model, self.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to check if model is new (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "openai", "model": model, "operation": "is_model_new"}
            )
            return False
        except Exception as e:
            logger.warning(
                f"Unexpected error checking if model is new: {e}",
                exc_info=True,
                extra={"provider": "openai", "model": model, "operation": "is_model_new"}
            )
            return False
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ):
        """
        Create an OpenAI GPT agent instance.
        
        When ``base_url`` is provided, returns an ``OpenAICompatibleAgent``
        targeting that endpoint (useful for NVIDIA NIM, Azure OpenAI, or
        any OpenAI-compatible API). Otherwise returns a standard
        ``GPT4Agent`` pointing at api.openai.com.
        
        Args:
            model: GPT model identifier
            name: Optional agent name (defaults to model-based name)
            **config: Configuration options
                - api_key: OpenAI API key (or use OPENAI_API_KEY env var)
                - base_url: Custom API endpoint (triggers OpenAICompatibleAgent)
                - max_tokens: Maximum tokens to generate (default 16384)
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        """
        # Decision 37A: be permissive about model IDs.
        if model not in self.supported_models:
            logger.warning(
                f"OpenAIProvider: model '{model}' not in supported_models list; "
                f"continuing anyway."
            )
        
        if name is None:
            name = model.replace("gpt-", "gpt").replace("-preview", "")
        
        base_url = config.get('base_url')
        if base_url is not None:
            return OpenAICompatibleAgent(
                name=name,
                model=model,
                api_key=config.get('api_key'),
                api_key_env=config.get('api_key_env'),
                base_url=base_url,
                max_tokens=config.get('max_tokens', 16384),
                cost_tracker=config.get('cost_tracker'),
                budget_manager=config.get('budget_manager'),
                timeout_config=config.get('timeout_config'),
                retry_config=config.get('retry_config'),
                enable_retry=config.get('enable_retry', False),
                use_connection_pool=config.get('use_connection_pool', False),
                system_prompt=config.get('system_prompt'),
            )
        
        return GPT4Agent(
            name=name,
            model=model,
            api_key=config.get('api_key'),
            max_tokens=config.get('max_tokens', 16384),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager'),
            timeout_config=config.get('timeout_config'),
            retry_config=config.get('retry_config'),
            enable_retry=config.get('enable_retry', False),
            use_connection_pool=config.get('use_connection_pool', False),
            system_prompt=config.get('system_prompt'),
        )

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate OpenAI configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        base_url = config.get('base_url')
        api_key_env = config.get('api_key_env')
        env_api_key = os.getenv(api_key_env) if api_key_env else None

        # Check for API key
        api_key = config.get('api_key') or env_api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            if base_url:
                raise ConfigurationError(
                    "API key required for authenticated custom endpoint. "
                    "Pass api_key, set api_key_env, or set OPENAI_API_KEY. "
                    "For NVIDIA NIM, prefer NIMProvider or set api_key_env='NVIDIA_API_KEY'."
                )
            raise ConfigurationError(
                "OpenAI API key required. "
                "Set OPENAI_API_KEY environment variable or pass api_key in config."
            )
        
        # Validate max_tokens if provided
        max_tokens = config.get('max_tokens')
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ConfigurationError(
                    f"max_tokens must be a positive integer, got: {max_tokens}"
                )
            # Many OpenAI models support >4k completion tokens; let API enforce exact limits.
            # We keep a conservative-but-high cap to prevent accidental runaway configs.
            if max_tokens > 16384:
                raise ConfigurationError(
                    f"max_tokens ({max_tokens}) exceeds maximum allowed (16384)"
                )
        
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Return required environment variables for the default OpenAI path."""
        return ['OPENAI_API_KEY']
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific GPT model"""
        return self.MODEL_INFO.get(model)
    
    def supports_streaming(self) -> bool:
        """OpenAI supports streaming responses"""
        return True
    
    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        """Get OpenAI capabilities"""
        return [
            'text-generation',
            'function-calling',
            'vision',  # GPT-4 Turbo and Vision models
            'json-mode',
        ]


def _base_url_is_local(base_url: str) -> bool:
    """Treat loopback and RFC1918 private addresses as local — these don't
    require an API key. Captures localhost, 127.0.0.0/8, 10.0.0.0/8,
    172.16.0.0/12, 192.168.0.0/16, plus IPv6 loopback/private. Hostnames
    other than 'localhost' are conservatively treated as non-local.
    """
    host = urlparse(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


class OpenAICompatibleProvider:
    """Provider for arbitrary OpenAI-compatible endpoints.

    Use this when you want provider-registry ergonomics with a custom
    ``base_url`` and optional custom API-key env var.
    """

    DEFAULT_MODELS = ["custom-model"]

    @property
    def name(self) -> str:
        return "openai-compatible"

    @property
    def display_name(self) -> str:
        return "OpenAI-Compatible Endpoint"

    @property
    def supported_models(self) -> List[str]:
        return self.DEFAULT_MODELS.copy()

    def create_agent(
        self,
        model: str,
        name: Optional[str] = None,
        **config,
    ) -> OpenAICompatibleAgent:
        """Create an agent for a custom OpenAI-compatible endpoint."""
        if name is None:
            name = model.replace("/", "-")

        base_url = config.get('base_url')
        if not base_url:
            raise ConfigurationError(
                "base_url is required for OpenAICompatibleProvider."
            )

        return OpenAICompatibleAgent(
            name=name,
            model=model,
            api_key=config.get('api_key'),
            api_key_env=config.get('api_key_env'),
            base_url=base_url,
            max_tokens=config.get('max_tokens', 16384),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager'),
            timeout_config=config.get('timeout_config'),
            retry_config=config.get('retry_config'),
            enable_retry=config.get('enable_retry', False),
            use_connection_pool=config.get('use_connection_pool', False),
            system_prompt=config.get('system_prompt'),
        )

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate a custom OpenAI-compatible endpoint configuration."""
        base_url = config.get('base_url')
        if not base_url:
            raise ConfigurationError(
                "base_url is required for OpenAICompatibleProvider."
            )

        api_key_env = config.get('api_key_env')
        api_key = config.get('api_key')
        env_api_key = os.getenv(api_key_env) if api_key_env else None
        is_local = _base_url_is_local(base_url)

        if not is_local and not (api_key or env_api_key):
            raise ConfigurationError(
                "API key required for non-local OpenAI-compatible endpoint. "
                "Pass api_key or set api_key_env."
            )

        max_tokens = config.get('max_tokens')
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ConfigurationError(
                    f"max_tokens must be a positive integer, got: {max_tokens}"
                )
        return True

    def get_required_env_vars(self) -> List[str]:
        """OpenAI-compatible endpoints are config-driven; no fixed env var."""
        return []

    def supports_streaming(self) -> bool:
        return True

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        return ['text-generation', 'json-mode', 'custom-endpoint']


class NIMProvider(OpenAICompatibleProvider):
    """Provider for NVIDIA NIM OpenAI-compatible endpoints."""

    NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
    NIM_MODELS = [
        "nvidia/nemotron-3-nano-30b-a3b",
    ]

    @property
    def name(self) -> str:
        return "nim"

    @property
    def display_name(self) -> str:
        return "NVIDIA NIM"

    @property
    def supported_models(self) -> List[str]:
        return self.NIM_MODELS.copy()

    def create_agent(
        self,
        model: str,
        name: Optional[str] = None,
        **config,
    ) -> OpenAICompatibleAgent:
        """Create an agent for NVIDIA NIM."""
        config = dict(config)
        config.setdefault('base_url', self.NIM_BASE_URL)
        config.setdefault('api_key_env', 'NVIDIA_API_KEY')
        return super().create_agent(model=model, name=name, **config)

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate NVIDIA NIM configuration."""
        api_key = config.get('api_key')
        api_key_env = config.get('api_key_env', 'NVIDIA_API_KEY')
        env_api_key = os.getenv(api_key_env)
        if not (api_key or env_api_key):
            raise ConfigurationError(
                "NVIDIA API key required. "
                "Set NVIDIA_API_KEY or pass api_key in config."
            )

        nim_config = dict(config)
        nim_config.setdefault('base_url', self.NIM_BASE_URL)
        nim_config.setdefault('api_key_env', api_key_env)
        return super().validate_config(nim_config)

    def get_required_env_vars(self) -> List[str]:
        return ['NVIDIA_API_KEY']


class OllamaProvider:
    """Provider for Ollama (local LLM runtime).

    For authenticated remote endpoints like NVIDIA NIM, prefer
    ``NIMProvider`` or ``OpenAICompatibleProvider`` so validation and
    metadata match the endpoint semantics.
    """
    
    # Common Ollama models (user may have others installed)
    COMMON_MODELS = [
        "llama2",
        "llama2:13b",
        "llama2:70b",
        "codellama",
        "mistral",
        "mixtral",
        "phi",
        "neural-chat",
    ]
    
    @property
    def name(self) -> str:
        return "ollama"
    
    @property
    def display_name(self) -> str:
        return "Ollama (Local)"
    
    @property
    def supported_models(self) -> List[str]:
        return self.COMMON_MODELS.copy()
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> OpenAICompatibleAgent:
        """
        Create an Ollama agent instance.
        
        Args:
            model: Ollama model identifier
            name: Optional agent name
            **config: Configuration options
                - base_url: API URL (default: http://localhost:11434/v1)
                - max_tokens: Maximum tokens to generate
        """
        if name is None:
            name = f"ollama-{model}"
        
        default_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        # Ensure the /v1 suffix for OpenAI-compatible endpoint
        if not default_host.rstrip('/').endswith('/v1'):
            default_host = default_host.rstrip('/') + '/v1'
        base_url = config.get('base_url', default_host)
        
        return OpenAICompatibleAgent(
            name=name,
            model=model,
            api_key=config.get('api_key'),
            base_url=base_url,
            max_tokens=config.get('max_tokens', 4096),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager'),
            timeout_config=config.get('timeout_config'),
            retry_config=config.get('retry_config'),
            enable_retry=config.get('enable_retry', False),
            use_connection_pool=config.get('use_connection_pool', False),
            system_prompt=config.get('system_prompt'),
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Ollama configuration."""
        base_url = config.get('base_url')
        if base_url and not any(host in base_url for host in ('localhost', '127.0.0.1')):
            api_key = config.get('api_key')
            api_key_env = config.get('api_key_env')
            env_api_key = os.getenv(api_key_env) if api_key_env else None
            if not (api_key or env_api_key):
                raise ConfigurationError(
                    "Remote non-local endpoint passed to OllamaProvider without API key. "
                    "Prefer NIMProvider or OpenAICompatibleProvider for authenticated endpoints."
                )
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Ollama doesn't require environment variables for local use"""
        return []
    
    def supports_streaming(self) -> bool:
        return True
    
    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        return ['text-generation', 'local-execution']
