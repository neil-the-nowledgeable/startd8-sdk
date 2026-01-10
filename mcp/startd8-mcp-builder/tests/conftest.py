"""Pytest configuration for Startd8 MCP server tests.

Imports shared fixtures from fixtures.py and configures pytest-asyncio.
"""

import pytest

# Import all fixtures from fixtures.py to make them available to all tests
# Use relative import for reliable fixture discovery regardless of how pytest is invoked
from .fixtures import (
    test_skills_directory,
    test_env_vars,
    mock_anthropic_api,
)

# Re-export fixtures for pytest discovery
__all__ = [
    "test_skills_directory",
    "test_env_vars", 
    "mock_anthropic_api",
]
