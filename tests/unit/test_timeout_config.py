"""
Tests for TimeoutConfig and agent timeout integration.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestTimeoutConfig:
    """Tests for TimeoutConfig dataclass"""

    def test_default_config(self):
        """Default timeout values are reasonable"""
        from startd8.agents import TimeoutConfig

        config = TimeoutConfig()
        assert config.connect == 10.0
        assert config.read == 120.0
        assert config.write == 30.0
        assert config.pool == 10.0

    def test_custom_config(self):
        """Custom timeout values are accepted"""
        from startd8.agents import TimeoutConfig

        config = TimeoutConfig(
            connect=5.0,
            read=60.0,
            write=15.0,
            pool=5.0
        )
        assert config.connect == 5.0
        assert config.read == 60.0
        assert config.write == 15.0
        assert config.pool == 5.0

    def test_negative_connect_raises(self):
        """Negative connect timeout raises ValueError"""
        from startd8.agents import TimeoutConfig

        with pytest.raises(ValueError, match="connect timeout must be non-negative"):
            TimeoutConfig(connect=-1.0)

    def test_negative_read_raises(self):
        """Negative read timeout raises ValueError"""
        from startd8.agents import TimeoutConfig

        with pytest.raises(ValueError, match="read timeout must be non-negative"):
            TimeoutConfig(read=-1.0)

    def test_negative_write_raises(self):
        """Negative write timeout raises ValueError"""
        from startd8.agents import TimeoutConfig

        with pytest.raises(ValueError, match="write timeout must be non-negative"):
            TimeoutConfig(write=-1.0)

    def test_negative_pool_raises(self):
        """Negative pool timeout raises ValueError"""
        from startd8.agents import TimeoutConfig

        with pytest.raises(ValueError, match="pool timeout must be non-negative"):
            TimeoutConfig(pool=-1.0)

    def test_zero_values_allowed(self):
        """Zero timeout values are allowed"""
        from startd8.agents import TimeoutConfig

        config = TimeoutConfig(connect=0.0, read=0.0, write=0.0, pool=0.0)
        assert config.connect == 0.0
        assert config.read == 0.0
        assert config.write == 0.0
        assert config.pool == 0.0

    def test_to_httpx_timeout(self):
        """to_httpx_timeout returns properly configured httpx.Timeout"""
        from startd8.agents import TimeoutConfig
        import httpx

        config = TimeoutConfig(connect=5.0, read=60.0, write=15.0, pool=5.0)
        timeout = config.to_httpx_timeout()

        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 5.0
        assert timeout.read == 60.0
        assert timeout.write == 15.0
        assert timeout.pool == 5.0


class TestClaudeAgentTimeout:
    """Tests for ClaudeAgent timeout configuration"""

    def test_default_timeout_config(self):
        """ClaudeAgent has DEFAULT_TIMEOUT_CONFIG class attribute"""
        from startd8.agents import ClaudeAgent, TimeoutConfig

        default = ClaudeAgent.DEFAULT_TIMEOUT_CONFIG
        assert isinstance(default, TimeoutConfig)
        assert default.connect == 10.0
        assert default.read == 120.0

    def test_uses_default_timeout_when_none(self):
        """When timeout_config is None, uses DEFAULT_TIMEOUT_CONFIG"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.agents.Anthropic') as mock_anthropic, \
                 patch('startd8.agents.AsyncAnthropic') as mock_async:
                from startd8.agents import ClaudeAgent

                agent = ClaudeAgent(name="test", model="claude-3-opus-20240229")

                assert agent.timeout_config is ClaudeAgent.DEFAULT_TIMEOUT_CONFIG
                # Verify timeout was passed to clients
                mock_anthropic.assert_called_once()
                call_kwargs = mock_anthropic.call_args[1]
                assert 'timeout' in call_kwargs

    def test_custom_timeout_config(self):
        """Custom timeout_config is used when provided"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.agents.Anthropic') as mock_anthropic, \
                 patch('startd8.agents.AsyncAnthropic') as mock_async:
                from startd8.agents import ClaudeAgent, TimeoutConfig

                custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
                agent = ClaudeAgent(
                    name="test",
                    model="claude-3-opus-20240229",
                    timeout_config=custom_timeout
                )

                assert agent.timeout_config is custom_timeout
                assert agent.timeout_config.connect == 5.0
                assert agent.timeout_config.read == 30.0


class TestGPT4AgentTimeout:
    """Tests for GPT4Agent timeout configuration"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    def test_default_timeout_config(self):
        """GPT4Agent has DEFAULT_TIMEOUT_CONFIG class attribute"""
        from startd8.agents import GPT4Agent, TimeoutConfig

        default = GPT4Agent.DEFAULT_TIMEOUT_CONFIG
        assert isinstance(default, TimeoutConfig)
        assert default.connect == 10.0
        assert default.read == 120.0

    def test_uses_default_timeout_when_none(self):
        """When timeout_config is None, uses DEFAULT_TIMEOUT_CONFIG"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent

            agent = GPT4Agent(name="test", model="gpt-4")

            assert agent.timeout_config is GPT4Agent.DEFAULT_TIMEOUT_CONFIG

    def test_custom_timeout_config(self):
        """Custom timeout_config is used when provided"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent, TimeoutConfig

            custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                timeout_config=custom_timeout
            )

            assert agent.timeout_config is custom_timeout
            assert agent.timeout_config.connect == 5.0
            assert agent.timeout_config.read == 30.0


