"""
Google Gemini provider implementation
"""

from typing import List, Dict, Any, Optional
import os

from ..agents import GeminiAgent
from ..exceptions import ConfigurationError


class GeminiProvider:
    """Provider for Google Gemini models"""
    
    # Official Gemini models
    MODELS = [
        "gemini-pro",
        "gemini-pro-vision",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]
    
    # Model metadata
    MODEL_INFO = {
        "gemini-pro": {
            "name": "Gemini Pro",
            "context_window": 32768,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.50,
            "cost_per_1m_output": 1.50,
        },
        "gemini-pro-vision": {
            "name": "Gemini Pro Vision",
            "context_window": 16384,
            "max_output_tokens": 2048,
            "cost_per_1m_input": 0.25,
            "cost_per_1m_output": 0.50,
        },
        "gemini-1.5-pro": {
            "name": "Gemini 1.5 Pro",
            "context_window": 1000000,  # 1M tokens!
            "max_output_tokens": 8192,
            "cost_per_1m_input": 3.50,
            "cost_per_1m_output": 10.50,
        },
        "gemini-1.5-flash": {
            "name": "Gemini 1.5 Flash",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.35,
            "cost_per_1m_output": 1.05,
        },
    }
    
    @property
    def name(self) -> str:
        return "gemini"
    
    @property
    def display_name(self) -> str:
        return "Google Gemini"
    
    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> GeminiAgent:
        """
        Create a Gemini agent instance.
        
        Args:
            model: Gemini model identifier
            name: Optional agent name (defaults to model-based name)
            **config: Configuration options
                - api_key: Google API key (or use GOOGLE_API_KEY env var)
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        
        Note:
            Full Gemini implementation requires google-generativeai package.
            Install with: pip install google-generativeai
        """
        if model not in self.MODELS:
            raise ValueError(
                f"Model {model} not supported by Gemini provider. "
                f"Available models: {', '.join(self.MODELS)}"
            )
        
        # Generate a friendly name if not provided
        if name is None:
            # Extract version from model (e.g., "pro" from "gemini-pro")
            parts = model.split('-')
            if len(parts) >= 2:
                name = f"gemini-{parts[1]}"
            else:
                name = model
        
        return GeminiAgent(
            name=name,
            model=model,
            api_key=config.get('api_key')
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate Gemini configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Check for API key
        api_key = config.get('api_key') or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "Google API key required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key in config."
            )
        
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Return required environment variables"""
        return ['GOOGLE_API_KEY']
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific Gemini model"""
        return self.MODEL_INFO.get(model)
    
    def supports_streaming(self) -> bool:
        """Gemini supports streaming responses"""
        return True
    
    def get_capabilities(self) -> List[str]:
        """Get Gemini capabilities"""
        caps = ['text-generation', 'function-calling']
        
        # Add vision for vision models
        if 'vision' in self.name or '1.5' in self.name:
            caps.append('vision')
        
        # Gemini 1.5 has huge context
        if '1.5' in self.name:
            caps.append('ultra-long-context')  # 1M tokens!
        
        return caps
