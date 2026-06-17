"""
Pricing service for model cost calculation

Manages pricing data for different LLM models with support for:
- Default pricing configuration
- Custom pricing updates
- Persistent pricing storage
- Provider detection
"""

from typing import Dict, Optional, Tuple
from pathlib import Path
import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from ..logging_config import get_logger

logger = get_logger(__name__)


class ModelPricing(BaseModel):
    """Pricing for a specific model.

    Cache multipliers express Anthropic prompt-caching economics relative to the
    base input rate (REQ-CT-1): a cache *read* (hit) bills at 0.1x base input, a
    5-minute cache *write* bills at 1.25x base input. They are overridable per
    model for providers with different cache economics.
    """
    model: str
    provider: str
    input_cost_per_million: float
    output_cost_per_million: float
    cache_read_multiplier: float = 0.1
    cache_write_multiplier: float = 1.25
    estimated: bool = False  # True when the rate is a proxy, not a confirmed published price
    effective_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class PricingService:
    """
    Service for managing and calculating model pricing.
    
    Supports:
    - Loading pricing from file for easy updates
    - Fallback to default pricing
    - Historical pricing (for accurate cost calculation)
    
    Example:
        pricing = PricingService()
        
        # Calculate cost
        input_cost, output_cost = pricing.calculate_cost_breakdown(
            "claude-3-5-sonnet-20241022",
            input_tokens=1500,
            output_tokens=500
        )
        
        # Update pricing
        pricing.update_pricing(
            "claude-3-5-sonnet-20241022",
            input_cost=3.0,
            output_cost=15.0
        )
    """
    
    # Default pricing (updated January 2026)
    DEFAULT_PRICING: Dict[str, ModelPricing] = {
        # Anthropic Claude Fable 5 — Mythos-class flagship (GA 2026-06-09)
        "claude-fable-5": ModelPricing(
            model="claude-fable-5",
            provider="anthropic",
            input_cost_per_million=10.0,
            output_cost_per_million=50.0,
            notes="Anthropic published rate for Claude Fable 5.",
        ),
        # Anthropic Claude 4.8 / 4.7 (current Opus flagship defaults; rates estimated
        # from the 4.6 Opus tier until confirmed — REQ-CT-4)
        "claude-opus-4-8": ModelPricing(
            model="claude-opus-4-8",
            provider="anthropic",
            input_cost_per_million=5.0,
            output_cost_per_million=25.0,
            estimated=True,
            notes="Estimated from Opus 4.6 tier; update when published rate confirmed.",
        ),
        "claude-opus-4-7": ModelPricing(
            model="claude-opus-4-7",
            provider="anthropic",
            input_cost_per_million=5.0,
            output_cost_per_million=25.0,
            estimated=True,
            notes="Estimated from Opus 4.6 tier; update when published rate confirmed.",
        ),
        # Anthropic Claude 4.6 family
        "claude-opus-4-6": ModelPricing(
            model="claude-opus-4-6",
            provider="anthropic",
            input_cost_per_million=5.0,
            output_cost_per_million=25.0
        ),
        "claude-sonnet-4-6": ModelPricing(
            model="claude-sonnet-4-6",
            provider="anthropic",
            input_cost_per_million=3.0,
            output_cost_per_million=15.0
        ),
        # Anthropic Claude 4.5 family
        "claude-opus-4-5-20251101": ModelPricing(
            model="claude-opus-4-5-20251101",
            provider="anthropic",
            input_cost_per_million=5.0,
            output_cost_per_million=25.0
        ),
        "claude-sonnet-4-5-20250929": ModelPricing(
            model="claude-sonnet-4-5-20250929",
            provider="anthropic",
            input_cost_per_million=3.0,
            output_cost_per_million=15.0
        ),
        "claude-haiku-4-5-20251001": ModelPricing(
            model="claude-haiku-4-5-20251001",
            provider="anthropic",
            input_cost_per_million=1.0,
            output_cost_per_million=5.0
        ),
        # Anthropic Claude 4.x family
        "claude-opus-4-1-20250805": ModelPricing(
            model="claude-opus-4-1-20250805",
            provider="anthropic",
            input_cost_per_million=15.0,
            output_cost_per_million=75.0
        ),
        "claude-sonnet-4-20250514": ModelPricing(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_cost_per_million=3.0,
            output_cost_per_million=15.0
        ),
        # Anthropic Claude 3.5 family
        "claude-3-5-sonnet-20241022": ModelPricing(
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            input_cost_per_million=3.0,
            output_cost_per_million=15.0
        ),
        "claude-3-5-haiku-20241022": ModelPricing(
            model="claude-3-5-haiku-20241022",
            provider="anthropic",
            input_cost_per_million=1.0,
            output_cost_per_million=5.0
        ),
        # Anthropic Claude 3 legacy
        "claude-3-opus-20240229": ModelPricing(
            model="claude-3-opus-20240229",
            provider="anthropic",
            input_cost_per_million=15.0,
            output_cost_per_million=75.0
        ),
        "claude-3-haiku-20240307": ModelPricing(
            model="claude-3-haiku-20240307",
            provider="anthropic",
            input_cost_per_million=0.25,
            output_cost_per_million=1.25
        ),

        # OpenAI GPT-5.x family (current defaults; rates estimated from the
        # nearest GPT-4.x/o3 tier until confirmed — REQ-CT-4)
        "gpt-5.5-pro": ModelPricing(
            model="gpt-5.5-pro", provider="openai",
            input_cost_per_million=10.0, output_cost_per_million=40.0,
            estimated=True, notes="Estimated (flagship/o3 tier); confirm published rate.",
        ),
        "gpt-5.5": ModelPricing(
            model="gpt-5.5", provider="openai",
            input_cost_per_million=2.5, output_cost_per_million=10.0,
            estimated=True, notes="Estimated (GPT-4o tier); confirm published rate.",
        ),
        "gpt-5.4-mini": ModelPricing(
            model="gpt-5.4-mini", provider="openai",
            input_cost_per_million=0.4, output_cost_per_million=1.6,
            estimated=True, notes="Estimated (4.1-mini tier); confirm published rate.",
        ),
        "gpt-5.4-nano": ModelPricing(
            model="gpt-5.4-nano", provider="openai",
            input_cost_per_million=0.1, output_cost_per_million=0.4,
            estimated=True, notes="Estimated (4.1-nano tier); confirm published rate.",
        ),
        "gpt-5.3-codex": ModelPricing(
            model="gpt-5.3-codex", provider="openai",
            input_cost_per_million=2.5, output_cost_per_million=10.0,
            estimated=True, notes="Estimated (GPT-4o tier); confirm published rate.",
        ),
        # OpenAI GPT-4.1 family (1M context)
        "gpt-4.1": ModelPricing(
            model="gpt-4.1",
            provider="openai",
            input_cost_per_million=2.0,
            output_cost_per_million=8.0
        ),
        "gpt-4.1-mini": ModelPricing(
            model="gpt-4.1-mini",
            provider="openai",
            input_cost_per_million=0.4,
            output_cost_per_million=1.6
        ),
        "gpt-4.1-nano": ModelPricing(
            model="gpt-4.1-nano",
            provider="openai",
            input_cost_per_million=0.1,
            output_cost_per_million=0.4
        ),
        # OpenAI o-series reasoning models
        "o3": ModelPricing(
            model="o3",
            provider="openai",
            input_cost_per_million=10.0,
            output_cost_per_million=40.0
        ),
        "o3-mini": ModelPricing(
            model="o3-mini",
            provider="openai",
            input_cost_per_million=1.1,
            output_cost_per_million=4.4
        ),
        "o3-pro": ModelPricing(
            model="o3-pro",
            provider="openai",
            input_cost_per_million=20.0,
            output_cost_per_million=80.0
        ),
        "o4-mini": ModelPricing(
            model="o4-mini",
            provider="openai",
            input_cost_per_million=1.1,
            output_cost_per_million=4.4
        ),
        # OpenAI GPT-4o family
        "gpt-4o": ModelPricing(
            model="gpt-4o",
            provider="openai",
            input_cost_per_million=2.5,
            output_cost_per_million=10.0
        ),
        "gpt-4o-mini": ModelPricing(
            model="gpt-4o-mini",
            provider="openai",
            input_cost_per_million=0.15,
            output_cost_per_million=0.60
        ),
        # OpenAI legacy
        "gpt-4-turbo": ModelPricing(
            model="gpt-4-turbo",
            provider="openai",
            input_cost_per_million=10.0,
            output_cost_per_million=30.0
        ),
        "gpt-4": ModelPricing(
            model="gpt-4",
            provider="openai",
            input_cost_per_million=30.0,
            output_cost_per_million=60.0
        ),
        "gpt-3.5-turbo": ModelPricing(
            model="gpt-3.5-turbo",
            provider="openai",
            input_cost_per_million=0.5,
            output_cost_per_million=1.5
        ),

        # Google Gemini 3.x family
        "gemini-3.1-pro-preview": ModelPricing(
            model="gemini-3.1-pro-preview", provider="google",
            input_cost_per_million=1.25, output_cost_per_million=5.0,
            estimated=True, notes="Estimated (Gemini 2.5/3 Pro tier); confirm published rate.",
        ),
        "gemini-3-pro-preview": ModelPricing(
            model="gemini-3-pro-preview",
            provider="google",
            input_cost_per_million=1.25,
            output_cost_per_million=5.0
        ),
        "gemini-3-flash-preview": ModelPricing(
            model="gemini-3-flash-preview",
            provider="google",
            input_cost_per_million=0.1,
            output_cost_per_million=0.4
        ),
        # Google Gemini 2.5 family
        "gemini-2.5-pro": ModelPricing(
            model="gemini-2.5-pro",
            provider="google",
            input_cost_per_million=1.25,
            output_cost_per_million=5.0
        ),
        "gemini-2.5-flash": ModelPricing(
            model="gemini-2.5-flash",
            provider="google",
            input_cost_per_million=0.15,
            output_cost_per_million=0.6
        ),
        "gemini-2.5-flash-lite": ModelPricing(
            model="gemini-2.5-flash-lite",
            provider="google",
            input_cost_per_million=0.075,
            output_cost_per_million=0.3
        ),
        # Google Gemini 2.0 family
        "gemini-2.0-flash": ModelPricing(
            model="gemini-2.0-flash",
            provider="google",
            input_cost_per_million=0.1,
            output_cost_per_million=0.4
        ),
        "gemini-2.0-flash-lite": ModelPricing(
            model="gemini-2.0-flash-lite",
            provider="google",
            input_cost_per_million=0.075,
            output_cost_per_million=0.3
        ),
        # Google Gemini legacy (retired)
        "gemini-1.5-pro": ModelPricing(
            model="gemini-1.5-pro",
            provider="google",
            input_cost_per_million=3.5,
            output_cost_per_million=10.5
        ),
        "gemini-1.5-flash": ModelPricing(
            model="gemini-1.5-flash",
            provider="google",
            input_cost_per_million=0.075,
            output_cost_per_million=0.30
        ),
        # NVIDIA NIM
        "nvidia/nemotron-3-nano-30b-a3b": ModelPricing(
            model="nvidia/nemotron-3-nano-30b-a3b",
            provider="nim",
            input_cost_per_million=0.30,
            output_cost_per_million=0.30
        ),
        # DeepSeek (FR-4: confirm against https://api-docs.deepseek.com/quick_start/pricing)
        "deepseek-chat": ModelPricing(
            model="deepseek-chat",
            provider="deepseek",
            input_cost_per_million=0.27,
            output_cost_per_million=1.10,
            estimated=True,
            notes="DeepSeek-V3 list price (cache-miss); confirm at api-docs.deepseek.com pricing.",
        ),
        "deepseek-reasoner": ModelPricing(
            model="deepseek-reasoner",
            provider="deepseek",
            input_cost_per_million=0.55,
            output_cost_per_million=2.19,
            estimated=True,
            notes="DeepSeek-R1 list price (cache-miss); confirm at api-docs.deepseek.com pricing.",
        ),
        # Jetson edge cluster (FR-J9b). Two call sites resolve different ids: the pre-run
        # ESTIMATE keys on the public alias (stripped from the `provider:model` spec) while the
        # RUNTIME tracker keys on the SERVED id (the agent's translated model). Both must be present
        # or the dry-run warns "NO PRICING" / the runtime hits the misleading $3/$15 fallback —
        # exactly the path the dry-run surfaced. Marginal on-prem cost is ≈$0; the amortized-vs-
        # free-lane representation is OQ-J3 (report-side, gates the cost ranking per FR-J8).
        # -- served ids (runtime tracker) --
        "mistralai/Mistral-7B-v0.3": ModelPricing(
            model="mistralai/Mistral-7B-v0.3",
            provider="jetson",
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            estimated=True,
            notes="Jetson served id; on-prem marginal ≈$0; amortized cost is OQ-J3 (cost-lane gate).",
        ),
        "iter_002": ModelPricing(
            model="iter_002",
            provider="jetson",
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            estimated=True,
            notes="Jetson served id; in-domain-finetune (fenced track). OQ-J3 for cost rep.",
        ),
        # -- aliases (pre-run estimate) --
        "mistral-7b-base": ModelPricing(
            model="mistral-7b-base",
            provider="jetson",
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            estimated=True,
            notes="Jetson alias of mistralai/Mistral-7B-v0.3; ≈$0 marginal; OQ-J3 cost-lane gate.",
        ),
        "iter-002": ModelPricing(
            model="iter-002",
            provider="jetson",
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            estimated=True,
            notes="Jetson alias of iter_002; in-domain-finetune (fenced track); OQ-J3 for cost rep.",
        ),
    }

    # Provider detection patterns
    PROVIDER_PATTERNS = {
        "anthropic": ["claude"],
        "openai": ["gpt", "o1", "o3", "o4", "davinci", "curie"],
        "google": ["gemini", "palm"],
        "nim": ["nemotron", "nvidia"],
        "deepseek": ["deepseek"],
        "jetson": ["jetson"],
    }
    
    def __init__(self, pricing_file: Optional[Path] = None):
        self._pricing: Dict[str, ModelPricing] = dict(self.DEFAULT_PRICING)
        self._pricing_file = pricing_file
        
        if pricing_file and pricing_file.exists():
            self._load_pricing_file(pricing_file)
    
    def _load_pricing_file(self, path: Path):
        """Load pricing from JSON file"""
        try:
            with open(path) as f:
                data = json.load(f)
            
            for model_data in data.get("models", []):
                pricing = ModelPricing(**model_data)
                self._pricing[pricing.model] = pricing
            
            logger.info(f"Loaded pricing for {len(data.get('models', []))} models from {path}")
        except Exception as e:
            logger.warning(f"Failed to load pricing file {path}: {e}")
    
    def save_pricing_file(self, path: Optional[Path] = None):
        """Save current pricing to file"""
        path = path or self._pricing_file
        if not path:
            raise ValueError("No pricing file path specified")
        
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "models": [p.model_dump() for p in self._pricing.values()]
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Saved pricing for {len(self._pricing)} models to {path}")
    
    # Trailing date-suffix patterns used by providers for dated model variants:
    # Anthropic `-YYYYMMDD` (claude-sonnet-4-5-20250929) and OpenAI `-YYYY-MM-DD`
    # (gpt-5.5-2026-04-23). Stripping these lets a dated id resolve to its undated
    # family entry WITHOUT the unsafe bare-prefix collapse (REQ-CT-3).
    _DATE_SUFFIX_RE = re.compile(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$")

    # Conservative fallback rate when a model is unknown (flagged estimated).
    _FALLBACK_INPUT_PER_M = 3.0
    _FALLBACK_OUTPUT_PER_M = 15.0

    def resolve_pricing(self, model: str) -> Tuple[ModelPricing, bool]:
        """Resolve a model to pricing, family-safely (REQ-CT-3/CT-5).

        Resolution order: exact key → same-id with a trailing date suffix stripped
        → conservative *estimated* fallback. Crucially this never maps a model to a
        DIFFERENT family's rate (the old ``startswith(key.rsplit('-',1)[0])`` collapse
        could price ``gpt-5.5-pro`` as ``gpt-4.1``).

        Returns ``(pricing, estimated)`` where ``estimated`` is True when the rate is
        a flagged proxy or the fallback.
        """
        exact = self._pricing.get(model)
        if exact is not None:
            return exact, exact.estimated

        undated = self._DATE_SUFFIX_RE.sub("", model)
        if undated != model:
            base = self._pricing.get(undated)
            if base is not None:
                return base, base.estimated

        logger.warning(
            "No pricing entry for model %r; using estimated fallback "
            "($%.2f/$%.2f per M). Add an entry via update_pricing for accuracy.",
            model, self._FALLBACK_INPUT_PER_M, self._FALLBACK_OUTPUT_PER_M,
        )
        return (
            ModelPricing(
                model=model,
                provider=self.get_provider_for_model(model) or "unknown",
                input_cost_per_million=self._FALLBACK_INPUT_PER_M,
                output_cost_per_million=self._FALLBACK_OUTPUT_PER_M,
                estimated=True,
                notes="Fallback estimate — no pricing entry for this model.",
            ),
            True,
        )

    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        """Get pricing for a model (exact or date-normalized only).

        Returns None when the model has no real entry — preserving the historical
        "None means unknown" contract. For cost calculation use ``resolve_pricing``,
        which adds the flagged fallback.
        """
        exact = self._pricing.get(model)
        if exact is not None:
            return exact
        undated = self._DATE_SUFFIX_RE.sub("", model)
        if undated != model:
            return self._pricing.get(undated)
        return None

    def calculate_cost_breakdown(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> Tuple[float, float]:
        """
        Calculate cost breakdown for input and output tokens, cache-aware (REQ-CT-1).

        ``input_tokens`` is the NON-cached input (Anthropic reports cache tokens
        separately). The returned input cost folds in cache economics:
        ``input·rate + cache_creation·rate·write_mult + cache_read·rate·read_mult``.
        Defaults keep the no-cache result identical to the prior implementation.

        Returns:
            Tuple of (input_cost, output_cost) in USD
        """
        pricing, _estimated = self.resolve_pricing(model)
        in_rate = pricing.input_cost_per_million / 1_000_000
        input_cost = (
            input_tokens * in_rate
            + cache_creation_input_tokens * in_rate * pricing.cache_write_multiplier
            + cache_read_input_tokens * in_rate * pricing.cache_read_multiplier
        )
        output_cost = output_tokens * (pricing.output_cost_per_million / 1_000_000)
        return input_cost, output_cost
    
    def calculate_total_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> float:
        """Calculate total cost for a model call (cache-aware)."""
        input_cost, output_cost = self.calculate_cost_breakdown(
            model, input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens,
        )
        return input_cost + output_cost
    
    def get_provider_for_model(self, model: str) -> Optional[str]:
        """Detect provider from model name"""
        pricing = self.get_pricing(model)
        if pricing:
            return pricing.provider
        
        model_lower = model.lower()
        for provider, patterns in self.PROVIDER_PATTERNS.items():
            if any(p in model_lower for p in patterns):
                return provider
        
        return None
    
    def update_pricing(
        self,
        model: str,
        input_cost_per_million: float,
        output_cost_per_million: float,
        provider: Optional[str] = None
    ):
        """Update pricing for a model"""
        provider = provider or self.get_provider_for_model(model) or "unknown"
        
        self._pricing[model] = ModelPricing(
            model=model,
            provider=provider,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million
        )
        
        logger.info(f"Updated pricing for {model}: ${input_cost_per_million}/${output_cost_per_million} per M tokens")
    
    def list_models(self) -> Dict[str, ModelPricing]:
        """List all models with pricing"""
        return dict(self._pricing)
    
    def estimate_cost(
        self,
        model: str,
        prompt_chars: int,
        expected_output_chars: int = 0
    ) -> float:
        """
        Estimate cost based on character counts.
        
        Uses rough estimate of 4 characters per token.
        Useful for pre-call cost estimation.
        """
        # Rough token estimation (4 chars per token on average)
        input_tokens = prompt_chars // 4
        output_tokens = expected_output_chars // 4 if expected_output_chars else input_tokens // 2
        
        return self.calculate_total_cost(model, input_tokens, output_tokens)
