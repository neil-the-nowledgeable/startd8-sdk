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
from ..otel import ProjectContext, add_project_context_to_span
from .agentic_otel import set_attributes as otel_set_attributes
from .agentic_otel import span as otel_span
from .base import BaseAgent
from .compaction import compact, find_clean_cut, is_context_window_error

logger = get_logger(__name__)


# FR-CC3: register the run-level span (agentic.session) so the observability artifact generator
# (collect_span_descriptors → artifact_generator) auto-derives Dashboard/SLO/Alert artifacts. This
# DESCRIBES the span already emitted by AgenticSession._run/.stream (since fce92b6c) — it does not
# emit a new span. Harvested via collector.py:_INSTRUMENTED_MODULES.
_OTEL_DESCRIPTORS = {
    "category": "ai_agent_observability",
    "orientation": "system",
    "spans": [
        {
            "name_pattern": "agentic.session",
            "kind": "INTERNAL",
            "attributes": [
                "agentic.provider",
                "agentic.model",
                "agentic.tool_format",
                "agentic.tool_count",
                "agentic.streaming",
                "agentic.stop_reason",
                "agentic.turns",
                "agentic.total_tokens",
                "agentic.total_cost_usd",
                "gen_ai.system",
                "gen_ai.request.model",
                "gen_ai.usage.input_tokens",
                "gen_ai.usage.output_tokens",
                "io.contextcore.project.id",
                "io.contextcore.task.id",
            ],
        },
        {
            "name_pattern": "agentic.turn",
            "kind": "INTERNAL",
            "attributes": ["agentic.turn", "agentic.tool_calls", "agentic.stop_reason"],
        },
        {
            "name_pattern": "agentic.tool_call",
            "kind": "INTERNAL",
            "attributes": ["agentic.tool", "agentic.tool_ok", "agentic.tool_truncated"],
        },
        {
            "name_pattern": "agentic.compaction",
            "kind": "INTERNAL",
            "attributes": ["agentic.compaction_attempt"],
        },
    ],
}


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
    # FR-3/FR-4 reactive compaction: on a context-window overflow, summarize older history and
    # retry, keeping the most-recent `compact_keep_recent` messages intact. Bounded by max_compactions.
    compact_keep_recent: int = 6
    max_compactions: int = 3


@dataclass
class AgenticResult:
    """Outcome of a :meth:`AgenticSession.send`. ``stop_reason`` ∈ completed | max_turns |
    repeated_calls | budget | context_overflow."""

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


def stream_sync(async_event_iter):
    """Sync bridge for `stream()` (FR-S5a). Drives an ``AsyncIterator[AgenticEvent]`` from a
    synchronous caller (e.g. the questionary TUI REPL, which cannot ``asyncio.run`` an async
    generator) and yields each event. Runs its own event loop, pumping one event per ``__anext__``."""
    import asyncio

    agen = async_event_iter
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                return
    finally:
        try:
            loop.run_until_complete(agen.aclose())  # FR-S5b: propagate teardown on early exit
        except Exception:
            pass
        loop.close()


