"""
Mock provider for testing
"""

from typing import List, Dict, Any, Optional

from ..agents import MockAgent


class MockProvider:
    """Provider for mock agents (testing/development)"""
    
    MODELS = [
        "mock-model",
        "mock-fast",
        "mock-slow",
        "mock-expensive",
        "mock-cheap",
    ]
    
    @property
    def name(self) -> str:
        return "mock"
    
    @property
    def display_name(self) -> str:
        return "Mock Provider (Testing)"
    
    @property
    def supported_models(self) -> List[str]:
        return self.MODELS.copy()
    
    def create_agent(
        self,
        model: str,
        name: Optional[str] = None,
        **config
    ) -> MockAgent:
        """
        Create a mock agent instance.

        Args:
            model: Mock model identifier
            name: Optional agent name
            **config: Configuration options
                - timeout_config: Optional timeout configuration
                - retry_config: Optional retry configuration
        """
        if name is None:
            name = f"mock-{model.replace('mock-', '')}"

        return MockAgent(
            name=name,
            model=model,
            timeout_config=config.get('timeout_config'),
            retry_config=config.get('retry_config'),
            system_prompt=config.get('system_prompt'),
        )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Mock provider doesn't require configuration"""
        return True
    
    def get_required_env_vars(self) -> List[str]:
        """Mock provider doesn't require environment variables"""
        return []
    
    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Get metadata about mock models"""
        info = {
            "mock-model": {
                "name": "Mock Model",
                "context_window": 100000,
                "max_output_tokens": 4096,
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
            },
            "mock-fast": {
                "name": "Mock Fast Model",
                "context_window": 100000,
                "max_output_tokens": 4096,
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
                "latency_ms": 50,
            },
            "mock-slow": {
                "name": "Mock Slow Model",
                "context_window": 100000,
                "max_output_tokens": 4096,
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
                "latency_ms": 500,
            },
        }
        return info.get(model)
    
    def supports_streaming(self) -> bool:
        return False

    def get_capabilities(self, model: Optional[str] = None) -> List[str]:
        return ['text-generation', 'testing']

    def estimate_safe_output(
        self,
        model: str,
        complexity: str = "medium",
    ) -> Dict[str, int]:
        """Mock provider uses default conservative estimates."""
        complexity_limits = {
            "low": {"max_lines": 200, "max_tokens": 600, "buffer_percent": 10},
            "medium": {"max_lines": 150, "max_tokens": 500, "buffer_percent": 15},
            "high": {"max_lines": 100, "max_tokens": 350, "buffer_percent": 20},
        }
        return complexity_limits.get(complexity, complexity_limits["medium"])
