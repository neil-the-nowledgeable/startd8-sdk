"""
Tests for ClaudeAgent and GPT4Agent retry integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from startd8.utils.retry import RetryConfig, RetryError


# =============================================================================
# GPT4Agent Retry Tests
# =============================================================================


class TestGPT4AgentRetryConfig:
    """Tests for GPT4Agent retry configuration"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    def test_default_retry_disabled(self):
        """By default, retry is disabled for backward compatibility"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent
            agent = GPT4Agent(name="test", model="gpt-4")
            assert agent.retry_config is None

    def test_enable_retry_flag(self):
        """enable_retry=True uses default retry config"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent
            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                enable_retry=True
            )
            assert agent.retry_config is not None
            assert agent.retry_config.max_attempts == 3
            assert 429 in agent.retry_config.retryable_status_codes

    def test_custom_retry_config(self):
        """Custom retry config overrides default"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent
            custom_config = RetryConfig(max_attempts=5, base_delay=2.0)
            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                retry_config=custom_config
            )
            assert agent.retry_config is custom_config
            assert agent.retry_config.max_attempts == 5

    def test_default_retry_config_class_attribute(self):
        """DEFAULT_RETRY_CONFIG is accessible as class attribute"""
        from startd8.agents import GPT4Agent
        default = GPT4Agent.DEFAULT_RETRY_CONFIG
        assert default.max_attempts == 3
        assert default.base_delay == 1.0


class TestGPT4AgentRetryBehavior:
    """Tests for GPT4Agent retry behavior during API calls"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    @pytest.fixture
    def mock_response(self):
        """Create a mock OpenAI response"""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        return response

    @pytest.mark.asyncio
    async def test_agenerate_without_retry(self, mock_response):
        """agenerate works normally without retry config"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent

            agent = GPT4Agent(name="test", model="gpt-4")

            agent.async_client = MagicMock()
            agent.async_client.chat.completions.create = AsyncMock(return_value=mock_response)

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            assert usage.input == 10
            assert usage.output == 20
            agent.async_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_agenerate_with_retry_success_first_attempt(self, mock_response):
        """With retry enabled, successful first attempt returns immediately"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent

            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                enable_retry=True
            )

            agent.async_client = MagicMock()
            agent.async_client.chat.completions.create = AsyncMock(return_value=mock_response)

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            agent.async_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_agenerate_retries_on_connection_error(self, mock_response):
        """Connection errors are retried when retry is enabled"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent

            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                retry_config=RetryConfig(max_attempts=3, base_delay=0.01)
            )

            call_count = 0

            async def flaky_api(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("Connection reset")
                return mock_response

            agent.async_client = MagicMock()
            agent.async_client.chat.completions.create = flaky_api

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_agenerate_exhausts_retries(self):
        """All retry attempts exhausted raises APIError"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent
            from startd8.exceptions import APIError

            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                retry_config=RetryConfig(max_attempts=2, base_delay=0.01)
            )

            call_count = 0

            async def always_fails(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise ConnectionError("Permanent failure")

            agent.async_client = MagicMock()
            agent.async_client.chat.completions.create = always_fails

            with pytest.raises(APIError) as exc_info:
                await agent.agenerate("Hello")

            assert call_count == 2
            assert "2 attempts" in str(exc_info.value)


# =============================================================================
# ClaudeAgent Retry Tests
# =============================================================================


class TestClaudeAgentRetryConfig:
    """Tests for ClaudeAgent retry configuration"""

    def test_default_retry_disabled(self):
        """By default, retry is disabled for backward compatibility"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            agent = ClaudeAgent(name="test", model="claude-3-opus-20240229")
            assert agent.retry_config is None

    def test_enable_retry_flag(self):
        """enable_retry=True uses default retry config"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                enable_retry=True
            )
            assert agent.retry_config is not None
            assert agent.retry_config.max_attempts == 3
            assert 429 in agent.retry_config.retryable_status_codes
            assert 529 in agent.retry_config.retryable_status_codes  # Anthropic overloaded

    def test_custom_retry_config(self):
        """Custom retry config overrides default"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            custom_config = RetryConfig(max_attempts=5, base_delay=2.0)
            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                retry_config=custom_config
            )
            assert agent.retry_config is custom_config
            assert agent.retry_config.max_attempts == 5
            assert agent.retry_config.base_delay == 2.0

    def test_retry_config_takes_precedence_over_enable_retry(self):
        """retry_config parameter takes precedence over enable_retry flag"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            custom_config = RetryConfig(max_attempts=10)
            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                retry_config=custom_config,
                enable_retry=True  # Should be ignored
            )
            assert agent.retry_config.max_attempts == 10

    def test_default_retry_config_class_attribute(self):
        """DEFAULT_RETRY_CONFIG is accessible as class attribute"""
        from startd8.agents import ClaudeAgent
        default = ClaudeAgent.DEFAULT_RETRY_CONFIG
        assert default.max_attempts == 3
        assert default.base_delay == 1.0
        assert default.max_delay == 60.0


