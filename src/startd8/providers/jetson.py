"""
Jetson edge-cluster provider.

Enrolls a self-hosted Jetson Orin Nano cluster (an OpenAI-compatible FastAPI
endpoint on the LAN) as a benchmark serving backend. Dedicated provider so the
benchmark `provider:model` spec resolves with zero run-spec plumbing — the model
field selects which served model (base or a fine-tuned adapter), and the endpoint
is self-described here.

Design + firewall: ``docs/design/jetson-cluster-benchmark/``.

SECURITY (FR-J12): the target is **plaintext HTTP on an RFC1918 address with a
sentinel key that bypasses the SDK's localhost-only key-null guard**
(``agents/openai.py`` only nulls the key for localhost/127.0.0.1, NOT 192.168.x.x).
There is no transport authentication or integrity — any host on the LAN can
impersonate the endpoint and feed crafted completions into the scorer. The SDK
must therefore never *silently* dial it: ``create_agent`` refuses unless the
operator sets ``STARTD8_ALLOW_LAN_ENDPOINT=1``. TLS/mTLS is out of scope for v1
(NR-J6).

WHAT DOES NOT TRANSFER FROM THE DeepSeek PRECEDENT (R1-S10): DeepSeek is a clean
hosted vendor over TLS with a real key; Jetson is plaintext-LAN + sentinel key +
(for adapters) corpus-fine-tuned weights. Do not copy DeepSeek's transport,
key-trust, or contamination assumptions here.

CONTAMINATION (FR-J5/J5a): adapters such as ``iter-002`` were fine-tuned on the
benchmark corpus (microservices-demo / Online Boutique) and are labeled
``in-domain-finetune`` — they belong only in a separately labeled track, never the
general leaderboard. The base model is labeled ``clean`` (of *our* contamination;
see FR-J8 residual note re: pretraining exposure).
"""

from typing import List, Dict, Any, Optional
import os
import logging

from ..agents import OpenAICompatibleAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Operator opt-in gate (FR-J12) — the SDK will not dial the plaintext LAN endpoint
# without this set, so a misconfig can never silently reach a stranger on the LAN.
ALLOW_ENV = "STARTD8_ALLOW_LAN_ENDPOINT"


class JetsonProvider:
    """Provider for the self-hosted Jetson edge cluster via its OpenAI-compatible API."""

    # FR-J3 / R1-S2: env-overridable, not a bare constant (survives DHCP/host changes;
    # lets tests point at a mock server).
    DEFAULT_BASE_URL = "http://192.168.7.57:8000/v1"

    # FR-J3a: clean slash-free aliases mapped to the server's REAL model id. The served
    # id is what the agent reports to the cost tracker, so pricing is keyed under it.
    ALIASES: Dict[str, str] = {
        "mistral-7b-base": "mistralai/Mistral-7B-v0.3",
        "iter-002": "iter_002",
    }

    # FR-J5/J5a/J7: per-alias contamination posture.
    CONTAMINATION: Dict[str, str] = {
        "mistral-7b-base": "clean",            # clean of OUR 3 vectors (FR-J8 residual note)
        "iter-002": "in-domain-finetune",      # trained on the benchmark corpus — fenced track only
    }

    MODELS = list(ALIASES)

    @property
    def name(self) -> str:
        return "jetson"

    @property
    def display_name(self) -> str:
        return "Jetson Edge Cluster"

    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()

    @property
    def base_url(self) -> str:
        return os.getenv("JETSON_BASE_URL", self.DEFAULT_BASE_URL)

    def served_id(self, model: str) -> str:
        """Translate a public alias to the server's real model id (FR-J3a)."""
        return self.ALIASES.get(model, model)

    def contamination_label(self, model: str) -> str:
        """Contamination posture for a model/alias (FR-J5/J7); unknown → ``unknown``."""
        return self.CONTAMINATION.get(model, "unknown")

    def _require_opt_in(self) -> None:
        """FR-J12: refuse to construct/validate a LAN agent without explicit operator opt-in."""
        if os.getenv(ALLOW_ENV, "").strip().lower() not in ("1", "true", "yes"):
            raise ConfigurationError(
                f"Jetson LAN endpoint requires explicit opt-in. Set {ALLOW_ENV}=1 to allow the SDK "
                f"to dial the plaintext-HTTP RFC1918 endpoint ({self.base_url}). This is a deliberate "
                f"security gate (no transport auth/integrity; see FR-J12)."
            )

    def create_agent(
        self,
        model: str,
        name: Optional[str] = None,
        **config,
    ) -> OpenAICompatibleAgent:
        """
        Create a Jetson edge-cluster agent.

        Args:
            model: a public alias (e.g. ``mistral-7b-base``) — translated to the served id.
            name: optional agent name.
            **config: api_key (else LOCAL_FASTAPI_API_KEY / sentinel), max_tokens, cost_tracker, etc.
        """
        self._require_opt_in()

        if model not in self.MODELS:
            logger.warning(
                "JetsonProvider: model '%s' not in supported_models (aliases: %s); "
                "passing through verbatim.",
                model, ", ".join(self.MODELS),
            )

        served = self.served_id(model)
        if name is None:
            name = f"jetson-{model}"

        # FR-J11: the SDK nulls the key only for localhost/127.0.0.1, so a LAN IP needs a
        # non-empty key. The no-auth FastAPI server ignores it; a sentinel keeps the OpenAI
        # client happy.
        api_key = config.get("api_key") or os.getenv("LOCAL_FASTAPI_API_KEY", "local-no-auth")

        return OpenAICompatibleAgent(
            name=name,
            model=served,
            api_key=api_key,
            base_url=self.base_url,
            max_tokens=config.get("max_tokens", 2048),
            cost_tracker=config.get("cost_tracker"),
            budget_manager=config.get("budget_manager"),
            timeout_config=config.get("timeout_config"),
            retry_config=config.get("retry_config"),
            enable_retry=config.get("enable_retry", False),
            use_connection_pool=config.get("use_connection_pool", False),
        )

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Jetson configuration. Requires the FR-J12 opt-in; key is sentinel-tolerant."""
        self._require_opt_in()
        return True

    def get_required_env_vars(self) -> List[str]:
        # The opt-in flag is required; the API key is sentinel-defaulted (no real secret needed).
        return [ALLOW_ENV]

    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        if model not in self.ALIASES:
            return None
        return {
            "served_id": self.served_id(model),
            "contamination": self.contamination_label(model),
            "base_url": self.base_url,
        }

    def supports_streaming(self) -> bool:
        return True

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        return ["text-generation", "code"]
