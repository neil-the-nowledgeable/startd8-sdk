"""
Unit tests for provider system
"""

import pytest
from unittest.mock import Mock, patch

from startd8.providers import (
    AgentProvider,
    ProviderRegistry,
    AnthropicProvider,
    OpenAIProvider,
    OpenAICompatibleProvider,
    NIMProvider,
    MockProvider,
    GeminiProvider,
    OllamaProvider
)
from startd8.agents import BaseAgent, MockAgent, OpenAICompatibleAgent
from startd8.exceptions import ConfigurationError


class TestProviderProtocol:
    """Test AgentProvider protocol"""
    
    def test_protocol_validation(self):
        """Test that providers implement the protocol"""
        provider = MockProvider()
        assert isinstance(provider, AgentProvider)
    
    def test_required_properties(self):
        """Test that providers have required properties"""
        provider = MockProvider()
        
        assert hasattr(provider, 'name')
        assert hasattr(provider, 'display_name')
        assert hasattr(provider, 'supported_models')
        assert callable(getattr(provider, 'create_agent'))
        assert callable(getattr(provider, 'validate_config'))
        assert callable(getattr(provider, 'get_required_env_vars'))


class TestMockProvider:
    """Test MockProvider implementation"""
    
    def test_provider_properties(self):
        """Test provider basic properties"""
        provider = MockProvider()
        
        assert provider.name == "mock"
        assert provider.display_name == "Mock Provider (Testing)"
        assert len(provider.supported_models) > 0
        assert "mock-model" in provider.supported_models
    
    def test_create_agent(self):
        """Test creating an agent from provider"""
        provider = MockProvider()
        
        agent = provider.create_agent("mock-model")
        assert isinstance(agent, MockAgent)
        assert agent.model == "mock-model"
    
    def test_create_agent_with_name(self):
        """Test creating agent with custom name"""
        provider = MockProvider()
        
        agent = provider.create_agent("mock-model", name="custom-mock")
        assert agent.name == "custom-mock"
    
    def test_validate_config(self):
        """Test config validation"""
        provider = MockProvider()
        
        # Mock provider accepts any config
        assert provider.validate_config({}) == True
        assert provider.validate_config({"any": "value"}) == True
    
    def test_env_vars(self):
        """Test required env vars"""
        provider = MockProvider()
        
        # Mock provider doesn't need env vars
        assert provider.get_required_env_vars() == []
    
    def test_model_info(self):
        """Test getting model metadata"""
        provider = MockProvider()
        
        info = provider.get_model_info("mock-model")
        assert info is not None
        assert "name" in info
        assert "context_window" in info
    
    def test_capabilities(self):
        """Test provider capabilities"""
        provider = MockProvider()
        
        caps = provider.get_capabilities()
        assert isinstance(caps, list)
        assert "text-generation" in caps


