from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker states shared across skills and MCP gateway."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

