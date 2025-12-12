"""
Shared types/utilities used across the Startd8 SDK.
"""

from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker state."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

