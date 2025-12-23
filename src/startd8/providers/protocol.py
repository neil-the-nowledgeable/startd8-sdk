"""
Provider protocol defining the interface for agent providers
"""

from typing import Protocol, runtime_checkable, List, Dict, Any, Optional
from abc import abstractmethod


@runtime_checkable
class AgentProvider(Protocol):
    """
    Protocol defining the interface for agent providers.
    
    Providers are responsible for creating agent instances and
    validating configuration for their supported models.
    
    Example implementation:
        class MyProvider:
            @property
            def name(self) -> str:
                return "my-provider"
            
            @property
            def display_name(self) -> str:
                return "My Custom Provider"
            
            @property
            def supported_models(self) -> List[str]:
                return ["model-v1", "model-v2"]
            
            def create_agent(self, model: str, name: Optional[str] = None, **config):
                # Create and return agent instance
                return MyAgent(name=name or model, model=model, **config)
            
            def validate_config(self, config: Dict[str, Any]) -> bool:
                # Validate configuration
                return True
            
            def get_required_env_vars(self) -> List[str]:
                return ["MY_API_KEY"]
    """
    
    @property
    def name(self) -> str:
        """
        Unique provider identifier (e.g., 'anthropic', 'openai').
        
        This should be lowercase and URL-friendly.
        """
        ...
    
    @property
    def display_name(self) -> str:
        """
        Human-readable provider name (e.g., 'Anthropic Claude', 'OpenAI GPT')
        """
        ...
    
    @property
    def supported_models(self) -> List[str]:
        """
        List of model identifiers this provider supports.
        
        Returns:
            List of model names/IDs (e.g., ['gpt-4', 'gpt-3.5-turbo'])
        """
        ...
    
    def create_agent(
        self, 
        model: str, 
        name: Optional[str] = None,
        **config
    ) -> 'BaseAgent':
        """
        Create an agent instance for the specified model.
        
        Args:
            model: Model identifier (e.g., 'claude-3-opus-20240229')
            name: Optional agent name override (defaults to model-based name)
            **config: Provider-specific configuration (api_key, max_tokens, etc.)
            
        Returns:
            Configured BaseAgent instance
            
        Raises:
            ValueError: If model is not supported
            ConfigurationError: If config is invalid
        
        Example:
            agent = provider.create_agent(
                model="gpt-4",
                name="my-gpt4",
                api_key="sk-...",
                max_tokens=4096
            )
        """
        ...
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate provider configuration.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            True if valid
            
        Raises:
            ConfigurationError: If configuration is invalid (with helpful message)
        
        Example:
            try:
                provider.validate_config({"api_key": "sk-..."})
            except ConfigurationError as e:
                print(f"Invalid config: {e}")
        """
        ...
    
    def get_required_env_vars(self) -> List[str]:
        """
        Return list of required environment variables.
        
        Used for documentation and validation.
        
        Returns:
            List of environment variable names
        
        Example:
            ['ANTHROPIC_API_KEY', 'ANTHROPIC_API_URL']
        """
        ...
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a specific model (optional).
        
        Args:
            model: Model identifier
            
        Returns:
            Dictionary with model metadata or None if not available
        
        Example:
            {
                "name": "gpt-4",
                "context_window": 8192,
                "max_output_tokens": 4096,
                "cost_per_1k_input": 0.03,
                "cost_per_1k_output": 0.06
            }
        """
        return None
    
    def supports_streaming(self) -> bool:
        """
        Whether this provider supports streaming responses (optional).
        
        Returns:
            True if streaming is supported
        """
        return False
    
    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        """
        Get list of capabilities (optional).

        If `model` is provided, returns capabilities specific to that model.
        If `model` is None, returns provider-level capabilities (often a union
        across supported models).
        
        Returns:
            List of capability identifiers
        
        Example:
            ['text-generation', 'function-calling', 'vision']
        """
        return ['text-generation']
