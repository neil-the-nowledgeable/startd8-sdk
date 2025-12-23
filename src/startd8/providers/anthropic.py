"""
Anthropic Claude provider implementation
"""

from typing import List, Dict, Any, Optional
import os
import logging
from pathlib import Path

from ..agents import ClaudeAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Provider for Anthropic Claude models"""
    
    # Official Claude models (hardcoded baseline)
    HARDCODED_MODELS = [
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229", 
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ]
    
    @classmethod
    def _get_models(cls) -> List[str]:
        """Get merged list of hardcoded and discovered models"""
        try:
            from ..model_discovery import ModelDiscoveryService
            # Use default config dir
            discovery = ModelDiscoveryService()
            return discovery.merge_models('anthropic', cls.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to load discovered models (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "anthropic", "operation": "model_discovery"}
            )
            return cls.HARDCODED_MODELS.copy()
        except Exception as e:
            logger.warning(
                f"Unexpected error loading discovered models: {e}",
                exc_info=True,
                extra={"provider": "anthropic", "operation": "model_discovery"}
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
    
    # Model metadata for cost tracking and limits
    MODEL_INFO = {
        "claude-3-opus-20240229": {
            "name": "Claude 3 Opus",
            "context_window": 200000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 15.00,
            "cost_per_1m_output": 75.00,
        },
        "claude-3-sonnet-20240229": {
            "name": "Claude 3 Sonnet",
            "context_window": 200000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 3.00,
            "cost_per_1m_output": 15.00,
        },
        "claude-3-haiku-20240307": {
            "name": "Claude 3 Haiku",
            "context_window": 200000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 0.25,
            "cost_per_1m_output": 1.25,
        },
        "claude-3-5-sonnet-20241022": {
            "name": "Claude 3.5 Sonnet",
            "context_window": 200000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 3.00,
            "cost_per_1m_output": 15.00,
        },
        "claude-3-5-haiku-20241022": {
            "name": "Claude 3.5 Haiku",
            "context_window": 200000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 1.00,
            "cost_per_1m_output": 5.00,
        },
    }
    
    @property
    def name(self) -> str:
        return "anthropic"
    
    @property
    def display_name(self) -> str:
        return "Anthropic Claude"
    
    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()
    
    def is_model_new(self, model: str) -> bool:
        """Check if a model is newly discovered (not in hardcoded list)"""
        try:
            from ..model_discovery import ModelDiscoveryService
            discovery = ModelDiscoveryService()
            return discovery.is_model_new('anthropic', model, self.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to check if model is new (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "anthropic", "model": model, "operation": "is_model_new"}
            )
            return False
        except Exception as e:
            logger.warning(
                f"Unexpected error checking if model is new: {e}",
                exc_info=True,
                extra={"provider": "anthropic", "model": model, "operation": "is_model_new"}
            )
            return False
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> ClaudeAgent:
        """
        Create a Claude agent instance.
        
        Args:
            model: Claude model identifier
            name: Optional agent name (defaults to model-based name)
            **config: Configuration options
                - api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
                - max_tokens: Maximum tokens to generate (default 4096)
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        """
        # Decision 37A: be permissive about model IDs.
        # Keep a curated list for suggestions, but allow unknown models so users
        # can use newly released IDs without waiting for an SDK update.
        if model not in self.supported_models:
            logger.warning(
                f"AnthropicProvider: model '{model}' not in supported_models list; "
                f"continuing anyway."
            )
        
        # Generate a friendly name if not provided
        if name is None:
            # Extract model version from ID (e.g., "opus" from "claude-3-opus-20240229")
            parts = model.split('-')
            if len(parts) >= 3:
                name = f"claude-{parts[2]}"
            else:
                name = model
        
        return ClaudeAgent(
            name=name,
            model=model,
            api_key=config.get('api_key'),
            max_tokens=config.get('max_tokens', 4096),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager')
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate Anthropic configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Check for API key
        api_key = config.get('api_key') or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "Anthropic API key required. "
                "Set ANTHROPIC_API_KEY environment variable or pass api_key in config."
            )
        
        # Validate max_tokens if provided
        max_tokens = config.get('max_tokens')
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ConfigurationError(
                    f"max_tokens must be a positive integer, got: {max_tokens}"
                )
            if max_tokens > 8192:
                raise ConfigurationError(
                    f"max_tokens ({max_tokens}) exceeds maximum allowed (8192)"
                )
        
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Return required environment variables"""
        return ['ANTHROPIC_API_KEY']
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific Claude model"""
        return self.MODEL_INFO.get(model)
    
    def supports_streaming(self) -> bool:
        """Claude supports streaming responses"""
        return True
    
    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        """Get Claude capabilities"""
        return [
            'text-generation',
            'function-calling',
            'vision',  # Claude 3+ supports vision
            'long-context',  # 200K context window
        ]