class TestClaudeAgentRetryBehavior:
    """Tests for ClaudeAgent retry behavior during API calls"""

    @pytest.fixture
    def mock_response(self):
        """Create a mock Anthropic response"""
        response = MagicMock()
        response.content = [MagicMock(text="Test response")]
        response.usage = MagicMock(input_tokens=10, output_tokens=20)
        return response

    @pytest.mark.asyncio
    async def test_agenerate_without_retry(self, mock_response):
        """agenerate works normally without retry config"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent

            agent = ClaudeAgent(name="test", model="claude-3-opus-20240229")

            # Mock the async client
            agent.async_client = MagicMock()
            agent.async_client.messages.create = AsyncMock(return_value=mock_response)

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            assert usage.input == 10
            assert usage.output == 20
            agent.async_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_agenerate_with_retry_success_first_attempt(self, mock_response):
        """With retry enabled, successful first attempt returns immediately"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent

            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                enable_retry=True
            )

            agent.async_client = MagicMock()
            agent.async_client.messages.create = AsyncMock(return_value=mock_response)

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            agent.async_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_agenerate_retries_on_connection_error(self, mock_response):
        """Connection errors are retried when retry is enabled"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent

            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                retry_config=RetryConfig(max_attempts=3, base_delay=0.01)
            )

            call_count = 0

            async def flaky_api(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("Connection reset")
                return mock_response

            agent.async_client = MagicMock()
            agent.async_client.messages.create = flaky_api

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_agenerate_exhausts_retries(self):
        """All retry attempts exhausted raises APIError"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            from startd8.exceptions import APIError

            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                retry_config=RetryConfig(max_attempts=2, base_delay=0.01)
            )

            call_count = 0

            async def always_fails(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise ConnectionError("Permanent failure")

            agent.async_client = MagicMock()
            agent.async_client.messages.create = always_fails

            with pytest.raises(APIError) as exc_info:
                await agent.agenerate("Hello")

            assert call_count == 2
            assert "2 attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_agenerate_no_retry_without_config(self):
        """Without retry config, errors are not retried"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent
            from startd8.exceptions import APIError

            agent = ClaudeAgent(
                name="test",
                model="claude-3-opus-20240229",
                # No retry config
            )

            call_count = 0

            async def fails_once(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise ConnectionError("Connection error")

            agent.async_client = MagicMock()
            agent.async_client.messages.create = fails_once

            with pytest.raises((APIError, ConnectionError)):
                await agent.agenerate("Hello")

            # Should only be called once - no retry
            assert call_count == 1


class TestClaudeAgentMakeApiCall:
    """Tests for the _make_api_call helper method"""

    @pytest.mark.asyncio
    async def test_make_api_call_calls_client(self):
        """_make_api_call correctly calls the async client"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            from startd8.agents import ClaudeAgent

            mock_response = MagicMock()
            agent = ClaudeAgent(name="test", model="claude-3-opus-20240229")

            agent.async_client = MagicMock()
            agent.async_client.messages.create = AsyncMock(return_value=mock_response)

            result = await agent._make_api_call("Test prompt")

            assert result is mock_response
            agent.async_client.messages.create.assert_called_once_with(
                model="claude-3-opus-20240229",
                max_tokens=4096,
                messages=[{"role": "user", "content": "Test prompt"}]
            )


# =============================================================================
# GeminiAgent Retry Tests
# =============================================================================


class TestGeminiAgentRetryConfig:
    """Tests for GeminiAgent retry configuration"""

    @pytest.fixture(autouse=True)
    def mock_gemini(self):
        """Mock Gemini availability for all tests in this class"""
        with patch('startd8.agents._GEMINI_AVAILABLE', True), \
             patch('startd8.agents.genai') as mock_genai, \
             patch('startd8.agents.genai_types', MagicMock()):
            mock_genai.Client = MagicMock()
            yield mock_genai

    def test_default_retry_disabled(self):
        """By default, retry is disabled for backward compatibility"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent
            agent = GeminiAgent(name="test", model="gemini-1.5-flash")
            assert agent.retry_config is None

    def test_enable_retry_flag(self):
        """enable_retry=True uses default retry config"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent
            agent = GeminiAgent(
                name="test",
                model="gemini-1.5-flash",
                enable_retry=True
            )
            assert agent.retry_config is not None
            assert agent.retry_config.max_attempts == 3
            assert 429 in agent.retry_config.retryable_status_codes

    def test_custom_retry_config(self):
        """Custom retry config overrides default"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent
            custom_config = RetryConfig(max_attempts=5, base_delay=2.0)
            agent = GeminiAgent(
                name="test",
                model="gemini-1.5-flash",
                retry_config=custom_config
            )
            assert agent.retry_config is custom_config
            assert agent.retry_config.max_attempts == 5

    def test_default_retry_config_class_attribute(self):
        """DEFAULT_RETRY_CONFIG is accessible as class attribute"""
        from startd8.agents import GeminiAgent
        default = GeminiAgent.DEFAULT_RETRY_CONFIG
        assert default.max_attempts == 3
        assert default.base_delay == 1.0


class TestGeminiAgentRetryBehavior:
    """Tests for GeminiAgent retry behavior during API calls"""

    @pytest.fixture(autouse=True)
    def mock_gemini(self):
        """Mock Gemini availability for all tests in this class"""
        with patch('startd8.agents._GEMINI_AVAILABLE', True), \
             patch('startd8.agents.genai') as mock_genai, \
             patch('startd8.agents.genai_types') as mock_types:
            mock_genai.Client = MagicMock()
            mock_types.GenerateContentConfig = MagicMock()
            yield mock_genai

    @pytest.fixture
    def mock_response(self):
        """Create a mock Gemini response"""
        response = MagicMock()
        response.text = "Test response"
        response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=20,
            total_token_count=30
        )
        return response

    @pytest.mark.asyncio
    async def test_agenerate_retries_on_connection_error(self, mock_response):
        """Connection errors are retried when retry is enabled"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent

            agent = GeminiAgent(
                name="test",
                model="gemini-1.5-flash",
                retry_config=RetryConfig(max_attempts=3, base_delay=0.01)
            )

            call_count = 0

            async def flaky_api(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("Connection reset")
                return mock_response

            agent._make_api_call = flaky_api

            text, time_ms, usage = await agent.agenerate("Hello")

            assert text == "Test response"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_agenerate_exhausts_retries(self):
        """All retry attempts exhausted raises APIError"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent
            from startd8.exceptions import APIError

            agent = GeminiAgent(
                name="test",
                model="gemini-1.5-flash",
                retry_config=RetryConfig(max_attempts=2, base_delay=0.01)
            )

            call_count = 0

            async def always_fails(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise ConnectionError("Permanent failure")

            agent._make_api_call = always_fails

            with pytest.raises(APIError) as exc_info:
                await agent.agenerate("Hello")

            assert call_count == 2
            assert "2 attempts" in str(exc_info.value)


# =============================================================================
# OpenAICompatibleAgent Retry Tests
# =============================================================================


class TestOpenAICompatibleAgentRetryConfig:
    """Tests for OpenAICompatibleAgent retry configuration"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    def test_default_retry_disabled(self):
        """By default, retry is disabled for backward compatibility"""
        from startd8.agents import OpenAICompatibleAgent
        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1"
        )
        assert agent.retry_config is None

    def test_enable_retry_flag(self):
        """enable_retry=True uses default retry config"""
        from startd8.agents import OpenAICompatibleAgent
        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            enable_retry=True
        )
        assert agent.retry_config is not None
        assert agent.retry_config.max_attempts == 3
        assert 429 in agent.retry_config.retryable_status_codes

    def test_custom_retry_config(self):
        """Custom retry config overrides default"""
        from startd8.agents import OpenAICompatibleAgent
        custom_config = RetryConfig(max_attempts=5, base_delay=2.0)
        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            retry_config=custom_config
        )
        assert agent.retry_config is custom_config
        assert agent.retry_config.max_attempts == 5

    def test_default_retry_config_class_attribute(self):
        """DEFAULT_RETRY_CONFIG is accessible as class attribute"""
        from startd8.agents import OpenAICompatibleAgent
        default = OpenAICompatibleAgent.DEFAULT_RETRY_CONFIG
        assert default.max_attempts == 3
        assert default.base_delay == 1.0


