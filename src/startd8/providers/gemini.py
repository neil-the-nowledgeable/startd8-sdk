"""
Google Gemini provider implementation
"""

from typing import List, Dict, Any, Optional
import os
import logging

from ..agents import GeminiAgent
from ..exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Provider for Google Gemini models"""
    
    # Official Gemini models (hardcoded baseline)
    # Note: All Gemini 1.x models are retired and return 404
    HARDCODED_MODELS = [
        # Gemini 3.x family (Latest - November/December 2025)
        "gemini-3-pro-preview",       # Most powerful, reasoning-first
        "gemini-3-flash-preview",     # Complex multimodal understanding
        # Gemini 2.5 family
        "gemini-2.5-pro",             # Advanced reasoning and coding
        "gemini-2.5-flash",           # Fast responses (default in ChatGPT-style)
        "gemini-2.5-flash-lite",      # Fast, low-cost, high-performance
        # Gemini 2.0 family (retiring March 2026)
        "gemini-2.0-flash",           # Recommended default - stable
        "gemini-2.0-flash-lite",      # Ultra-efficient for simple tasks
        # Legacy (retired - return 404)
        "gemini-1.5-flash",           # Retired
        "gemini-1.5-pro",             # Retired
    ]
    
    @classmethod
    def _get_models(cls) -> List[str]:
        """Get merged list of hardcoded and discovered models"""
        try:
            from ..model_discovery import ModelDiscoveryService
            # Use default config dir
            discovery = ModelDiscoveryService()
            return discovery.merge_models('gemini', cls.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to load discovered models (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "gemini", "operation": "model_discovery"}
            )
            return cls.HARDCODED_MODELS.copy()
        except Exception as e:
            logger.warning(
                f"Unexpected error loading discovered models: {e}",
                exc_info=True,
                extra={"provider": "gemini", "operation": "model_discovery"}
            )
            return cls.HARDCODED_MODELS.copy()
    
    @classmethod
    def _get_models_instance(cls) -> List[str]:
        """Get models for an instance"""
        return cls._get_models()
    
    @property
    def MODELS(self) -> List[str]:
        """Dynamic models list that includes discovered models"""
        return self._get_models_instance()
    
    # Model name mapping for deprecated/retired models
    MODEL_MAPPING = {
        "gemini-pro": "gemini-2.0-flash",           # Retired
        "gemini-pro-vision": "gemini-2.0-flash",    # Retired
        "gemini-1.5-flash": "gemini-2.0-flash",     # Retired - returns 404
        "gemini-1.5-pro": "gemini-2.5-pro",         # Retired - returns 404
    }
    
    # Model metadata
    MODEL_INFO = {
        # Gemini 3.x family (Latest)
        "gemini-3-pro-preview": {
            "name": "Gemini 3 Pro",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 1.25,
            "cost_per_1m_output": 5.00,
        },
        "gemini-3-flash-preview": {
            "name": "Gemini 3 Flash",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.10,
            "cost_per_1m_output": 0.40,
        },
        # Gemini 2.5 family
        "gemini-2.5-pro": {
            "name": "Gemini 2.5 Pro",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 1.25,
            "cost_per_1m_output": 5.00,
        },
        "gemini-2.5-flash": {
            "name": "Gemini 2.5 Flash",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.15,
            "cost_per_1m_output": 0.60,
        },
        "gemini-2.5-flash-lite": {
            "name": "Gemini 2.5 Flash Lite",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.075,
            "cost_per_1m_output": 0.30,
        },
        # Gemini 2.0 family
        "gemini-2.0-flash": {
            "name": "Gemini 2.0 Flash",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.10,
            "cost_per_1m_output": 0.40,
        },
        "gemini-2.0-flash-lite": {
            "name": "Gemini 2.0 Flash Lite",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.075,
            "cost_per_1m_output": 0.30,
        },
        # Legacy models (retired - return 404)
        "gemini-1.5-pro": {
            "name": "Gemini 1.5 Pro (retired)",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 3.50,
            "cost_per_1m_output": 10.50,
            "deprecated": True,
            "replacement": "gemini-2.5-pro",
        },
        "gemini-1.5-flash": {
            "name": "Gemini 1.5 Flash (retired)",
            "context_window": 1000000,
            "max_output_tokens": 8192,
            "cost_per_1m_input": 0.35,
            "cost_per_1m_output": 1.05,
            "deprecated": True,
            "replacement": "gemini-2.0-flash",
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
    
    def is_model_new(self, model: str) -> bool:
        """Check if a model is newly discovered (not in hardcoded list)"""
        try:
            from ..model_discovery import ModelDiscoveryService
            discovery = ModelDiscoveryService()
            return discovery.is_model_new('gemini', model, self.HARDCODED_MODELS)
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Failed to check if model is new (import/attribute error): {e}",
                exc_info=True,
                extra={"provider": "gemini", "model": model, "operation": "is_model_new"}
            )
            return False
        except Exception as e:
            logger.warning(
                f"Unexpected error checking if model is new: {e}",
                exc_info=True,
                extra={"provider": "gemini", "model": model, "operation": "is_model_new"}
            )
            return False
    
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
                - max_tokens: Maximum tokens to generate (default: 16384)
                - temperature: Sampling temperature (default: 0.7)
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        
        Returns:
            Configured GeminiAgent instance
        
        Raises:
            ImportError: If google-genai package is not installed
        """
        # Map deprecated models to supported ones
        original_model = model
        if model in self.MODEL_MAPPING:
            mapped_model = self.MODEL_MAPPING[model]
            logger.warning(
                f"GeminiProvider: Model '{model}' is deprecated. "
                f"Mapping to '{mapped_model}'. "
                f"Please update your configuration to use '{mapped_model}' directly."
            )
            model = mapped_model
        
        # Decision 37A: be permissive about model IDs.
        # Keep a curated list for suggestions, but allow unknown models so users
        # can use newly released IDs without waiting for an SDK update.
        if model not in self.supported_models:
            logger.warning(
                f"GeminiProvider: model '{model}' not in supported_models list; "
                f"continuing anyway."
            )
        
        # Generate a friendly name if not provided
        if name is None:
            # Extract version from model (e.g., "pro" from "gemini-pro")
            parts = model.split('-')
            if len(parts) >= 2:
                name = f"gemini-{parts[1]}"
            else:
                name = model
        
        from ..agents import GeminiAgent
        
        try:
            return GeminiAgent(
                name=name,
                model=model,  # Use mapped model, not original
                api_key=config.get('api_key'),
                max_tokens=config.get('max_tokens', 16384),  # Increased from 4096 to prevent truncation
                temperature=config.get('temperature', 0.7),
                cost_tracker=config.get('cost_tracker'),
                budget_manager=config.get('budget_manager'),
                safety_settings=config.get('safety_settings'),
            )
        except ImportError as e:
            # Provide helpful installation instructions
            import sys
            python_exe = sys.executable
            error_msg = str(e)
            
            # Check if running from pipx
            if 'pipx' in python_exe or '.local/pipx' in python_exe:
                error_msg += (
                    f"\n\n[Installation Help]\n"
                    f"You're running startd8 from pipx. To install google-genai:\n"
                    f"  pipx inject startd8 google-genai\n\n"
                    f"Or install with extras:\n"
                    f"  pipx install startd8[gemini]\n"
                )
            else:
                error_msg += (
                    f"\n\n[Installation Help]\n"
                    f"Install the package using:\n"
                    f"  {python_exe} -m pip install google-genai\n\n"
                    f"Or install startd8 with Gemini support:\n"
                    f"  {python_exe} -m pip install 'startd8[gemini]'\n"
                )
            
            raise ImportError(error_msg) from e
    
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
    
    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        """
        Get Gemini capabilities.

        Capabilities are model-dependent (e.g., vision and ultra-long-context).
        If `model` is None, returns a provider-level union across supported models.
        """
        caps = ['text-generation', 'function-calling']

        model_lower = (model or "").lower().strip()

        # Provider-level union (when model not specified)
        if not model_lower:
            models = [m.lower() for m in self.MODELS]
            if any(("vision" in m) or ("1.5" in m) for m in models):
                caps.append('vision')
            if any("1.5" in m for m in models):
                caps.append('ultra-long-context')  # 1M tokens!
            return caps

        # Model-specific capabilities
        if ("vision" in model_lower) or ("1.5" in model_lower):
            caps.append('vision')
        if "1.5" in model_lower:
            caps.append('ultra-long-context')  # 1M tokens!

        return caps
