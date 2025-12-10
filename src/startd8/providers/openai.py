"""
OpenAI GPT provider implementation
"""

from typing import List, Dict, Any, Optional
import os

from ..agents import GPT4Agent, OpenAICompatibleAgent
from ..exceptions import ConfigurationError


class OpenAIProvider:
    """Provider for OpenAI GPT models"""
    
    # Official OpenAI models
    MODELS = [
        "gpt-4",
        "gpt-4-turbo-preview",
        "gpt-4-turbo",
        "gpt-4-1106-preview",
        "gpt-4-0125-preview",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-1106",
    ]
    
    # Model metadata
    MODEL_INFO = {
        "gpt-4": {
            "name": "GPT-4",
            "context_window": 8192,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 30.00,
            "cost_per_1m_output": 60.00,
        },
        "gpt-4-turbo-preview": {
            "name": "GPT-4 Turbo Preview",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 10.00,
            "cost_per_1m_output": 30.00,
        },
        "gpt-4-turbo": {
            "name": "GPT-4 Turbo",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 10.00,
            "cost_per_1m_output": 30.00,
        },
        "gpt-3.5-turbo": {
            "name": "GPT-3.5 Turbo",
            "context_window": 4096,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 0.50,
            "cost_per_1m_output": 1.50,
        },
        "gpt-3.5-turbo-16k": {
            "name": "GPT-3.5 Turbo 16K",
            "context_window": 16384,
            "max_output_tokens": 4096,
            "cost_per_1m_input": 3.00,
            "cost_per_1m_output": 4.00,
        },
    }
    
    @property
    def name(self) -> str:
        return "openai"
    
    @property
    def display_name(self) -> str:
        return "OpenAI GPT"
    
    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> GPT4Agent:
        """
        Create an OpenAI GPT agent instance.
        
        Args:
            model: GPT model identifier
            name: Optional agent name (defaults to model-based name)
            **config: Configuration options
                - api_key: OpenAI API key (or use OPENAI_API_KEY env var)
                - max_tokens: Maximum tokens to generate (default 4096)
                - cost_tracker: Optional cost tracker instance
                - budget_manager: Optional budget manager instance
        """
        if model not in self.MODELS:
            raise ValueError(
                f"Model {model} not supported by OpenAI provider. "
                f"Available models: {', '.join(self.MODELS)}"
            )
        
        # Generate a friendly name if not provided
        if name is None:
            # Use model name as-is or create short version
            name = model.replace("gpt-", "gpt").replace("-preview", "")
        
        return GPT4Agent(
            name=name,
            model=model,
            api_key=config.get('api_key'),
            max_tokens=config.get('max_tokens', 4096),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager')
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate OpenAI configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Check for API key
        api_key = config.get('api_key') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ConfigurationError(
                "OpenAI API key required. "
                "Set OPENAI_API_KEY environment variable or pass api_key in config."
            )
        
        # Validate max_tokens if provided
        max_tokens = config.get('max_tokens')
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ConfigurationError(
                    f"max_tokens must be a positive integer, got: {max_tokens}"
                )
            if max_tokens > 4096:
                raise ConfigurationError(
                    f"max_tokens ({max_tokens}) exceeds maximum allowed (4096)"
                )
        
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Return required environment variables"""
        return ['OPENAI_API_KEY']
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific GPT model"""
        return self.MODEL_INFO.get(model)
    
    def supports_streaming(self) -> bool:
        """OpenAI supports streaming responses"""
        return True
    
    def get_capabilities(self) -> List[str]:
        """Get OpenAI capabilities"""
        return [
            'text-generation',
            'function-calling',
            'vision',  # GPT-4 Turbo and Vision models
            'json-mode',
        ]


class OllamaProvider:
    """Provider for Ollama (local LLM runtime)"""
    
    # Common Ollama models (user may have others installed)
    COMMON_MODELS = [
        "llama2",
        "llama2:13b",
        "llama2:70b",
        "codellama",
        "mistral",
        "mixtral",
        "phi",
        "neural-chat",
    ]
    
    @property
    def name(self) -> str:
        return "ollama"
    
    @property
    def display_name(self) -> str:
        return "Ollama (Local)"
    
    @property
    def supported_models(self) -> List[str]:
        return self.COMMON_MODELS.copy()
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> OpenAICompatibleAgent:
        """
        Create an Ollama agent instance.
        
        Args:
            model: Ollama model identifier
            name: Optional agent name
            **config: Configuration options
                - base_url: Ollama API URL (default: http://localhost:11434/v1)
                - max_tokens: Maximum tokens to generate
        """
        if name is None:
            name = f"ollama-{model}"
        
        base_url = config.get('base_url', 'http://localhost:11434/v1')
        
        return OpenAICompatibleAgent(
            name=name,
            model=model,
            api_key=None,  # Ollama doesn't need API key for localhost
            base_url=base_url,
            max_tokens=config.get('max_tokens', 4096),
            cost_tracker=config.get('cost_tracker'),
            budget_manager=config.get('budget_manager')
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Ollama configuration"""
        # Ollama doesn't require API key for local use
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Ollama doesn't require environment variables for local use"""
        return []
    
    def supports_streaming(self) -> bool:
        return True
    
    def get_capabilities(self) -> List[str]:
        return ['text-generation', 'local-execution']