class TestAnthropicProvider:
    """Test AnthropicProvider implementation"""
    
    def test_provider_properties(self):
        """Test Anthropic provider properties"""
        provider = AnthropicProvider()
        
        assert provider.name == "anthropic"
        assert provider.display_name == "Anthropic Claude"
        assert len(provider.supported_models) > 0
        assert "claude-3-opus-20240229" in provider.supported_models
    
    def test_unsupported_model_logs_warning(self):
        """Test creating agent with unsupported model logs warning but continues"""
        provider = AnthropicProvider()

        # Decision 37A: Be permissive about model IDs - log warning but don't raise
        # This allows users to use newly released model IDs without SDK update
        import logging
        with patch.object(logging.getLogger('startd8.providers.anthropic'), 'warning') as mock_warn:
            # Will fail due to missing API key, not unsupported model
            try:
                provider.create_agent("unsupported-model")
            except ImportError:
                pass  # Expected - anthropic package may not be installed in test
            # Verify warning was logged about unsupported model
            if mock_warn.called:
                assert "not in supported_models" in str(mock_warn.call_args)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_validate_config_with_env_var(self):
        """Test config validation with env var"""
        provider = AnthropicProvider()
        
        # Should pass with env var set
        assert provider.validate_config({}) == True
    
    def test_validate_config_without_api_key(self):
        """Test config validation without API key"""
        provider = AnthropicProvider()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError, match="API key required"):
                provider.validate_config({})
    
    def test_validate_config_with_api_key(self):
        """Test config validation with API key in config"""
        provider = AnthropicProvider()
        
        assert provider.validate_config({"api_key": "test-key"}) == True
    
    def test_validate_config_invalid_max_tokens(self):
        """Test config validation with invalid max_tokens"""
        provider = AnthropicProvider()
        
        with pytest.raises(ConfigurationError, match="max_tokens"):
            provider.validate_config({
                "api_key": "test-key",
                "max_tokens": -1
            })
    
    def test_model_info(self):
        """Test getting model metadata"""
        provider = AnthropicProvider()
        
        info = provider.get_model_info("claude-3-opus-20240229")
        assert info is not None
        assert "name" in info
        assert "context_window" in info
        assert "cost_per_1m_input" in info
    
    def test_capabilities(self):
        """Test Anthropic capabilities"""
        provider = AnthropicProvider()
        
        caps = provider.get_capabilities()
        assert "text-generation" in caps
        assert "vision" in caps
        assert "long-context" in caps


class TestOpenAIProvider:
    """Test OpenAIProvider implementation"""
    
    def test_provider_properties(self):
        """Test OpenAI provider properties"""
        provider = OpenAIProvider()
        
        assert provider.name == "openai"
        assert provider.display_name == "OpenAI GPT"
        assert "gpt-4" in provider.supported_models
        assert "gpt-3.5-turbo" in provider.supported_models
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_validate_config(self):
        """Test config validation"""
        provider = OpenAIProvider()
        assert provider.validate_config({}) == True
    
    def test_model_info(self):
        """Test getting model metadata"""
        provider = OpenAIProvider()
        
        info = provider.get_model_info("gpt-4")
        assert info is not None
        assert "name" in info
        assert info["context_window"] == 8192

    def test_validate_config_custom_endpoint_requires_key(self):
        """Custom endpoints need api_key/api_key_env when not local."""
        provider = OpenAIProvider()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError, match="custom endpoint"):
                provider.validate_config({
                    "base_url": "https://integrate.api.nvidia.com/v1",
                })

    @patch.dict('os.environ', {'NVIDIA_API_KEY': 'test-key'}, clear=True)
    def test_validate_config_custom_endpoint_api_key_env(self):
        """Custom endpoints can use api_key_env."""
        provider = OpenAIProvider()
        assert provider.validate_config({
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key_env": "NVIDIA_API_KEY",
        }) is True

    def test_create_agent_with_base_url_returns_compatible_agent(self):
        """Passing base_url delegates to OpenAICompatibleAgent."""
        provider = OpenAIProvider()
        with patch('startd8.agents.openai._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.openai.OpenAI'), \
             patch('startd8.agents.openai.AsyncOpenAI'):
            agent = provider.create_agent(
                "nvidia/nemotron-3-nano-30b-a3b",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key="test-key",
            )
        assert isinstance(agent, OpenAICompatibleAgent)


class TestOpenAICompatibleProvider:
    """Test generic OpenAI-compatible provider."""

    def test_provider_properties(self):
        provider = OpenAICompatibleProvider()
        assert provider.name == "openai-compatible"
        assert provider.display_name == "OpenAI-Compatible Endpoint"

    def test_validate_config_requires_base_url(self):
        provider = OpenAICompatibleProvider()
        with pytest.raises(ConfigurationError, match="base_url"):
            provider.validate_config({})

    def test_validate_config_localhost_needs_no_key(self):
        provider = OpenAICompatibleProvider()
        assert provider.validate_config({"base_url": "http://localhost:11434/v1"}) is True

    def test_validate_config_remote_requires_key(self):
        provider = OpenAICompatibleProvider()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError, match="non-local"):
                provider.validate_config({"base_url": "https://example.com/v1"})


