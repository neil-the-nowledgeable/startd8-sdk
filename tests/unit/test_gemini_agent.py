"""
Focused tests for Gemini agent behavior and error handling.
"""

import asyncio
import pytest

from startd8.providers.gemini import GeminiProvider
from startd8.agents import GeminiAgent


class TestGeminiAgent:
    """Test Gemini agent implementation"""

    def test_gemini_agent_requires_package(self, mock_gemini_available):
        """Verify ImportError guard exists when dependency missing."""
        if mock_gemini_available is None:  # fixture skips if unavailable
            pytest.skip("google-generativeai not installed")

        with pytest.raises(ValueError, match="Google API key required"):
            GeminiAgent(name="test-gemini", model="gemini-pro")

    def test_gemini_agent_api_key_validation(self, mock_gemini_available):
        """Test that GeminiAgent validates API key"""
        with pytest.raises(ValueError, match="Google API key required"):
            GeminiAgent(
                name="test-gemini",
                model="gemini-pro",
                api_key=None  # No API key provided
            )

    def test_gemini_agent_with_mock(self, mock_gemini_available):
        """Test GeminiAgent with mocked google-generativeai"""
        agent = GeminiAgent(
            name="test-gemini",
            model="gemini-pro",
            api_key="test-key-12345",
            max_tokens=2048,
            temperature=0.5
        )

        assert agent.name == "test-gemini"
        assert agent.model == "gemini-pro"
        assert agent.max_tokens == 2048
        assert agent.temperature == 0.5

    def test_gemini_provider_creates_agent(self):
        """Test that GeminiProvider creates agents correctly"""
        provider = GeminiProvider()

        # Test that it creates agents without instantiating them fully
        # (since that requires API key)
        assert provider.name == "gemini"
        assert "gemini-pro" in provider.supported_models
        assert len(provider.supported_models) == 4

    def test_gemini_models_list(self):
        """Test that all Gemini models are properly configured"""
        provider = GeminiProvider()

        # Verify all models have pricing info
        for model in provider.supported_models:
            info = provider.get_model_info(model)
            assert info is not None
            assert "context_window" in info
            assert "max_output_tokens" in info
            assert "cost_per_1m_input" in info
            assert "cost_per_1m_output" in info

    def test_gemini_capabilities(self):
        """Test Gemini provider declares correct capabilities"""
        provider = GeminiProvider()
        caps = provider.get_capabilities()

        # Should declare text-generation
        assert "text-generation" in caps

    def test_gemini_agent_import_error_when_unavailable(self, mock_gemini_unavailable):
        """Test that GeminiAgent raises ImportError when _GEMINI_AVAILABLE is False"""
        with pytest.raises(ImportError, match="google-generativeai package not installed"):
            GeminiAgent(name="test-gemini", model="gemini-pro", api_key="test-key")

    @pytest.mark.asyncio
    async def test_gemini_agenerate_with_mocked_api(self, gemini_agent_factory, mock_generative_model):
        """Test GeminiAgent.agenerate() with mocked GenerativeModel.generate_content and count_tokens"""
        model_instance, _, _ = mock_generative_model
        agent = gemini_agent_factory(model_instance)

        response_text, response_time_ms, token_usage = await agent.agenerate("Test prompt")

        assert response_text == "Mocked Gemini response"
        assert response_time_ms > 0
        assert token_usage.input == 100
        assert token_usage.output == 100
        assert token_usage.total == 200

        # Verify API was called
        model_instance.generate_content.assert_called_once_with("Test prompt")
        assert model_instance.count_tokens.call_count == 2  # Once for input, once for output

    @pytest.mark.asyncio
    async def test_gemini_agenerate_token_counting_failure_fallback(self, gemini_agent_factory, mock_generative_model, caplog):
        """Test that token counting failure falls back to estimation and logs warning"""
        model_instance, mock_response, _ = mock_generative_model
        mock_response.text = "This is a test response with multiple words"
        model_instance.count_tokens.side_effect = Exception("Token counting failed")

        agent = gemini_agent_factory(model_instance)

        # Test agenerate with token counting failure
        with caplog.at_level("WARNING"):
            response_text, response_time_ms, token_usage = await agent.agenerate("Test prompt with words")

        # Should use fallback estimation
        assert token_usage.input > 0
        assert token_usage.output > 0
        assert "Failed to count tokens" in caplog.text

    @pytest.mark.asyncio
    async def test_gemini_agenerate_executor_behavior(self, gemini_agent_factory, mock_generative_model):
        """Test that run_in_executor works correctly in async context"""
        model_instance, mock_response, mock_count_response = mock_generative_model
        mock_response.text = "Test response"
        mock_count_response.total_tokens = 50
        model_instance.count_tokens.return_value = mock_count_response

        agent = gemini_agent_factory(model_instance)

        # Test that executor runs safely in async context
        response_text, response_time_ms, token_usage = await agent.agenerate("Test")

        assert response_text == "Test response"
        assert token_usage.total > 0

    @pytest.mark.asyncio
    async def test_gemini_executor_in_active_loop(self, gemini_agent_factory, mock_generative_model):
        """Test that executor works correctly when already in an active event loop"""
        model_instance, mock_response, mock_count_response = mock_generative_model
        mock_response.text = "Test response"
        mock_count_response.total_tokens = 50
        model_instance.count_tokens.return_value = mock_count_response

        agent = gemini_agent_factory(model_instance)

        # Test executor behavior inside an active loop
        async def nested_async():
            return await agent.agenerate("Test prompt")

        response_text, response_time_ms, token_usage = await nested_async()

        assert response_text == "Test response"
        assert token_usage.total > 0

    @pytest.mark.asyncio
    async def test_gemini_token_counting_error_logs_warning(self, gemini_agent_factory, mock_generative_model, caplog):
        """Test that token counting errors log warnings and use fallback"""
        model_instance, mock_response, _ = mock_generative_model
        mock_response.text = "Test response with multiple words"
        model_instance.count_tokens.side_effect = Exception("API error")

        agent = gemini_agent_factory(model_instance)

        with caplog.at_level("WARNING"):
            response_text, response_time_ms, token_usage = await agent.agenerate("Test prompt")

        assert len(caplog.records) > 0
        assert any("Failed to count tokens" in record.message for record in caplog.records)
        assert token_usage.input > 0
        assert token_usage.output > 0

    @pytest.mark.asyncio
    async def test_gemini_token_counting_fallback_positive_values(self, gemini_agent_factory, mock_generative_model):
        """Test that fallback token counts are always positive"""
        model_instance, mock_response, _ = mock_generative_model
        mock_response.text = "x"  # Very short response
        mock_response.finish_reason = "STOP"
        model_instance.count_tokens.side_effect = Exception("Error")

        agent = gemini_agent_factory(model_instance)

        response_text, response_time_ms, token_usage = await agent.agenerate("x")

        assert token_usage.input >= 1
        assert token_usage.output >= 1
        assert token_usage.total >= 2

    @pytest.mark.asyncio
    async def test_gemini_api_call_error_propagates(self, gemini_agent_factory, mock_generative_model):
        """Test that API call errors are properly propagated"""
        model_instance, _, _ = mock_generative_model
        model_instance.generate_content.side_effect = Exception("API connection failed")

        agent = gemini_agent_factory(model_instance)

        with pytest.raises(RuntimeError, match="Gemini API call failed"):
            await agent.agenerate("Test prompt")

    @pytest.mark.asyncio
    async def test_gemini_empty_response_error(self, gemini_agent_factory, mock_generative_model):
        """Test that empty response raises RuntimeError"""
        model_instance, mock_response, _ = mock_generative_model
        mock_response.text = None  # Empty response
        mock_response.finish_reason = "SAFETY"
        model_instance.generate_content.return_value = mock_response

        agent = gemini_agent_factory(model_instance)

        with pytest.raises(RuntimeError, match="empty response"):
            await agent.agenerate("Test prompt")

    @pytest.mark.asyncio
    async def test_gemini_executor_thread_safety(self, gemini_agent_factory, mock_generative_model):
        """Test that executor handles concurrent calls safely"""
        model_instance, mock_response, mock_count_response = mock_generative_model
        mock_response.text = "Test response"
        mock_count_response.total_tokens = 50
        model_instance.count_tokens.return_value = mock_count_response

        agent = gemini_agent_factory(model_instance)

        tasks = [agent.agenerate(f"Test prompt {i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for response_text, response_time_ms, token_usage in results:
            assert response_text == "Test response"
            assert token_usage.total > 0