async def tee(async_event_iter, n: int = 2):
    """Fan-out an async event stream into *n* independent iterators (FR-S7, OQ-S1).

    Buffers events so a slow consumer does not drop events, and a blocked consumer does not deadlock
    the others (each gets its own queue). Returns a list of *n* async iterators."""
    import asyncio

    queues = [asyncio.Queue() for _ in range(n)]
    _SENTINEL = object()

    async def _pump():
        try:
            async for ev in async_event_iter:
                for q in queues:
                    await q.put(ev)
        finally:
            for q in queues:
                await q.put(_SENTINEL)

    asyncio.ensure_future(_pump())  # the running loop keeps a ref until it completes

    async def _branch(q):
        while True:
            ev = await q.get()
            if ev is _SENTINEL:
                return
            yield ev

    return [_branch(q) for q in queues]


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
        project_context: "Optional[ProjectContext]" = None,
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
        # FR-18: optional ContextCore project/task attribution. When set, the root session span is
        # stamped with io.contextcore.* attributes so an agentic run is attributable in the same
        # project views humans + other agents use. The loop stays fully usable without it.
        self.project_context = project_context
        self.messages: list[dict] = []
        self.total_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

    async def send(self, user_message: str) -> AgenticResult:
        """Append a user message and run the loop to a terminal state."""
        self.messages.append({"role": "user", "content": user_message})
        return await self._run()

    async def _run(self) -> AgenticResult:
        # FR-18: a root session span wraps the whole loop; the outcome is stamped on return.
        with otel_span(
            "agentic.session",
            **{
                "agentic.provider": self.agent.name,
                "agentic.model": self.agent.model,
                # gen_ai.* semantic conventions — align with the AI Agent Observability taxonomy so
                # the shipped artifact generator (dashboards/SLOs) can target agentic runs.
                "gen_ai.system": self.agent.name,
                "gen_ai.request.model": self.agent.model,
                "agentic.tool_format": self.tool_format,
                "agentic.tool_count": len(self.registry),
            },
        ) as session_span:
            if self.project_context is not None:
                add_project_context_to_span(session_span, self.project_context)
            result = await self._run_loop()
            otel_set_attributes(
                session_span,
                **{
                    "agentic.stop_reason": result.stop_reason,
                    "agentic.turns": result.turns,
                    "agentic.total_tokens": result.total_tokens,
                    "agentic.total_cost_usd": result.total_cost_usd,
                    "gen_ai.usage.input_tokens": self.total_input_tokens,
                    "gen_ai.usage.output_tokens": self.total_output_tokens,
                },
            )
            return result

    async def _run_loop(self) -> AgenticResult:
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

            with otel_span("agentic.turn", **{"agentic.turn": turn}) as turn_span:
                try:
                    agent_turn = await self._call_with_compaction(tools)
                except ContextWindowExceededError:
                    logger.warning("AgenticSession stopped: context overflow unrecoverable by compaction")
                    otel_set_attributes(turn_span, **{"agentic.stop_reason": "context_overflow"})
                    return self._result(last_text, "context_overflow", turn)
                self._account(agent_turn)
                last_text = agent_turn.text or last_text
                self.messages.append(_assistant_message(agent_turn, self.tool_format))

                n_calls = len(agent_turn.tool_calls)
                otel_set_attributes(turn_span, **{"agentic.tool_calls": n_calls})

                if not agent_turn.tool_calls:  # model answered → done
                    return self._result(agent_turn.text, "completed", turn)

                calls = agent_turn.tool_calls[: cfg.max_tool_calls_per_turn]

                # FR-15: repeated-identical-call breaker (guards the {}-degraded doom loop).
                for c in calls:
                    key = (c.name, json.dumps(c.arguments, sort_keys=True, default=str))
                    call_counts[key] = call_counts.get(key, 0) + 1
                    if call_counts[key] > cfg.repeated_call_limit:
                        logger.warning("AgenticSession stopped: repeated identical call %s", c.name)
                        otel_set_attributes(turn_span, **{"agentic.stop_reason": "repeated_calls"})
                        return self._result(last_text, "repeated_calls", turn)

                results = []
                for c in calls:
                    with otel_span("agentic.tool_call", **{"agentic.tool": c.name}) as tool_span:
                        res = await self.registry.dispatch(c)
                        otel_set_attributes(
                            tool_span,
                            **{"agentic.tool_ok": res.ok, "agentic.tool_truncated": res.truncated},
                        )
                        results.append(res)
                self.messages.extend(_tool_result_messages(results, self.tool_format))

        return self._result(last_text, "max_turns", cfg.max_turns)

    # ----------------------------------------------------------------- streaming (FR-2, MVP-A)
    async def stream(self, user_message: str):
        """Stream a run as typed events (FR-S5): ``StreamStart`` → per-turn ``TextDelta``/tool events
        → terminal ``RunComplete(result)``. The event stream is teeable (FR-S7) and the loop logic is
        shared with :meth:`send` (same tool dispatch, budget, compaction). ``send()`` is unchanged and
        remains the non-streaming default."""
        from ..models import RunComplete, StreamStart

        self.messages.append({"role": "user", "content": user_message})
        yield StreamStart()
        with otel_span(
            "agentic.session",
            **{
                "agentic.provider": self.agent.name,
                "agentic.model": self.agent.model,
                "gen_ai.system": self.agent.name,
                "gen_ai.request.model": self.agent.model,
                "agentic.streaming": True,
                "agentic.tool_count": len(self.registry),
            },
        ) as session_span:
            if self.project_context is not None:
                add_project_context_to_span(session_span, self.project_context)
            result_holder: list = []
            async for ev in self._stream_loop(result_holder):
                if isinstance(ev, RunComplete):
                    otel_set_attributes(
                        session_span,
                        **{
                            "agentic.stop_reason": ev.result.stop_reason,
                            "agentic.turns": ev.result.turns,
                            "agentic.total_tokens": ev.result.total_tokens,
                            "gen_ai.usage.input_tokens": self.total_input_tokens,
                            "gen_ai.usage.output_tokens": self.total_output_tokens,
                        },
                    )
                yield ev

    async def _stream_loop(self, result_holder: list):
        from ..models import (
            ErrorEvent, RunComplete, ToolCallResult, ToolCallStarted, TurnComplete,
        )

        tools = self.registry.for_format(self.tool_format)
        call_counts: dict[tuple, int] = {}
        cfg = self.config
        last_text = ""

        for turn in range(1, cfg.max_turns + 1):
            if cfg.max_total_tokens is not None and self.total_tokens >= cfg.max_total_tokens:
                yield RunComplete(self._finish(result_holder, last_text, "budget", turn - 1))
                return
            if cfg.max_cost_usd is not None and self.total_cost_usd >= cfg.max_cost_usd:
                yield RunComplete(self._finish(result_holder, last_text, "budget", turn - 1))
                return

            turn_obj: Optional[AgenticTurn] = None
            try:
                async for ev in self._stream_one_call(tools):
                    if isinstance(ev, TurnComplete):
                        turn_obj = ev.turn  # primitive's terminal marker — captured, not forwarded
                    else:
                        yield ev  # TextDelta / CompactionEvent / StreamReset
            except ContextWindowExceededError as exc:
                yield ErrorEvent("context", "ContextWindowExceededError", str(exc), False)
                yield RunComplete(self._finish(result_holder, last_text, "context_overflow", turn))
                return

            assert turn_obj is not None  # the primitive always ends with TurnComplete
            self._account(turn_obj)
            last_text = turn_obj.text or last_text
            self.messages.append(_assistant_message(turn_obj, self.tool_format))

            if not turn_obj.tool_calls:
                yield TurnComplete(turn_obj)
                yield RunComplete(self._finish(result_holder, turn_obj.text, "completed", turn))
                return

            calls = turn_obj.tool_calls[: cfg.max_tool_calls_per_turn]
            for c in calls:
                key = (c.name, json.dumps(c.arguments, sort_keys=True, default=str))
                call_counts[key] = call_counts.get(key, 0) + 1
                if call_counts[key] > cfg.repeated_call_limit:
                    yield RunComplete(self._finish(result_holder, last_text, "repeated_calls", turn))
                    return

            results = []
            for c in calls:
                yield ToolCallStarted(c.id, c.name)
                with otel_span("agentic.tool_call", **{"agentic.tool": c.name}) as tool_span:
                    res = await self.registry.dispatch(c)
                    otel_set_attributes(tool_span, **{"agentic.tool_ok": res.ok})
                yield ToolCallResult(c.id, c.name, res.ok)
                results.append(res)
            self.messages.extend(_tool_result_messages(results, self.tool_format))
            yield TurnComplete(turn_obj)

        yield RunComplete(self._finish(result_holder, last_text, "max_turns", cfg.max_turns))

    async def _stream_one_call(self, tools: list):
        """Yield one turn's model events (text deltas + a terminal ``TurnComplete``), handling
        overflow → compaction → retry (FR-S9) with a ``StreamReset``/``CompactionEvent`` before each
        retry. Falls back to a single ``TextDelta`` for non-streaming agents (FR-S6). Raises
        :class:`ContextWindowExceededError` when overflow cannot be recovered."""
        from ..models import CompactionEvent, StreamReset, TextDelta, TurnComplete

        attempts = 0
        while True:
            try:
                if self.agent.supports_streaming():
                    async for ev in self.agent.agenerate_tools_stream(
                        self.messages, tools, system_prompt=self.system_prompt
                    ):
                        yield ev
                else:  # FR-S6 uniform fallback: one text delta + a synthetic TurnComplete
                    turn = await self.agent.agenerate_tools(
                        self.messages, tools, system_prompt=self.system_prompt
                    )
                    if turn.text:
                        yield TextDelta(turn.text)
                    yield TurnComplete(turn)
                return
            except Exception as exc:  # noqa: BLE001 — only overflow handled; others re-raise
                if not is_context_window_error(exc):
                    raise
                attempts += 1
                if attempts > self.config.max_compactions or find_clean_cut(
                    self.messages, self.tool_format, self.config.compact_keep_recent
                ) <= 0:
                    raise ContextWindowExceededError("context overflow unrecoverable by compaction") from exc
                yield StreamReset("overflow_retry")  # FR-S9: consumer clears partial text before retry
                yield CompactionEvent(attempts)
                with otel_span("agentic.compaction", **{"agentic.compaction_attempt": attempts}):
                    self.messages = await compact(
                        self.messages, self.tool_format, self._summarize, self.config.compact_keep_recent
                    )

    def _finish(self, holder: list, text: str, stop_reason: str, turns: int) -> "AgenticResult":
        result = self._result(text, stop_reason, turns)
        holder.append(result)
        return result

    async def _call_with_compaction(self, tools: list) -> AgenticTurn:
        """Call the model; on a context-window overflow (FR-3), compact older history (FR-4) and
        retry — up to ``max_compactions``. Raises :class:`ContextWindowExceededError` when the
        transcript cannot be compacted further (already minimal) or compaction is exhausted."""
        attempts = 0
        while True:
            try:
                return await self.agent.agenerate_tools(
                    self.messages, tools, system_prompt=self.system_prompt
                )
            except Exception as exc:  # noqa: BLE001 — only context-overflow is handled; others re-raise
                if not is_context_window_error(exc):
                    raise
                attempts += 1
                if attempts > self.config.max_compactions:
                    raise ContextWindowExceededError(
                        "context overflow persists after compaction"
                    ) from exc
                if find_clean_cut(self.messages, self.tool_format, self.config.compact_keep_recent) <= 0:
                    raise ContextWindowExceededError(
                        "cannot compact further (transcript already at minimum)"
                    ) from exc
                with otel_span("agentic.compaction", **{"agentic.compaction_attempt": attempts}):
                    self.messages = await compact(
                        self.messages, self.tool_format, self._summarize, self.config.compact_keep_recent
                    )
                logger.warning("AgenticSession compacted history (compaction %d)", attempts)

    async def _summarize(self, text: str) -> str:
        """Summarize transcript head via the agent's plain text path (no tools)."""
        prompt = (
            "Summarize the following conversation history concisely, preserving key facts, decisions, "
            "and any tool results that later turns may rely on:\n\n" + text
        )
        result = await self.agent.agenerate(prompt)
        return result.text

    def _account(self, turn: AgenticTurn) -> None:
        if turn.token_usage is not None:
            self.total_tokens += turn.token_usage.total or 0
            self.total_input_tokens += turn.token_usage.input or 0
            self.total_output_tokens += turn.token_usage.output or 0
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
