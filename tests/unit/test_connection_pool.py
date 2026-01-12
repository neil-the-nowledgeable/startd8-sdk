"""
Tests for connection pooling functionality.
"""

import pytest
import threading
from unittest.mock import MagicMock, patch


class TestClientPool:
    """Tests for ClientPool class"""

    def test_pool_singleton_pattern(self):
        """get_client_pool returns the same instance"""
        from startd8.agents import get_client_pool

        pool1 = get_client_pool()
        pool2 = get_client_pool()
        assert pool1 is pool2

    def test_pool_initialization(self):
        """ClientPool initializes with empty client dictionaries"""
        from startd8.agents import ClientPool

        pool = ClientPool()
        stats = pool.stats()
        assert stats["sync_clients"] == 0
        assert stats["async_clients"] == 0

    def test_pool_thread_safety(self):
        """ClientPool is thread-safe"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout_config = TimeoutConfig()
        results = []
        errors = []

        def worker(i):
            try:
                with patch('startd8.agents.pool._OPENAI_AVAILABLE', True), \
                     patch('startd8.agents.pool.OpenAI', MagicMock()), \
                     patch('startd8.agents.pool.AsyncOpenAI', MagicMock()):
                    pool.get_openai_clients(
                        api_key=f"test-key-{i % 3}",  # Use 3 different keys
                        timeout_config=timeout_config
                    )
                results.append(i)
            except Exception as e:
                errors.append((i, e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10

    def test_pool_cleanup(self):
        """ClientPool cleanup clears all clients"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()

        with patch('startd8.agents.pool._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.pool.OpenAI', MagicMock()), \
             patch('startd8.agents.pool.AsyncOpenAI', MagicMock()):
            pool.get_openai_clients(
                api_key="test-key",
                timeout_config=TimeoutConfig()
            )

            assert pool.stats()["sync_clients"] > 0

            pool.cleanup()
            assert pool.stats()["sync_clients"] == 0
            assert pool.stats()["async_clients"] == 0


class TestClientPoolAnthropicClients:
    """Tests for Anthropic client pooling"""

    def test_get_anthropic_clients_creates_clients(self):
        """get_anthropic_clients creates both sync and async clients"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()

        with patch('startd8.agents.pool.Anthropic') as mock_sync, \
             patch('startd8.agents.pool.AsyncAnthropic') as mock_async:
            sync, async_client = pool.get_anthropic_clients(
                api_key="test-key",
                timeout_config=TimeoutConfig()
            )

            mock_sync.assert_called_once()
            mock_async.assert_called_once()
            assert pool.stats()["sync_clients"] == 1
            assert pool.stats()["async_clients"] == 1

    def test_get_anthropic_clients_reuses_clients(self):
        """get_anthropic_clients returns cached clients for same config"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout_config = TimeoutConfig()

        with patch('startd8.agents.pool.Anthropic') as mock_sync, \
             patch('startd8.agents.pool.AsyncAnthropic') as mock_async:
            sync1, async1 = pool.get_anthropic_clients(
                api_key="test-key",
                timeout_config=timeout_config
            )
            sync2, async2 = pool.get_anthropic_clients(
                api_key="test-key",
                timeout_config=timeout_config
            )

            # Should only be created once
            assert mock_sync.call_count == 1
            assert mock_async.call_count == 1
            assert sync1 is sync2
            assert async1 is async2

    def test_get_anthropic_clients_different_keys(self):
        """get_anthropic_clients creates separate clients for different API keys"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout_config = TimeoutConfig()

        with patch('startd8.agents.pool.Anthropic') as mock_sync, \
             patch('startd8.agents.pool.AsyncAnthropic') as mock_async:
            pool.get_anthropic_clients(api_key="key1", timeout_config=timeout_config)
            pool.get_anthropic_clients(api_key="key2", timeout_config=timeout_config)

            # Should be created twice (different keys)
            assert mock_sync.call_count == 2
            assert pool.stats()["sync_clients"] == 2

    def test_get_anthropic_clients_different_timeouts(self):
        """get_anthropic_clients creates separate clients for different timeouts"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout1 = TimeoutConfig(read=30.0)
        timeout2 = TimeoutConfig(read=60.0)

        with patch('startd8.agents.pool.Anthropic') as mock_sync, \
             patch('startd8.agents.pool.AsyncAnthropic') as mock_async:
            pool.get_anthropic_clients(api_key="key", timeout_config=timeout1)
            pool.get_anthropic_clients(api_key="key", timeout_config=timeout2)

            # Should be created twice (different timeouts)
            assert mock_sync.call_count == 2
            assert pool.stats()["sync_clients"] == 2


