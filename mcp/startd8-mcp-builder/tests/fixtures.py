"""Shared pytest fixtures for Startd8 MCP server tests.

These fixtures provide isolated skill directories, mocked Anthropic API
responses, and controlled environment variables for reliable tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Iterable

import pytest


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def test_skills_directory(tmp_path: Path) -> Path:
    """Create temporary directory with several test skills.

    Layout:
        tmp_path/
          skill-test-1/
            SKILL.md         # with YAML frontmatter
          skill-test-2/
            SKILL.md         # with YAML frontmatter
          skill-test-3/
            SKILL.md         # without frontmatter (fallback to dir name)
          skill-test-4/
            SKILL.md         # malformed YAML frontmatter
          no-skill-file/     # directory without SKILL.md
    """

    # Skill with valid frontmatter
    _write_file(
        tmp_path / "skill-test-1" / "SKILL.md",
        """---
name: skill-test-1
description: First test skill
metadata:
  version: "1.0.0"
  author: Tester One
  tags: ["test", "sample"]
---
# Body for skill-test-1
""",
    )

    # Another skill with valid frontmatter
    _write_file(
        tmp_path / "skill-test-2" / "SKILL.md",
        """---
name: skill-test-2
description: Second test skill
metadata:
  version: "2.0.0"
  author: Tester Two
  tags: ["test2"]
---
# Body for skill-test-2
""",
    )

    # Skill without frontmatter (should fall back to directory name)
    _write_file(
        tmp_path / "skill-test-3" / "SKILL.md",
        """# Skill Test 3

This SKILL.md intentionally has no YAML frontmatter.
""",
    )

    # Skill with malformed YAML frontmatter
    _write_file(
        tmp_path / "skill-test-4" / "SKILL.md",
        """---
name: skill-test-4
metadata: {unclosed
---
# Malformed frontmatter should be handled gracefully
""",
    )

    # Directory without SKILL.md (should be ignored)
    (tmp_path / "no-skill-file").mkdir(parents=True, exist_ok=True)

    return tmp_path


@pytest.fixture
def test_env_vars(monkeypatch: pytest.MonkeyPatch) -> Iterable[Dict[str, Any]]:
    """Set up and tear down environment variables for tests.

    Yields a dict-like view of the environment so tests can inspect
    current values if needed.
    """

    original_env = os.environ.copy()

    # Provide sane defaults commonly used by tests; individual tests
    # can override as needed.
    monkeypatch.setenv("STARTD8_SKILL_PATH", "")

    try:
        yield os.environ
    finally:
        # Restore original environment to avoid cross-test pollution
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
def mock_anthropic_api(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Mock Anthropic API for unit tests.

    Provides a minimal stand-in for the anthropic.Anthropic client that
    records the last request and returns a deterministic response.

    Integration tests are expected to hit the real Anthropic API and
    should *not* use this fixture.
    """

    class _FakeUsage:
        def __init__(self, input_tokens: int = 10, output_tokens: int = 20) -> None:
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens

    class _FakeMessage:
        def __init__(self, text: str) -> None:
            self.content = [type("_Text", (), {"text": text})()]
            self.usage = _FakeUsage()

    class _FakeMessages:
        def __init__(self, store: Dict[str, Any]) -> None:
            self._store = store

        def create(self, **kwargs: Any) -> _FakeMessage:
            self._store["last_request"] = kwargs
            return _FakeMessage(text="fake-response")

    class _FakeAnthropic:
        def __init__(self, store: Dict[str, Any], api_key: str | None = None) -> None:
            self.api_key = api_key
            # Record requests in the fixture-level store so tests can assert on them.
            self.messages = _FakeMessages(store)

    store: Dict[str, Any] = {}

    def _fake_anthropic_constructor(*args: Any, **kwargs: Any) -> _FakeAnthropic:
        return _FakeAnthropic(store=store, api_key=kwargs.get("api_key"))

    # Create a fake anthropic module shape expected by startd8_mcp
    fake_module = type("_AnthropicModule", (), {"Anthropic": _fake_anthropic_constructor})()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(globals(), "anthropic", fake_module)

    # Also ensure that importing "anthropic" in the AUT imports our fake
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_module)

    store["module"] = fake_module
    return store
