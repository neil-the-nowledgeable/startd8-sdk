"""Startd8 MCP server implementation (internal package).

Public entrypoint remains `startd8_mcp.py` for backward compatibility.
"""

from .server import *  # noqa: F403

# Re-export the MCP instance and tool callables for convenience.
from .server import mcp  # noqa: F401