class TestClientPoolOpenAIClients:
    """Tests for OpenAI client pooling"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability"""
        with patch('startd8.agents.pool._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.pool.OpenAI', MagicMock()), \
             patch('startd8.agents.pool.AsyncOpenAI', MagicMock()):
            yield

    def test_get_openai_clients_creates_clients(self):
        """get_openai_clients creates both sync and async clients"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()

        with patch('startd8.agents.pool.OpenAI') as mock_sync, \
             patch('startd8.agents.pool.AsyncOpenAI') as mock_async:
            sync, async_client = pool.get_openai_clients(
                api_key="test-key",
                timeout_config=TimeoutConfig()
            )

            mock_sync.assert_called_once()
            mock_async.assert_called_once()

    def test_get_openai_clients_with_base_url(self):
        """get_openai_clients includes base_url in cache key"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout_config = TimeoutConfig()

        with patch('startd8.agents.pool.OpenAI') as mock_sync, \
             patch('startd8.agents.pool.AsyncOpenAI') as mock_async:
            pool.get_openai_clients(
                api_key="key",
                timeout_config=timeout_config,
                base_url="http://localhost:11434/v1"
            )
            pool.get_openai_clients(
                api_key="key",
                timeout_config=timeout_config,
                base_url="http://localhost:8080/v1"
            )

            # Different base_urls should create separate clients
            assert mock_sync.call_count == 2


