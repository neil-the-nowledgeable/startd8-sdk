"""
Mistral AI provider implementation
"""

from typing import List, Dict, Any, Optional
import os
import logging

from ..agents import OpenAICompatibleAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class MistralProvider:
    """Provider for Mistral AI models via OpenAI-compatible API"""

    MODELS = [
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
        "codestral-latest",
        "ministral-8b-latest",
        "ministral-3b-latest",
    ]

    MODEL_INFO = {
        "mistral-large-latest": {
            "name": "Mistral Large",
            "context_window": 256000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 2.00,
            "cost_per_1m_output": 6.00,
        },
        "mistral-medium-latest": {
            "name": "Mistral Medium",
            "context_window": 131000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.40,
            "cost_per_1m_output": 2.00,
        },
        "mistral-small-latest": {
            "name": "Mistral Small",
            "context_window": 128000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.10,
            "cost_per_1m_output": 0.30,
        },
        "codestral-latest": {
            "name": "Codestral",
            "context_window": 256000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.30,
            "cost_per_1m_output": 0.90,
        },
        "ministral-8b-latest": {
            "name": "Ministral 8B",
            "context_window": 128000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.10,
            "cost_per_1m_output": 0.10,
        },
        "ministral-3b-latest": {
            "name": "Ministral 3B",
            "context_window": 128000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.04,
            "cost_per_1m_output": 0.04,
        },
    }

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def display_name(self) -> str:
        return "Mistral AI"

    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()

    def create_agent(
        self,
        model: str,
        name: Optional[str] = None,
        **config,
    ) -> OpenAICompatibleAgent:
        """
        Create a Mistral AI agent instance.

        Args:
            model: Mistral model identifier
            name: Optional agent name
            **config: Configuration options
                - api_key: Mistral API key (or use MISTRAL_API_KEY env var)
                - max_tokens: Maximum tokens to generate
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        """
        if model not in self.MODELS:
            logger.warning(
                f"MistralProvider: model '{model}' not in supported_models list; "
                f"continuing anyway."
            )

        if name is None:
            name = f"mistral-{model}"

        api_key = config.get('api_key') or os.getenv('MISTRAL_API_KEY')

        return OpenAICompatibleAgent(
            name=name,
            model=model,
            api_key=api_key,
            base_url='https://api.mistral.ai/v1',
            max_tokens=config.get('max_tokens', 8192),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager'),
            timeout_config=config.get('timeout_config'),
            retry_config=config.get('retry_config'),
            enable_retry=config.get('enable_retry', False),
            use_connection_pool=config.get('use_connection_pool', False),
        )

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate Mistral configuration.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        api_key = config.get('api_key') or os.getenv('MISTRAL_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "Mistral API key required. "
                "Set MISTRAL_API_KEY environment variable or pass api_key in config."
            )
        return True

    def get_required_env_vars(self) -> List[str]:
        return ['MISTRAL_API_KEY']

    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific Mistral model"""
        return self.MODEL_INFO.get(model)

    def supports_streaming(self) -> bool:
        return True

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        return ['text-generation', 'function-calling', 'json-mode']
