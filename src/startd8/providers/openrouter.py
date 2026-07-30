"""
OpenRouter provider implementation.

OpenRouter (https://openrouter.ai) is a **US-billed OpenAI-compatible aggregator**: one key routes to
many upstream vendors (DeepSeek, xAI/Grok, Qwen, Llama, …) behind a single Chat Completions API. This
lets the benchmark enroll DeepSeek's V3/R1 models — and others — without each vendor's own billing
(notably sidestepping DeepSeek's cancelled top-ups).

Dedicated provider (the DeepSeek recipe): hardcode the endpoint + read the env key → an
``OpenAICompatibleAgent``, so ``openrouter:<model>`` resolves with zero benchmark-plumbing changes.
See ``docs/design/openrouter-vendor/``.

Model ids are passed through **verbatim** (FR-OR-2) — OpenRouter's canonical, slash-bearing ids
(``deepseek/deepseek-chat``) ARE the API contract; ``slug()`` already makes them path-safe, so there
is no alias-translation layer (unlike the Jetson lane). OpenRouter is a **cost-ranked cloud vendor**
(FR-OR-7), not a $0 local lane.
"""

from typing import List, Dict, Any, Optional
import os
import logging

from ..agents import OpenAICompatibleAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class OpenRouterProvider:
    """Provider for OpenRouter's OpenAI-compatible aggregator API."""

    BASE_URL = "https://openrouter.ai/api/v1"

    # Canonical OpenRouter ids, verified against live GET /models (2026-07-30 M4 expand).
    # Unlisted ids still pass through with a warning (FR-OR-2).
    MODELS = [
        "deepseek/deepseek-chat",                 # DeepSeek-V3 mid (lab deepseek)
        "deepseek/deepseek-r1",                   # DeepSeek-R1 reasoner (legacy pin)
        "deepseek/deepseek-v4-pro",               # DeepSeek-V4 Pro flagship
        "deepseek/deepseek-v4-flash",             # DeepSeek-V4 Flash fast
        "qwen/qwen-2.5-coder-32b-instruct",       # hosted sibling of local qwen2.5-coder:7b
        "qwen/qwen3-max",                        # Qwen3 Max flagship
        "qwen/qwen-plus",                        # Qwen-Plus mid
        "qwen/qwen3-coder-flash",                # Qwen3 Coder Flash fast
        # 8-lab heats expand (2026-07-30): Moonshot / Z.ai / MiniMax
        "moonshotai/kimi-k3",                    # Moonshot Kimi K3 flagship
        "moonshotai/kimi-k2.7-code",             # Moonshot Kimi K2.7 Code mid
        "moonshotai/kimi-k2.5",                  # Moonshot Kimi K2.5 fast
        "z-ai/glm-5.2",                          # Z.ai GLM-5.2 flagship
        "z-ai/glm-5.1",                          # Z.ai GLM-5.1 mid
        "z-ai/glm-4.7-flash",                    # Z.ai GLM-4.7 Flash fast
        "minimax/minimax-m3",                    # MiniMax M3 flagship
        "minimax/minimax-m2.7",                  # MiniMax M2.7 mid
        "minimax/minimax-m2.5",                  # MiniMax M2.5 fast
    ]

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return "OpenRouter"

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
        Create an OpenRouter agent.

        Args:
            model: an OpenRouter model id, passed through verbatim (e.g. ``deepseek/deepseek-chat``).
            name: optional agent name.
            **config: api_key (else OPENROUTER_API_KEY), max_tokens, cost_tracker, etc.
        """
        # The aggregator catalog is large and drifts; an unlisted id is a warning, not an error.
        if model not in self.MODELS:
            logger.warning(
                "OpenRouterProvider: model '%s' not in the pinned roster; passing through verbatim.",
                model,
            )

        if name is None:
            name = f"openrouter-{model}"

        api_key = config.get('api_key') or os.getenv('OPENROUTER_API_KEY')

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
        Validate OpenRouter configuration.

        Raises:
            ConfigurationError: message contains "API key required" so a missing/unfunded key is
            classified ``infra_fail`` by the benchmark's ``_INFRA_ERROR_MARKERS`` (incl. the new
            402/insufficient-balance markers), never scored as a model 0 (FR-OR-3).
        """
        api_key = config.get('api_key') or os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "OpenRouter API key required. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key in config."
            )
        return True

    def get_required_env_vars(self) -> List[str]:
        return ['OPENROUTER_API_KEY']

    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Light metadata; None for an unlisted id (pricing/catalog own the details)."""
        if model not in self.MODELS:
            return None
        return {"id": model, "base_url": self.BASE_URL, "vendor": model.split("/", 1)[0]}

    def supports_streaming(self) -> bool:
        return True

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        caps = ['text-generation', 'code', 'function-calling']
        if model and ("r1" in model or "reason" in model):
            caps.append('reasoning')
        return caps