class TestClientPoolGeminiClients:
    """Tests for Gemini client pooling"""

    @pytest.fixture(autouse=True)
    def mock_gemini(self):
        """Mock Gemini availability"""
        with patch('startd8.agents.pool._GEMINI_AVAILABLE', True), \
             patch('startd8.agents.pool.genai') as mock_genai:
            mock_genai.Client = MagicMock()
            yield mock_genai

    def test_get_gemini_client_creates_client(self):
        """get_gemini_client creates a genai.Client"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()

        with patch('startd8.agents.pool.genai') as mock_genai, \
             patch('httpx.Client', MagicMock()):
            mock_genai.Client = MagicMock()
            client = pool.get_gemini_client(
                api_key="test-key",
                timeout_config=TimeoutConfig()
            )

            mock_genai.Client.assert_called_once()

    def test_get_gemini_client_reuses_client(self):
        """get_gemini_client returns cached client for same config"""
        from startd8.agents import ClientPool, TimeoutConfig

        pool = ClientPool()
        timeout_config = TimeoutConfig()

        with patch('startd8.agents.pool.genai') as mock_genai, \
             patch('httpx.Client', MagicMock()):
            mock_genai.Client = MagicMock()
            client1 = pool.get_gemini_client(
                api_key="test-key",
                timeout_config=timeout_config
            )
            client2 = pool.get_gemini_client(
                api_key="test-key",
                timeout_config=timeout_config
            )

            # Should only be created once
            assert mock_genai.Client.call_count == 1
            assert client1 is client2


class TestClaudeAgentConnectionPool:
    """Tests for ClaudeAgent connection pooling"""

    def test_uses_pool_when_enabled(self):
        """ClaudeAgent uses connection pool when use_connection_pool=True"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.agents.claude.Anthropic') as mock_sync, \
                 patch('startd8.agents.claude.AsyncAnthropic') as mock_async, \
                 patch('startd8.agents.claude.get_client_pool') as mock_get_pool:
                from startd8.agents import ClaudeAgent

                mock_pool = MagicMock()
                mock_pool.get_anthropic_clients.return_value = (MagicMock(), MagicMock())
                mock_get_pool.return_value = mock_pool

                agent = ClaudeAgent(name="test", use_connection_pool=True)

                mock_get_pool.assert_called_once()
                mock_pool.get_anthropic_clients.assert_called_once()
                assert agent._use_connection_pool is True
                assert agent._owns_clients is False

    def test_creates_own_clients_when_disabled(self):
        """ClaudeAgent creates own clients when use_connection_pool=False"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('startd8.agents.claude.Anthropic') as mock_sync, \
                 patch('startd8.agents.claude.AsyncAnthropic') as mock_async:
                from startd8.agents import ClaudeAgent

                agent = ClaudeAgent(name="test", use_connection_pool=False)

                mock_sync.assert_called_once()
                mock_async.assert_called_once()
                assert agent._use_connection_pool is False
                assert agent._owns_clients is True


class TestGPT4AgentConnectionPool:
    """Tests for GPT4Agent connection pooling"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability"""
        with patch('startd8.agents.openai._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.openai.OpenAI', MagicMock()), \
             patch('startd8.agents.openai.AsyncOpenAI', MagicMock()):
            yield

    def test_uses_pool_when_enabled(self):
        """GPT4Agent uses connection pool when use_connection_pool=True"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('startd8.agents.openai.get_client_pool') as mock_get_pool:
                from startd8.agents import GPT4Agent

                mock_pool = MagicMock()
                mock_pool.get_openai_clients.return_value = (MagicMock(), MagicMock())
                mock_get_pool.return_value = mock_pool

                agent = GPT4Agent(name="test", use_connection_pool=True)

                mock_get_pool.assert_called_once()
                mock_pool.get_openai_clients.assert_called_once()
                assert agent._use_connection_pool is True
                assert agent._owns_clients is False

    def test_creates_own_clients_when_disabled(self):
        """GPT4Agent creates own clients when use_connection_pool=False"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('startd8.agents.openai.OpenAI') as mock_sync, \
                 patch('startd8.agents.openai.AsyncOpenAI') as mock_async:
                from startd8.agents import GPT4Agent

                agent = GPT4Agent(name="test", use_connection_pool=False)

                mock_sync.assert_called_once()
                mock_async.assert_called_once()
                assert agent._use_connection_pool is False
                assert agent._owns_clients is True


class TestGeminiAgentConnectionPool:
    """Tests for GeminiAgent connection pooling"""

    @pytest.fixture(autouse=True)
    def mock_gemini(self):
        """Mock Gemini availability"""
        with patch('startd8.agents.gemini._GEMINI_AVAILABLE', True), \
             patch('startd8.agents.gemini.genai') as mock_genai, \
             patch('startd8.agents.gemini.genai_types', MagicMock()), \
             patch('httpx.Client', MagicMock()):
            mock_genai.Client = MagicMock()
            yield mock_genai

    def test_uses_pool_when_enabled(self):
        """GeminiAgent uses connection pool when use_connection_pool=True"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            with patch('startd8.agents.gemini.get_client_pool') as mock_get_pool:
                from startd8.agents import GeminiAgent

                mock_pool = MagicMock()
                mock_pool.get_gemini_client.return_value = MagicMock()
                mock_get_pool.return_value = mock_pool

                agent = GeminiAgent(name="test", use_connection_pool=True)

                mock_get_pool.assert_called_once()
                mock_pool.get_gemini_client.assert_called_once()
                assert agent._use_connection_pool is True
                assert agent._owns_clients is False

    def test_creates_own_clients_when_disabled(self):
        """GeminiAgent creates own client when use_connection_pool=False"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            with patch('startd8.agents.gemini.genai') as mock_genai, \
                 patch('httpx.Client', MagicMock()):
                mock_genai.Client = MagicMock()
                from startd8.agents import GeminiAgent

                agent = GeminiAgent(name="test", use_connection_pool=False)

                mock_genai.Client.assert_called_once()
                assert agent._use_connection_pool is False
                assert agent._owns_clients is True