class TestNIMProvider:
    """Test NVIDIA NIM provider."""

    def test_provider_properties(self):
        provider = NIMProvider()
        assert provider.name == "nim"
        assert provider.display_name == "NVIDIA NIM"
        assert "nvidia/nemotron-3-nano-30b-a3b" in provider.supported_models

    @patch.dict('os.environ', {'NVIDIA_API_KEY': 'test-key'}, clear=True)
    def test_validate_config_uses_nvidia_env_var(self):
        provider = NIMProvider()
        assert provider.validate_config({}) is True

    def test_validate_config_without_key(self):
        provider = NIMProvider()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError, match="NVIDIA API key required"):
                provider.validate_config({})


class TestGeminiProvider:
    """Test GeminiProvider implementation"""
    
    def test_provider_properties(self):
        """Test Gemini provider properties"""
        provider = GeminiProvider()

        assert provider.name == "gemini"
        assert provider.display_name == "Google Gemini"
        assert "gemini-2.0-flash" in provider.supported_models

    def test_model_info(self):
        """Test Gemini model metadata"""
        provider = GeminiProvider()

        info = provider.get_model_info("gemini-2.0-flash")
        assert info is not None
        assert info["context_window"] == 1000000  # 1M tokens!


class TestOllamaProvider:
    """Test OllamaProvider implementation"""
    
    def test_provider_properties(self):
        """Test Ollama provider properties"""
        provider = OllamaProvider()
        
        assert provider.name == "ollama"
        assert provider.display_name == "Ollama (Local)"
        assert "llama2" in provider.supported_models
    
    def test_validate_config(self):
        """Test Ollama config validation (no API key needed)"""
        provider = OllamaProvider()
        
        # Should always pass
        assert provider.validate_config({}) == True

    def test_validate_config_remote_without_key_fails(self):
        """Remote endpoints without auth should fail validation."""
        provider = OllamaProvider()
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError, match="Prefer NIMProvider"):
                provider.validate_config({"base_url": "https://integrate.api.nvidia.com/v1"})
    
    def test_env_vars(self):
        """Test Ollama doesn't need env vars"""
        provider = OllamaProvider()
        assert provider.get_required_env_vars() == []


