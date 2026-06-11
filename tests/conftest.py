"""
Pytest configuration and shared fixtures
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator

from startd8 import AgentFramework
from startd8.models import Prompt, AgentResponse, Benchmark, TokenUsage
from startd8.agents import MockAgent
from startd8.storage import FileSystemStorage


def pytest_configure(config):
    """Force the no-network ``local`` secrets backend for the unit suite.

    A developer may have persisted ``secrets_backend.backend = doppler`` in their real
    ``~/.startd8/config.json``. Without this guard, every ``AgentFramework()`` (and the
    CLI callback) would hydrate from their live Doppler during an ordinary ``pytest`` run
    — a surprise network call against a personal token. Mirrors the integration-test
    policy: live secrets backends are opt-in via STARTD8_RUN_INTEGRATION=1. Individual
    secrets tests still override this per-test via ``monkeypatch``.
    """
    if os.getenv("STARTD8_RUN_INTEGRATION") != "1":
        os.environ["STARTD8_SECRETS_BACKEND"] = "local"


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.integration tests unless STARTD8_RUN_INTEGRATION=1.

    Integration tests make **live** LLM API calls (e.g. real anthropic:claude-sonnet
    requests via implementation_engine.engine), which incur real charges. They are
    therefore opt-in: a normal ``pytest`` run (or CI) skips them so it can never
    accidentally bill the configured API key. Run them explicitly with:

        STARTD8_RUN_INTEGRATION=1 pytest -m integration ...
    """
    if os.getenv("STARTD8_RUN_INTEGRATION") == "1":
        return
    skip_integration = pytest.mark.skip(
        reason="live-API integration test — set STARTD8_RUN_INTEGRATION=1 to run "
        "(makes real, billable LLM calls)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def storage_dir(temp_dir: Path) -> Path:
    """Create a storage directory for tests"""
    storage_path = temp_dir / "storage"
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


@pytest.fixture
def framework(storage_dir: Path) -> AgentFramework:
    """Create an AgentFramework instance for testing"""
    return AgentFramework(storage_dir=storage_dir)


@pytest.fixture
def storage_backend(storage_dir: Path) -> FileSystemStorage:
    """Create a FileSystemStorage instance for testing"""
    return FileSystemStorage(storage_dir)


@pytest.fixture
def sample_prompt() -> Prompt:
    """Create a sample prompt for testing"""
    return Prompt(
        id="prompt-test123",
        content="Test prompt content",
        version="1.0.0",
        tags=["test", "sample"],
        metadata={"test": True}
    )


@pytest.fixture
def sample_token_usage() -> TokenUsage:
    """Create sample token usage for testing"""
    return TokenUsage(
        input=100,
        output=200,
        total=300
    )


@pytest.fixture
def sample_response(sample_prompt: Prompt, sample_token_usage: TokenUsage) -> AgentResponse:
    """Create a sample agent response for testing"""
    return AgentResponse(
        id="response-test123",
        prompt_id=sample_prompt.id,
        agent_name="mock",
        model="mock-model",
        response="Test response content",
        response_time_ms=150,
        token_usage=sample_token_usage,
        metadata={"test": True}
    )


@pytest.fixture
def mock_agent() -> MockAgent:
    """Create a mock agent for testing"""
    return MockAgent(name="test-mock", model="test-model")


@pytest.fixture
def sample_benchmark(sample_prompt: Prompt) -> Benchmark:
    """Create a sample benchmark for testing"""
    return Benchmark(
        id="benchmark-test123",
        name="Test Benchmark",
        prompt_id=sample_prompt.id,
        status="created",
        metadata={"test": True}
    )


class PromptFactory:
    """Factory for creating test prompts"""
    
    @staticmethod
    def create(
        content: str = "Test prompt",
        version: str = "1.0.0",
        tags: list = None,
        **kwargs
    ) -> Prompt:
        """Create a prompt with default or custom values"""
        import uuid
        return Prompt(
            id=kwargs.get("id", f"prompt-{uuid.uuid4().hex[:12]}"),
            content=content,
            version=version,
            tags=tags or [],
            metadata=kwargs.get("metadata", {})
        )


class ResponseFactory:
    """Factory for creating test responses"""
    
    @staticmethod
    def create(
        prompt_id: str,
        agent_name: str = "mock",
        response: str = "Test response",
        response_time_ms: int = 100,
        token_usage: TokenUsage = None,
        **kwargs
    ) -> AgentResponse:
        """Create a response with default or custom values"""
        import uuid
        if token_usage is None:
            token_usage = TokenUsage(input=50, output=50, total=100)
        
        return AgentResponse(
            id=kwargs.get("id", f"response-{uuid.uuid4().hex[:12]}"),
            prompt_id=prompt_id,
            agent_name=agent_name,
            model=kwargs.get("model", "mock-model"),
            response=response,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=kwargs.get("metadata", {})
        )


@pytest.fixture
def prompt_factory() -> PromptFactory:
    """Provide prompt factory"""
    return PromptFactory


@pytest.fixture
def response_factory() -> ResponseFactory:
    """Provide response factory"""
    return ResponseFactory









