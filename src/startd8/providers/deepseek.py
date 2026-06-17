"""
DeepSeek provider implementation.

DeepSeek exposes an OpenAI-compatible Chat Completions API, so this provider is a
thin dedicated wrapper around :class:`OpenAICompatibleAgent` with the DeepSeek
endpoint and key conventions baked in (mirrors :class:`MistralProvider`).

Being a *dedicated* provider (rather than the generic ``openai-compatible`` one)
is deliberate: the model benchmark pins models as ``provider:model`` strings and
never threads a ``base_url`` through the run spec. Self-describing the endpoint
here lets ``deepseek:deepseek-chat`` resolve with zero benchmark-plumbing changes.
See ``docs/design/deepseek-vendor/DEEPSEEK_VENDOR_REQUIREMENTS.md`` (FR-1, FR-6).
"""

from typing import List, Dict, Any, Optional
import os
import logging

from ..agents import OpenAICompatibleAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """Provider for DeepSeek models via their OpenAI-compatible API."""

    BASE_URL = "https://api.deepseek.com/v1"

    MODELS = [
        "deepseek-chat",      # DeepSeek-V3 class — general chat/code
        "deepseek-reasoner",  # DeepSeek-R1 class — reasoning (emits reasoning_content)
    ]

    MODEL_INFO = {
        "deepseek-chat": {
            "name": "DeepSeek Chat (V3)",
            "context_window": 64000,
            "max_output_tokens": 8192,
            # FR-4: confirm against https://api-docs.deepseek.com/quick_start/pricing
            "cost_per_1m_input": 0.27,
            "cost_per_1m_output": 1.10,
        },
        "deepseek-reasoner": {
            "name": "DeepSeek Reasoner (R1)",
            "context_window": 64000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.55,
            "cost_per_1m_output": 2.19,
        },
    }

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def display_name(self) -> str:
        return "DeepSeek"

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
        Create a DeepSeek agent instance.

        Args:
            model: DeepSeek model identifier (e.g. ``deepseek-chat``)
            name: Optional agent name
            **config: Configuration options
                - api_key: DeepSeek API key (or use DEEPSEEK_API_KEY env var)
                - max_tokens: Maximum tokens to generate
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        """
        if model not in self.MODELS:
            logger.warning(
                f"DeepSeekProvider: model '{model}' not in supported_models list; "
                f"continuing anyway."
            )

        if name is None:
            name = f"deepseek-{model}"

        api_key = config.get('api_key') or os.getenv('DEEPSEEK_API_KEY')

        return OpenAICompatibleAgent(
            name=name,
            model=model,
            api_key=api_key,
            base_url=self.BASE_URL,
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
        Validate DeepSeek configuration.

        Raises:
            ConfigurationError: If configuration is invalid. The message contains
            "API key required" so a missing key is classified ``infra_fail`` by the
            benchmark's ``_INFRA_ERROR_MARKERS`` (FR-3), not scored as a model 0.
        """
        api_key = config.get('api_key') or os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "DeepSeek API key required. "
                "Set DEEPSEEK_API_KEY environment variable or pass api_key in config."
            )
        return True

    def get_required_env_vars(self) -> List[str]:
        return ['DEEPSEEK_API_KEY']

    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific DeepSeek model."""
        return self.MODEL_INFO.get(model)

    def supports_streaming(self) -> bool:
        return True

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        caps = ['text-generation', 'function-calling', 'json-mode']
        if model == "deepseek-reasoner":
            caps.append('reasoning')
        return caps