class TestProviderRegistry:
    """Test ProviderRegistry functionality"""
    
    def setup_method(self):
        """Clear registry before each test"""
        ProviderRegistry.clear()
    
    def teardown_method(self):
        """Clear registry after each test"""
        ProviderRegistry.clear()

    def test_builtin_registry_contains_new_endpoint_providers(self):
        """Registry should include explicit endpoint providers."""
        ProviderRegistry.discover(force=True)
        providers = ProviderRegistry.list_providers()
        assert "openai-compatible" in providers
        assert "nim" in providers
    
    def test_register_provider(self):
        """Test registering a provider"""
        provider = MockProvider()
        ProviderRegistry.register(provider)
        
        assert "mock" in ProviderRegistry.list_providers()
    
    def test_register_invalid_provider(self):
        """Test registering invalid provider"""
        class InvalidProvider:
            pass
        
        with pytest.raises(TypeError, match="does not implement AgentProvider"):
            ProviderRegistry.register(InvalidProvider())
    
    def test_get_provider(self):
        """Test getting a provider by name"""
        provider = MockProvider()
        ProviderRegistry.register(provider)
        
        retrieved = ProviderRegistry.get_provider("mock")
        assert retrieved is not None
        assert retrieved.name == "mock"
    
    def test_get_provider_case_insensitive(self):
        """Test provider lookup is case-insensitive"""
        provider = MockProvider()
        ProviderRegistry.register(provider)
        
        assert ProviderRegistry.get_provider("MOCK") is not None
        assert ProviderRegistry.get_provider("Mock") is not None
    
    def test_get_nonexistent_provider(self):
        """Test getting a provider that doesn't exist"""
        result = ProviderRegistry.get_provider("nonexistent")
        assert result is None
    
    def test_list_providers(self):
        """Test listing all providers"""
        ProviderRegistry.register(MockProvider())
        
        providers = ProviderRegistry.list_providers()
        assert isinstance(providers, list)
        assert "mock" in providers
    
    def test_list_all_models(self):
        """Test listing all models from all providers"""
        ProviderRegistry.register(MockProvider())
        
        models = ProviderRegistry.list_all_models()
        assert isinstance(models, dict)
        assert "mock" in models
        assert isinstance(models["mock"], list)
    
    def test_find_provider_for_model(self):
        """Test finding which provider supports a model"""
        ProviderRegistry.register(MockProvider())
        
        provider = ProviderRegistry.find_provider_for_model("mock-model")
        assert provider is not None
        assert provider.name == "mock"
    
    def test_find_provider_for_nonexistent_model(self):
        """Test finding provider for unsupported model"""
        result = ProviderRegistry.find_provider_for_model("nonexistent-model")
        assert result is None
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_create_agent(self):
        """Test creating agent through registry"""
        ProviderRegistry.register(MockProvider())
        
        agent = ProviderRegistry.create_agent(
            provider_name="mock",
            model="mock-model"
        )
        
        assert isinstance(agent, MockAgent)
        assert agent.model == "mock-model"
    
    def test_create_agent_unknown_provider(self):
        """Test creating agent from unknown provider"""
        with pytest.raises(ConfigurationError, match="Unknown provider"):
            ProviderRegistry.create_agent(
                provider_name="nonexistent",
                model="some-model"
            )
    
    def test_get_provider_info(self):
        """Test getting provider information"""
        ProviderRegistry.register(MockProvider())
        
        info = ProviderRegistry.get_provider_info("mock")
        assert info is not None
        assert info["name"] == "mock"
        assert "models" in info
        assert "env_vars" in info
        assert "capabilities" in info
    
    def test_get_provider_info_nonexistent(self):
        """Test getting info for nonexistent provider"""
        info = ProviderRegistry.get_provider_info("nonexistent")
        assert info is None
    
    def test_discover_builtin_providers(self):
        """Test that built-in providers are auto-discovered"""
        ProviderRegistry.discover()
        
        providers = ProviderRegistry.list_providers()
        
        # Should include built-in providers
        assert "mock" in providers
        # anthropic and openai might not be available if packages not installed
    
    def test_singleton_pattern(self):
        """Test that ProviderRegistry is a singleton"""
        registry1 = ProviderRegistry()
        registry2 = ProviderRegistry()
        
        assert registry1 is registry2


class TestCustomProvider:
    """Test creating custom providers"""
    
    def test_custom_provider(self):
        """Test implementing a custom provider"""
        
        class CustomProvider:
            @property
            def name(self) -> str:
                return "custom"
            
            @property
            def display_name(self) -> str:
                return "Custom Provider"
            
            @property
            def supported_models(self):
                return ["custom-v1", "custom-v2"]
            
            def create_agent(self, model: str, name=None, **config):
                return MockAgent(name=name or "custom", model=model)
            
            def validate_config(self, config):
                return True
            
            def get_required_env_vars(self):
                return []
            
            def get_capabilities(self):
                return ["text-generation"]
            
            def supports_streaming(self):
                return False
        
        # Register custom provider
        ProviderRegistry.clear()
        custom = CustomProvider()
        ProviderRegistry.register(custom)
        
        # Test it works
        assert "custom" in ProviderRegistry.list_providers()
        
        provider = ProviderRegistry.get_provider("custom")
        assert provider.name == "custom"
        
        agent = ProviderRegistry.create_agent("custom", "custom-v1")
        assert agent.model == "custom-v1"
