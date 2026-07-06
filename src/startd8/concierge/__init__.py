"""Concierge — project-side SDK-onboarding assist surface.

The Concierge is the role that prepares a project for SDK onboarding (survey, readiness
assessment, kickoff instantiation, friction capture). Posture: **assist, not operate** — it
surveys and advises; it never runs the cascade, records a gate, or (over MCP) writes to disk.

This package holds the callable, MCP/CLI-agnostic logic (FR-C14 SDK half). The FastMCP wrapper
(`startd8_concierge` tool in `mcp/startd8-mcp-builder/startd8_mcp.py`) and the optional
`startd8 concierge` CLI both delegate here, so there is one code path.

Spike scope (read-only core): `survey` and `assess`. Write actions (`instantiate-kickoff`,
`log-friction`) and `derive-contract` are deferred per CONCIERGE_MCP_REQUIREMENTS.md v0.3.

Stable public API (FR-C11/C14):
    handle_concierge_tool(action, project_root) -> dict   # action dispatch, schema-versioned
    build_survey(project_root) -> dict
    build_assess(project_root) -> dict
"""

from .core import (
    SCHEMA_VERSION,
    ConciergeError,
    build_assess,
    build_survey,
    handle_concierge_read,
    handle_concierge_tool,
)
from .writes import load_experience_doc

__all__ = [
    "SCHEMA_VERSION",
    "ConciergeError",
    "build_assess",
    "build_survey",
    "handle_concierge_read",
    "handle_concierge_tool",
    "load_experience_doc",
]
