"""Generic MCP tool client + loop adapter (FR-11) — drive MCP server tools through the agentic loop.

The existing :mod:`startd8.mcp.gateway` is skill/workflow-oriented (``execute_skill``/``list_skills``)
and cannot drive *arbitrary* MCP tools. This module is the missing generic client: a small
``list_tools`` / ``call_tool`` abstraction (ported in shape from ml-intern's ``tools.py``) plus an
adapter that snapshots a server's tools into the loop's canonical :class:`ToolRegistry`.

Two design points carried from the convergent review:
- **Canonical, not parallel (R5-A5).** MCP-discovered tools become ordinary :class:`ToolSpec`s and
  enter through the *same* registry/dispatch seam as built-in tools — no second registration path.
- **Effect-class default-deny (FR-19 / FR-11-after-default-deny).** Each tool's effect class is
  derived from its ``readOnlyHint`` / ``destructiveHint`` annotation, so by default the registry
  (``allow_effect_classes={"read"}``) executes only read-only MCP tools; effectful ones are denied
  unless explicitly allow-listed/approved. This is *why* the MCP consumer is safe to expose.

The transport is pluggable. The core (protocol + mapping + adapter) has **no third-party
dependency** and is fully testable with a fake client. A concrete :class:`FastMCPToolClient` is
provided for real use; it lazily imports ``fastmcp`` so the SDK does not hard-depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from ..agents.agentic import AgenticSession, SessionConfig, ToolRegistry, ToolSpec
from ..agents.base import BaseAgent
from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class McpToolInfo:
    """A provider-neutral description of one MCP tool, from ``list_tools``."""

    name: str
    description: str
    input_schema: dict
    read_only: bool = True
    destructive: bool = False

    @property
    def effect_class(self) -> str:
        """Map MCP annotations → the loop's effect class (drives FR-19 default-deny)."""
        if self.destructive:
            return "destructive"
        return "read" if self.read_only else "write"


@runtime_checkable
class ToolClient(Protocol):
    """The minimal MCP client surface the loop needs. Any transport implementing this works."""

    async def list_tools(self) -> list[McpToolInfo]: ...

    async def call_tool(self, name: str, arguments: dict) -> str: ...


async def build_registry_from_mcp(
    client: ToolClient,
    *,
    allow_effect_classes: tuple[str, ...] = ("read",),
    result_max_bytes: int = 8192,
) -> ToolRegistry:
    """Snapshot *client*'s tools into a canonical :class:`ToolRegistry` (R4-F4: frozen per session).

    Each MCP tool becomes a :class:`ToolSpec` whose handler calls back through ``client.call_tool``;
    its ``effect_class`` is tagged from the server's annotations so the FR-19 policy applies. The
    listing is taken **once** here — a session works against this snapshot; a changed server requires
    an explicit rebuild (refresh), not silent drift.
    """
    infos = await client.list_tools()
    specs: list[ToolSpec] = []

    def _make_handler(tool_name: str):
        async def handler(arguments: dict) -> str:
            return await client.call_tool(tool_name, arguments)

        return handler

    for info in infos:
        specs.append(
            ToolSpec(
                name=info.name,
                description=info.description,
                parameters=info.input_schema or {"type": "object"},
                handler=_make_handler(info.name),
                effect_class=info.effect_class,
            )
        )
    logger.info(
        "MCP registry snapshot: %d tools (allow=%s)", len(specs), sorted(allow_effect_classes)
    )
    return ToolRegistry(specs, allow_effect_classes=allow_effect_classes, result_max_bytes=result_max_bytes)


async def new_mcp_agent_session(
    agent: BaseAgent,
    client: ToolClient,
    *,
    system_prompt: Optional[str] = None,
    config: Optional[SessionConfig] = None,
    allow_effect_classes: tuple[str, ...] = ("read",),
) -> AgenticSession:
    """Build an :class:`AgenticSession` over *agent* that can drive *client*'s MCP tools.

    Defaults to read-only (``allow_effect_classes={"read"}``). Pass a wider allow-list **only** with
    an explicit approval/allow-list decision (FR-19) — exposing the SDK's full MCP surface, which
    includes effectful tools, to an LLM loop without that gate is exactly what default-deny prevents.
    """
    registry = await build_registry_from_mcp(client, allow_effect_classes=allow_effect_classes)
    return AgenticSession(agent, registry, system_prompt=system_prompt, config=config)


class FastMCPToolClient:
    """Optional concrete :class:`ToolClient` backed by ``fastmcp.Client`` (lazy-imported).

    Connects to the SDK's own FastMCP server (or any MCP server spec ``fastmcp.Client`` accepts).
    Requires ``pip install fastmcp``; the import happens on connect, so importing this module never
    forces the dependency. Use as an async context manager::

        async with FastMCPToolClient(server) as client:
            session = await new_mcp_agent_session(agent, client)
    """

    def __init__(self, server: Any) -> None:
        self._server = server
        self._client: Any = None

    async def __aenter__(self) -> "FastMCPToolClient":
        try:
            from fastmcp import Client  # lazy: no hard dependency
        except ImportError as exc:  # pragma: no cover - exercised only when fastmcp is absent
            raise RuntimeError(
                "FastMCPToolClient requires the 'fastmcp' package (pip install fastmcp)"
            ) from exc
        self._client = Client(self._server)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)
            self._client = None

    async def list_tools(self) -> list[McpToolInfo]:
        raw = await self._client.list_tools()
        out: list[McpToolInfo] = []
        for t in raw:
            ann = getattr(t, "annotations", None)
            read_only = bool(_ann(ann, "readOnlyHint", True))
            destructive = bool(_ann(ann, "destructiveHint", False))
            out.append(
                McpToolInfo(
                    name=t.name,
                    description=getattr(t, "description", "") or "",
                    input_schema=getattr(t, "inputSchema", None) or {"type": "object"},
                    read_only=read_only,
                    destructive=destructive,
                )
            )
        return out

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._client.call_tool(name, arguments)
        # fastmcp returns a result whose content is a list of typed blocks; collect text.
        content = getattr(result, "content", result)
        if isinstance(content, list):
            return "\n".join(getattr(b, "text", str(b)) for b in content)
        return getattr(content, "text", str(content))


def _ann(annotations: Any, key: str, default: Any) -> Any:
    """Read an annotation value across dict- or attr-shaped annotation objects."""
    if annotations is None:
        return default
    if isinstance(annotations, dict):
        return annotations.get(key, default)
    return getattr(annotations, key, default)
