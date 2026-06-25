"""Agentic tool-use loop (Increment 1) — ``AgenticSession`` + ``ToolRegistry``.

The multi-turn runtime the SDK was missing: it drives a tool-use-capable agent
(:meth:`BaseAgent.agenerate_tools`, FR-0) to completion, dispatching the model's tool calls to
registered handlers and feeding results back until the model answers with no tool calls — or a
safety bound stops it.

**Status: EXPERIMENTAL (FR-21).** Public types here are pre-1.0 and may change.

Safety is first-class from the start (CRP triage, requirements v0.3):
- **FR-15** loop bounds — ``max_turns``, ``max_tool_calls_per_turn``, a repeated-identical-call
  breaker, and a fail-closed per-session token/cost budget checked **before** each model re-entry.
- **FR-9** execution contract — unknown tool names are rejected with a tool-error result (never
  executed); results are wrapped in a bounded envelope.
- **FR-19** effect-class default-deny — every tool is tagged ``read``/``write``/``destructive``;
  only allow-listed classes execute (Concierge uses ``{"read"}`` → its survey/assess only).
- **FR-16** ``ToolResultPolicy`` — redact obvious secrets + cap size before results re-enter context.
- **FR-17** typed error taxonomy.

Deliberately deferred (tracked in the plan, not built here): context-overflow detection +
compaction (FR-3/FR-4 — the typed :class:`ContextWindowExceededError` is defined but the
per-provider detector lands with compaction), streaming (FR-2), OTel spans (FR-18), and trajectory
persistence (FR-20). The provider message-shaping below is a minimal inline codec; the full
provider-neutral transcript/``MessageCodec`` layer (plan 0.4) supersedes it later.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..logging_config import get_logger
from ..models import AgenticTurn, ToolCallRequest
from .base import BaseAgent

logger = get_logger(__name__)


# --------------------------------------------------------------------------- errors (FR-17)
class AgenticError(Exception):
    """Base for agentic-loop errors."""


class UnsupportedToolUseError(AgenticError):
    """The agent does not implement the FR-0 tool-use primitive (``supports_tool_use()`` is False)."""


class AgenticLoopExceededError(AgenticError):
    """A loop safety bound was hit (turns / repeated calls). Carries the partial result."""


class BudgetExceededError(AgenticError):
    """The per-session token/cost ceiling was reached. Carries the partial result."""


class ContextWindowExceededError(AgenticError):
    """Normalized context-window-overflow (FR-3). Detector + compaction land with the compaction step."""


EFFECT_CLASSES = ("read", "write", "destructive")


# --------------------------------------------------------------------------- tools (FR-9 / FR-19)
@dataclass
class ToolSpec:
    """A canonical, provider-neutral tool definition (FR-9).

    ``handler`` takes the parsed arguments dict and returns a result (str or JSON-able); it may be
    sync or async. ``effect_class`` drives the FR-19 default-deny policy.
    """

    name: str
    description: str
    parameters: dict  # JSON Schema (object) for the arguments
    handler: Callable[[dict], Any]
    effect_class: str = "read"

    def __post_init__(self) -> None:
        if self.effect_class not in EFFECT_CLASSES:
            raise ValueError(f"effect_class must be one of {EFFECT_CLASSES}, got {self.effect_class!r}")


@dataclass
class ToolResult:
    """Bounded result envelope (FR-9) returned to the model."""

    tool_call_id: str
    name: str
    ok: bool
    content: str
    truncated: bool = False


# FR-16: ToolResultPolicy — redact obvious secrets + cap size before results re-enter model context.
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})"
)


def apply_result_policy(text: str, *, max_bytes: int = 8192) -> tuple[str, bool]:
    """Redact known secret patterns and cap byte size. Returns ``(clean_text, was_truncated)``."""
    redacted = _SECRET_RE.sub("[REDACTED]", text)
    raw = redacted.encode("utf-8")
    if len(raw) > max_bytes:
        return raw[:max_bytes].decode("utf-8", errors="ignore") + "\n…[truncated]", True
    return redacted, False


class ToolRegistry:
    """Holds tools, renders them to provider format, and dispatches calls under the effect policy.

    ``allow_effect_classes`` is the FR-19 allow-list — defaults to read-only. The Concierge surface
    constructs the registry with exactly its two read tools and the default ``{"read"}`` policy.
    """

    def __init__(
        self,
        tools: Optional[list[ToolSpec]] = None,
        *,
        allow_effect_classes: tuple[str, ...] = ("read",),
        result_max_bytes: int = 8192,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.allow_effect_classes = set(allow_effect_classes)
        self.result_max_bytes = result_max_bytes
        for t in tools or []:
            self.register(t)

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> set[str]:
        return set(self._tools)

    # --- provider rendering (minimal inline codec; plan 0.2/0.4 generalize this) ---
    def for_format(self, fmt: str) -> list[dict]:
        if fmt == "anthropic":
            return [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in self._tools.values()
            ]
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in self._tools.values()
        ]

    async def dispatch(self, call: ToolCallRequest) -> ToolResult:
        """Execute one tool call under the FR-9 + FR-19 contract. Never raises for tool-side issues
        — failures come back as ``ok=False`` results the model can read and react to."""
        spec = self._tools.get(call.name)
        if spec is None:  # FR-9: unknown tool name → tool-error, never execute
            return ToolResult(call.id, call.name, ok=False, content=f"error: unknown tool '{call.name}'")
        if spec.effect_class not in self.allow_effect_classes:  # FR-19: default-deny
            return ToolResult(
                call.id, call.name, ok=False,
                content=f"error: tool '{call.name}' ({spec.effect_class}) is not permitted by policy",
            )
        try:
            out = spec.handler(call.arguments)
            if inspect.isawaitable(out):
                out = await out
            raw = out if isinstance(out, str) else json.dumps(out, default=str)
            content, truncated = apply_result_policy(raw, max_bytes=self.result_max_bytes)
            return ToolResult(call.id, call.name, ok=True, content=content, truncated=truncated)
        except Exception as exc:  # tool failure is data, not a loop crash
            return ToolResult(call.id, call.name, ok=False, content=f"error: {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- session (FR-1 / FR-15)
@dataclass
class SessionConfig:
    """FR-15 loop-safety configuration."""

    max_turns: int = 12
    max_tool_calls_per_turn: int = 16
    repeated_call_limit: int = 3  # same (name, args) more than N times → break
    max_total_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None


@dataclass
class AgenticResult:
    """Outcome of a :meth:`AgenticSession.send`. ``stop_reason`` ∈ completed | max_turns |
    repeated_calls | budget."""

    text: str
    stop_reason: str
    turns: int
    total_tokens: int
    total_cost_usd: float
    messages: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.stop_reason == "completed"


def _resolve_tool_format(agent: BaseAgent) -> str:
    """Pick the provider tool/message dialect. Temporary shim until agents expose it directly (0.2)."""
    return "anthropic" if "Claude" in type(agent).__name__ else "openai"


def _assistant_message(turn: AgenticTurn, fmt: str) -> dict:
    if fmt == "anthropic":
        content: list[dict] = []
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        for tc in turn.tool_calls:
            content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
        return {"role": "assistant", "content": content or turn.text}
    msg: dict = {"role": "assistant", "content": turn.text or None}
    if turn.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return msg


def _tool_result_messages(results: list[ToolResult], fmt: str) -> list[dict]:
    if fmt == "anthropic":
        return [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r.tool_call_id, "content": r.content,
                     "is_error": not r.ok}
                    for r in results
                ],
            }
        ]
    return [{"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content} for r in results]


class AgenticSession:
    """Multi-turn tool-use loop over a single tool-capable agent (FR-1).

    Usage::

        session = AgenticSession(agent, registry, system_prompt="...")
        result = await session.send("How ready is this project?")
        print(result.text, result.stop_reason)
    """

    def __init__(
        self,
        agent: BaseAgent,
        registry: ToolRegistry,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[SessionConfig] = None,
        tool_format: Optional[str] = None,
    ) -> None:
        if not agent.supports_tool_use():
            raise UnsupportedToolUseError(
                f"{type(agent).__name__} does not support tool use; cannot drive an AgenticSession"
            )
        self.agent = agent
        self.registry = registry
        self.system_prompt = system_prompt
        self.config = config or SessionConfig()
        self.tool_format = tool_format or _resolve_tool_format(agent)
        self.messages: list[dict] = []
        self.total_tokens = 0
        self.total_cost_usd = 0.0

    async def send(self, user_message: str) -> AgenticResult:
        """Append a user message and run the loop to a terminal state."""
        self.messages.append({"role": "user", "content": user_message})
        return await self._run()

    async def _run(self) -> AgenticResult:
        tools = self.registry.for_format(self.tool_format)
        call_counts: dict[tuple, int] = {}
        cfg = self.config
        last_text = ""

        for turn in range(1, cfg.max_turns + 1):
            # FR-15: fail-closed budget check BEFORE spending another model call.
            if cfg.max_total_tokens is not None and self.total_tokens >= cfg.max_total_tokens:
                logger.warning("AgenticSession stopped: token budget reached (%s)", self.total_tokens)
                return self._result(last_text, "budget", turn - 1)
            if cfg.max_cost_usd is not None and self.total_cost_usd >= cfg.max_cost_usd:
                logger.warning("AgenticSession stopped: cost budget reached ($%.4f)", self.total_cost_usd)
                return self._result(last_text, "budget", turn - 1)

            agent_turn = await self.agent.agenerate_tools(
                self.messages, tools, system_prompt=self.system_prompt
            )
            self._account(agent_turn)
            last_text = agent_turn.text or last_text
            self.messages.append(_assistant_message(agent_turn, self.tool_format))

            if not agent_turn.tool_calls:  # model answered → done
                return self._result(agent_turn.text, "completed", turn)

            calls = agent_turn.tool_calls[: cfg.max_tool_calls_per_turn]

            # FR-15: repeated-identical-call breaker (guards the {}-degraded doom loop).
            for c in calls:
                key = (c.name, json.dumps(c.arguments, sort_keys=True, default=str))
                call_counts[key] = call_counts.get(key, 0) + 1
                if call_counts[key] > cfg.repeated_call_limit:
                    logger.warning("AgenticSession stopped: repeated identical call %s", c.name)
                    return self._result(last_text, "repeated_calls", turn)

            results = [await self.registry.dispatch(c) for c in calls]
            self.messages.extend(_tool_result_messages(results, self.tool_format))

        return self._result(last_text, "max_turns", cfg.max_turns)

    def _account(self, turn: AgenticTurn) -> None:
        if turn.token_usage is not None:
            self.total_tokens += turn.token_usage.total or 0
            try:
                self.total_cost_usd += turn.token_usage.cost_estimate
            except Exception:  # cost estimation is best-effort
                pass

    def _result(self, text: str, stop_reason: str, turns: int) -> AgenticResult:
        return AgenticResult(
            text=text,
            stop_reason=stop_reason,
            turns=turns,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
            messages=self.messages,
        )
