"""Regression for the survivorship-audit finding SA-STARTD8-MOCKAGENT-ERROR-NOOP.

Before the fix, ``MockAgent(error=...)`` fell into the ignored ``**kwargs``, so any test that
constructed a mock with an injected error to exercise a failure path silently ran the SUCCESS path
and passed green while asserting nothing about error handling. These tests pin the injection down:
``error=`` must actually raise on every generation call, and the default (no ``error=``) must be
completely unchanged.
"""
import asyncio

import pytest

from startd8.agents.mock import MockAgent


def test_error_instance_is_raised_by_agenerate():
    agent = MockAgent(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(agent.agenerate("hi"))


def test_error_class_is_instantiated_and_raised():
    agent = MockAgent(error=ValueError)  # a class, not an instance
    with pytest.raises(ValueError):
        asyncio.run(agent.agenerate("hi"))


def test_error_injection_also_applies_to_tool_use_path():
    agent = MockAgent(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(agent.agenerate_tools("hi", tools=[]))


def test_default_no_error_is_unchanged():
    # The load-bearing regression: no error= means the mock behaves exactly as before.
    agent = MockAgent()
    result = asyncio.run(agent.agenerate("hello world"))
    assert "Mock response" in result.text
