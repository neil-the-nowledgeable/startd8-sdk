"""
Anthropic Claude provider implementation
"""

from typing import List, Dict, Any, Optional
import os

from ..agents import ClaudeAgent
from ..exceptions import ConfigurationError


class AnthropicProvider:
    """Provider for Anthropic Claude models"""
    
    # Official Claude models
    MODELS = [
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229", 
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ]
    
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
        if model not in self.MODELS:
            raise ValueError(
                f"Model {model} not supported by Anthropic provider. "
                f"Available models: {', '.join(self.MODELS)}"
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
    
    def get_capabilities(self) -> List[str]:
        """Get Claude capabilities"""
        return [
            'text-generation',
            'function-calling',
            'vision',  # Claude 3+ supports vision
            'long-context',  # 200K context window
        ]
