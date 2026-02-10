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
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from ..logging_config import get_logger

logger = get_logger(__name__)


class ModelPricing(BaseModel):
    """Pricing for a specific model"""
    model: str
    provider: str
    input_cost_per_million: float
    output_cost_per_million: float
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
        # Anthropic Claude 4.6 family
        "claude-opus-4-6": ModelPricing(
            model="claude-opus-4-6",
            provider="anthropic",
            input_cost_per_million=5.0,
            output_cost_per_million=25.0
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
        "claude-haiku-4-5-20251008": ModelPricing(
            model="claude-haiku-4-5-20251008",
            provider="anthropic",
            input_cost_per_million=1.0,
            output_cost_per_million=5.0
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
    }
    
    # Provider detection patterns
    PROVIDER_PATTERNS = {
        "anthropic": ["claude"],
        "openai": ["gpt", "o1", "o3", "o4", "davinci", "curie"],
        "google": ["gemini", "palm"],
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
    
    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        """Get pricing for a model"""
        # Exact match
        if model in self._pricing:
            return self._pricing[model]
        
        # Try prefix match (for versioned models)
        for key, pricing in self._pricing.items():
            if model.startswith(key.rsplit('-', 1)[0]):
                return pricing
        
        return None
    
    def calculate_cost_breakdown(
        self, 
        model: str, 
        input_tokens: int, 
        output_tokens: int
    ) -> Tuple[float, float]:
        """
        Calculate cost breakdown for input and output tokens.
        
        Returns:
            Tuple of (input_cost, output_cost) in USD
        """
        pricing = self.get_pricing(model)
        
        if pricing:
            input_cost = (input_tokens / 1_000_000) * pricing.input_cost_per_million
            output_cost = (output_tokens / 1_000_000) * pricing.output_cost_per_million
        else:
            # Fallback to conservative estimate
            logger.warning(f"No pricing for model {model}, using fallback")
            input_cost = (input_tokens / 1_000_000) * 3.0
            output_cost = (output_tokens / 1_000_000) * 15.0
        
        return input_cost, output_cost
    
    def calculate_total_cost(
        self, 
        model: str, 
        input_tokens: int, 
        output_tokens: int
    ) -> float:
        """Calculate total cost for a model call"""
        input_cost, output_cost = self.calculate_cost_breakdown(
            model, input_tokens, output_tokens
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