class TestOpenAICompatibleAgentConnectionPool:
    """Tests for OpenAICompatibleAgent connection pooling"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability"""
        with patch('startd8.agents.openai._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.openai.OpenAI', MagicMock()), \
             patch('startd8.agents.openai.AsyncOpenAI', MagicMock()):
            yield

    def test_uses_pool_when_enabled(self):
        """OpenAICompatibleAgent uses connection pool when use_connection_pool=True"""
        with patch('startd8.agents.openai.get_client_pool') as mock_get_pool:
            from startd8.agents import OpenAICompatibleAgent

            mock_pool = MagicMock()
            mock_pool.get_openai_clients.return_value = (MagicMock(), MagicMock())
            mock_get_pool.return_value = mock_pool

            agent = OpenAICompatibleAgent(
                name="test",
                base_url="http://localhost:11434/v1",
                use_connection_pool=True
            )

            mock_get_pool.assert_called_once()
            mock_pool.get_openai_clients.assert_called_once()
            assert agent._use_connection_pool is True
            assert agent._owns_clients is False

    def test_creates_own_clients_when_disabled(self):
        """OpenAICompatibleAgent creates own clients when use_connection_pool=False"""
        with patch('startd8.agents.openai.OpenAI') as mock_sync, \
             patch('startd8.agents.openai.AsyncOpenAI') as mock_async:
            from startd8.agents import OpenAICompatibleAgent

            agent = OpenAICompatibleAgent(
                name="test",
                base_url="http://localhost:11434/v1",
                use_connection_pool=False
            )

            mock_sync.assert_called_once()
            mock_async.assert_called_once()
            assert agent._use_connection_pool is False
            assert agent._owns_clients is True

    def test_passes_base_url_to_pool(self):
        """OpenAICompatibleAgent passes base_url to pool"""
        with patch('startd8.agents.openai.get_client_pool') as mock_get_pool:
            from startd8.agents import OpenAICompatibleAgent

            mock_pool = MagicMock()
            mock_pool.get_openai_clients.return_value = (MagicMock(), MagicMock())
            mock_get_pool.return_value = mock_pool

            agent = OpenAICompatibleAgent(
                name="test",
                base_url="http://localhost:11434/v1",
                use_connection_pool=True
            )

            # Verify base_url was passed to the pool
            call_kwargs = mock_pool.get_openai_clients.call_args[1]
            assert call_kwargs["base_url"] == "http://localhost:11434/v1"


class TestConnectionPoolWithRetryAndTimeout:
    """Tests for using connection pool with retry and timeout together"""

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI availability"""
        with patch('startd8.agents.openai._OPENAI_AVAILABLE', True), \
             patch('startd8.agents.openai.OpenAI', MagicMock()), \
             patch('startd8.agents.openai.AsyncOpenAI', MagicMock()):
            yield

    def test_pool_with_custom_timeout_and_retry(self):
        """Connection pool works with custom timeout and retry config"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('startd8.agents.openai.get_client_pool') as mock_get_pool:
                from startd8.agents import GPT4Agent, TimeoutConfig
                from startd8.utils.retry import RetryConfig

                mock_pool = MagicMock()
                mock_pool.get_openai_clients.return_value = (MagicMock(), MagicMock())
                mock_get_pool.return_value = mock_pool

                custom_timeout = TimeoutConfig(connect=5.0, read=30.0)
                custom_retry = RetryConfig(max_attempts=5)

                agent = GPT4Agent(
                    name="test",
                    timeout_config=custom_timeout,
                    retry_config=custom_retry,
                    use_connection_pool=True
                )

                assert agent.timeout_config is custom_timeout
                assert agent.retry_config is custom_retry
                assert agent._use_connection_pool is True

                # Verify timeout was passed to pool
                call_kwargs = mock_pool.get_openai_clients.call_args[1]
                assert call_kwargs["timeout_config"] is custom_timeout
