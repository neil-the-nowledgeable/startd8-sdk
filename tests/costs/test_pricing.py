"""
Unit tests for PricingService
"""

import pytest
from pathlib import Path
import tempfile
import json

from startd8.costs.pricing import PricingService, ModelPricing


class TestPricingService:
    """Tests for PricingService"""
    
    def test_default_pricing_loaded(self):
        """Test that default pricing is loaded on initialization"""
        pricing = PricingService()
        
        # Check some known models
        assert pricing.get_pricing("claude-3-5-sonnet-20241022") is not None
        assert pricing.get_pricing("gpt-4o") is not None
    
    def test_calculate_cost_breakdown(self):
        """Test cost calculation for input and output tokens"""
        pricing = PricingService()
        
        # Claude 3.5 Sonnet: $3/$15 per million
        input_cost, output_cost = pricing.calculate_cost_breakdown(
            "claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500
        )
        
        # Expected: (1000/1M * 3) + (500/1M * 15)
        assert abs(input_cost - 0.003) < 0.0001
        assert abs(output_cost - 0.0075) < 0.0001
    
    def test_calculate_total_cost(self):
        """Test total cost calculation"""
        pricing = PricingService()
        
        total = pricing.calculate_total_cost(
            "claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert abs(total - 0.0105) < 0.0001
    
    def test_get_provider_for_model(self):
        """Test provider detection"""
        pricing = PricingService()
        
        assert pricing.get_provider_for_model("claude-3-5-sonnet-20241022") == "anthropic"
        assert pricing.get_provider_for_model("gpt-4o") == "openai"
        assert pricing.get_provider_for_model("gemini-1.5-pro") == "google"
    
    def test_update_pricing(self):
        """Test updating pricing for a model"""
        pricing = PricingService()
        
        # Update pricing
        pricing.update_pricing(
            "test-model",
            input_cost_per_million=5.0,
            output_cost_per_million=10.0,
            provider="test-provider"
        )
        
        # Verify update
        model_pricing = pricing.get_pricing("test-model")
        assert model_pricing is not None
        assert model_pricing.input_cost_per_million == 5.0
        assert model_pricing.output_cost_per_million == 10.0
        assert model_pricing.provider == "test-provider"
    
    def test_fallback_pricing_for_unknown_model(self):
        """Test that unknown models use fallback pricing"""
        pricing = PricingService()
        
        # Unknown model should still return costs (fallback)
        input_cost, output_cost = pricing.calculate_cost_breakdown(
            "unknown-model-xyz",
            input_tokens=1000,
            output_tokens=500
        )
        
        # Fallback is $3/$15 per million
        assert input_cost > 0
        assert output_cost > 0
    
    def test_estimate_cost_from_characters(self):
        """Test cost estimation from character counts"""
        pricing = PricingService()
        
        # Rough estimate: 4 chars per token
        prompt_chars = 4000  # ~1000 tokens
        expected_output_chars = 2000  # ~500 tokens
        
        estimated_cost = pricing.estimate_cost(
            "claude-3-5-sonnet-20241022",
            prompt_chars=prompt_chars,
            expected_output_chars=expected_output_chars
        )
        
        # Should be close to 0.0105
        assert 0.008 < estimated_cost < 0.015
    
    def test_save_and_load_pricing_file(self):
        """Test saving and loading pricing from file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pricing_file = Path(tmpdir) / "pricing.json"
            
            # Create pricing service and add custom model
            pricing = PricingService(pricing_file=pricing_file)
            pricing.update_pricing(
                "custom-model",
                input_cost_per_million=2.0,
                output_cost_per_million=8.0,
                provider="custom"
            )
            
            # Save to file
            pricing.save_pricing_file()
            
            # Load in new instance
            pricing2 = PricingService(pricing_file=pricing_file)
            
            # Verify custom model was loaded
            custom_pricing = pricing2.get_pricing("custom-model")
            assert custom_pricing is not None
            assert custom_pricing.input_cost_per_million == 2.0
            assert custom_pricing.output_cost_per_million == 8.0
    
    def test_list_models(self):
        """Test listing all models with pricing"""
        pricing = PricingService()
        
        models = pricing.list_models()
        
        assert len(models) > 0
        assert "claude-3-5-sonnet-20241022" in models
        assert "gpt-4o" in models