class TestOpenAICompatibleAgentRetryBehavior:
    """Tests for OpenAICompatibleAgent retry behavior during API calls"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    @pytest.fixture
    def mock_response(self):
        """Create a mock OpenAI response"""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        return response

    @pytest.mark.asyncio
    async def test_agenerate_retries_on_connection_error(self, mock_response):
        """Connection errors are retried when retry is enabled"""
        from startd8.agents import OpenAICompatibleAgent

        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            retry_config=RetryConfig(max_attempts=3, base_delay=0.01)
        )

        call_count = 0

        async def flaky_api(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection reset")
            return mock_response

        agent._make_api_call = flaky_api

        text, time_ms, usage = await agent.agenerate("Hello")

        assert text == "Test response"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_agenerate_exhausts_retries(self):
        """All retry attempts exhausted raises APIError"""
        from startd8.agents import OpenAICompatibleAgent
        from startd8.exceptions import APIError

        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            retry_config=RetryConfig(max_attempts=2, base_delay=0.01)
        )

        call_count = 0

        async def always_fails(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Permanent failure")

        agent._make_api_call = always_fails

        with pytest.raises(APIError) as exc_info:
            await agent.agenerate("Hello")

        assert call_count == 2
        assert "2 attempts" in str(exc_info.value)
