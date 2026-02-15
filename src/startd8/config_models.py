"""
Configuration models for startd8 SDK

Defines configuration structures for pricing, models, and other settings.
"""

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    """Pricing configuration for a model"""
    input_cost_per_million: float = Field(description="Cost per million input tokens")
    output_cost_per_million: float = Field(description="Cost per million output tokens")
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for given token usage"""
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_million
        return input_cost + output_cost


class ModelConfig(BaseModel):
    """Configuration for a specific model"""
    name: str = Field(description="Model name/identifier")
    provider: str = Field(description="Provider name (anthropic, openai, etc.)")
    default_max_tokens: int = Field(default=4096, description="Default max tokens")
    pricing: Optional[ModelPricing] = Field(default=None, description="Pricing configuration")
    available: bool = Field(default=True, description="Whether model is available")


class PricingConfig(BaseModel):
    """Pricing configuration for all models"""
    models: Dict[str, ModelPricing] = Field(
        default_factory=dict,
        description="Pricing by model name"
    )
    
    @classmethod
    def default(cls) -> 'PricingConfig':
        """Get default pricing configuration"""
        return cls(
            models={
                # Anthropic Claude models
                "claude-3-opus-20240229": ModelPricing(
                    input_cost_per_million=15.0,
                    output_cost_per_million=75.0
                ),
                "claude-3-5-sonnet-20241022": ModelPricing(
                    input_cost_per_million=3.0,
                    output_cost_per_million=15.0
                ),
                "claude-3-haiku-20240307": ModelPricing(
                    input_cost_per_million=0.25,
                    output_cost_per_million=1.25
                ),
                # OpenAI GPT models
                "gpt-4-turbo-preview": ModelPricing(
                    input_cost_per_million=10.0,
                    output_cost_per_million=30.0
                ),
                "gpt-4": ModelPricing(
                    input_cost_per_million=30.0,
                    output_cost_per_million=60.0
                ),
                "gpt-3.5-turbo": ModelPricing(
                    input_cost_per_million=0.5,
                    output_cost_per_million=1.5
                ),
            }
        )
    
    def get_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Get pricing for a model"""
        return self.models.get(model_name)
    
    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a model and token usage"""
        pricing = self.get_pricing(model_name)
        if pricing:
            return pricing.calculate_cost(input_tokens, output_tokens)
        # Default fallback pricing (Claude 3.5 Sonnet)
        default = ModelPricing(input_cost_per_million=3.0, output_cost_per_million=15.0)
        return default.calculate_cost(input_tokens, output_tokens)


class ModelRegistry(BaseModel):
    """Registry of available models and their configurations"""
    models: Dict[str, ModelConfig] = Field(
        default_factory=dict,
        description="Models by name"
    )
    
    @classmethod
    def default(cls) -> 'ModelRegistry':
        """Get default model registry"""
        return cls(
            models={
                # Anthropic models
                "claude-3-opus-20240229": ModelConfig(
                    name="claude-3-opus-20240229",
                    provider="anthropic",
                    default_max_tokens=4096
                ),
                "claude-3-5-sonnet-20241022": ModelConfig(
                    name="claude-3-5-sonnet-20241022",
                    provider="anthropic",
                    default_max_tokens=32768
                ),
                "claude-3-haiku-20240307": ModelConfig(
                    name="claude-3-haiku-20240307",
                    provider="anthropic",
                    default_max_tokens=4096
                ),
                # OpenAI models
                "gpt-4-turbo-preview": ModelConfig(
                    name="gpt-4-turbo-preview",
                    provider="openai",
                    default_max_tokens=4096
                ),
                "gpt-4": ModelConfig(
                    name="gpt-4",
                    provider="openai",
                    default_max_tokens=4096
                ),
                "gpt-3.5-turbo": ModelConfig(
                    name="gpt-3.5-turbo",
                    provider="openai",
                    default_max_tokens=4096
                ),
            }
        )
    
    def get_model(self, model_name: str) -> Optional[ModelConfig]:
        """Get model configuration"""
        return self.models.get(model_name)
    
    def register_model(self, model: ModelConfig) -> None:
        """Register a new model"""
        self.models[model.name] = model
    
    def list_models_by_provider(self, provider: str) -> list[ModelConfig]:
        """List all models for a provider"""
        return [m for m in self.models.values() if m.provider == provider]















