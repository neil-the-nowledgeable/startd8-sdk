"""
Shared context variables for cross-cutting concerns.

This module centralizes ContextVars used across logging, events, and other
subsystems so they share the same context state.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# Correlation ID for tracing related logs/events/cost records across async calls.
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)

