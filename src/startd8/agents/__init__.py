# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms. Government agencies, fossil fuel companies,
# military contractors, and organizations using forced ranking are subject to Maximum Fee.

"""
Startd8 agents module.

This module provides LLM agents for various providers:
- ClaudeAgent: Anthropic Claude
- GPT4Agent: OpenAI GPT-4
- GeminiAgent: Google Gemini
- OpenAICompatibleAgent: Any OpenAI-compatible API (Ollama, Together AI, Groq, etc.)
- MockAgent: Testing mock
- ComposerAgent: Cursor Composer (deprecated)

Also provides shared infrastructure:
- BaseAgent: Abstract base class for all agents
- TimeoutConfig: Configurable timeout settings
- ClientPool: Thread-safe connection pool for HTTP clients
"""

from .pool import TimeoutConfig, ClientPool, get_client_pool
from .base import BaseAgent, is_completion_model, AgentRegistry
from .claude import ClaudeAgent
from .openai import GPT4Agent, OpenAICompatibleAgent
from .gemini import GeminiAgent
from .mock import MockAgent, ComposerAgent

__all__ = [
    # Infrastructure
    "TimeoutConfig",
    "ClientPool",
    "get_client_pool",
    # Base
    "BaseAgent",
    "is_completion_model",
    "AgentRegistry",
    # Agents
    "ClaudeAgent",
    "GPT4Agent",
    "OpenAICompatibleAgent",
    "GeminiAgent",
    "MockAgent",
    "ComposerAgent",
]