class TestGeminiAgentTimeout:
    """Tests for GeminiAgent timeout configuration"""

    @pytest.fixture(autouse=True)
    def mock_gemini(self):
        """Mock Gemini availability for all tests in this class"""
        with patch('startd8.agents._GEMINI_AVAILABLE', True), \
             patch('startd8.agents.genai') as mock_genai, \
             patch('startd8.agents.genai_types', MagicMock()), \
             patch('httpx.Client', MagicMock()):
            mock_genai.Client = MagicMock()
            yield mock_genai

    def test_default_timeout_config(self):
        """GeminiAgent has DEFAULT_TIMEOUT_CONFIG class attribute"""
        from startd8.agents import GeminiAgent, TimeoutConfig

        default = GeminiAgent.DEFAULT_TIMEOUT_CONFIG
        assert isinstance(default, TimeoutConfig)
        assert default.connect == 10.0
        assert default.read == 120.0

    def test_uses_default_timeout_when_none(self):
        """When timeout_config is None, uses DEFAULT_TIMEOUT_CONFIG"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent

            agent = GeminiAgent(name="test", model="gemini-1.5-flash")

            assert agent.timeout_config is GeminiAgent.DEFAULT_TIMEOUT_CONFIG

    def test_custom_timeout_config(self):
        """Custom timeout_config is used when provided"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            from startd8.agents import GeminiAgent, TimeoutConfig

            custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
            agent = GeminiAgent(
                name="test",
                model="gemini-1.5-flash",
                timeout_config=custom_timeout
            )

            assert agent.timeout_config is custom_timeout
            assert agent.timeout_config.connect == 5.0
            assert agent.timeout_config.read == 30.0


class TestOpenAICompatibleAgentTimeout:
    """Tests for OpenAICompatibleAgent timeout configuration"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    def test_default_timeout_config(self):
        """OpenAICompatibleAgent has DEFAULT_TIMEOUT_CONFIG class attribute"""
        from startd8.agents import OpenAICompatibleAgent, TimeoutConfig

        default = OpenAICompatibleAgent.DEFAULT_TIMEOUT_CONFIG
        assert isinstance(default, TimeoutConfig)
        assert default.connect == 10.0
        assert default.read == 120.0

    def test_uses_default_timeout_when_none(self):
        """When timeout_config is None, uses DEFAULT_TIMEOUT_CONFIG"""
        from startd8.agents import OpenAICompatibleAgent

        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1"
        )

        assert agent.timeout_config is OpenAICompatibleAgent.DEFAULT_TIMEOUT_CONFIG

    def test_custom_timeout_config(self):
        """Custom timeout_config is used when provided"""
        from startd8.agents import OpenAICompatibleAgent, TimeoutConfig

        custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
        agent = OpenAICompatibleAgent(
            name="test",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            timeout_config=custom_timeout
        )

        assert agent.timeout_config is custom_timeout
        assert agent.timeout_config.connect == 5.0
        assert agent.timeout_config.read == 30.0


class TestTimeoutAndRetryTogether:
    """Tests for using timeout and retry together"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability for all tests in this class"""
        with patch('startd8.agents._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.OpenAI', MagicMock()), \
             patch('startd8.agents.AsyncOpenAI', MagicMock()):
            yield

    def test_timeout_and_retry_can_be_set_together(self):
        """Both timeout_config and retry_config can be set"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent, TimeoutConfig
            from startd8.utils.retry import RetryConfig

            custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
            custom_retry = RetryConfig(max_attempts=5, base_delay=2.0)

            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                timeout_config=custom_timeout,
                retry_config=custom_retry
            )

            assert agent.timeout_config is custom_timeout
            assert agent.retry_config is custom_retry
            assert agent.timeout_config.connect == 5.0
            assert agent.retry_config.max_attempts == 5

    def test_enable_retry_with_custom_timeout(self):
        """enable_retry=True works with custom timeout"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            from startd8.agents import GPT4Agent, TimeoutConfig

            custom_timeout = TimeoutConfig(connect=5.0, read=30.0)

            agent = GPT4Agent(
                name="test",
                model="gpt-4",
                timeout_config=custom_timeout,
                enable_retry=True
            )

            assert agent.timeout_config is custom_timeout
            assert agent.retry_config is GPT4Agent.DEFAULT_RETRY_CONFIG
