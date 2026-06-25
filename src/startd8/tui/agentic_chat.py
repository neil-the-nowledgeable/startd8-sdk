"""TUI agentic chat (FR-10) — multi-turn conversation memory for the TUI's "Chat with Agent".

The legacy TUI chat (`mixin_enhancement_chain.chat_with_agent`) calls `agent.generate(user_input)`
once per line: **stateless** — each message is an independent generation with no history. This module
upgrades it to a persistent :class:`AgenticSession` so the conversation actually remembers prior
turns.

**Scope (FR-10 / R4-F6 — opt-in, legacy retained):**
- *Opt-in*: agentic mode is enabled only when ``STARTD8_TUI_AGENTIC`` is truthy **and** the selected
  agent implements the tool-use primitive (``supports_tool_use()``). Otherwise the caller keeps the
  legacy single-shot path. See :func:`agentic_mode_enabled`.
- *Sync bridge*: the REPL is synchronous (`questionary`); :func:`reply` runs the async session via
  ``asyncio.run`` so the existing loop stays thin (no async rewrite).
- *No tools by default*: the chat session is created with an **empty** ToolRegistry, so this is pure
  multi-turn conversation — no effectful surface. (Tool-enabled TUI chat is a later step gated on the
  FR-19 approval policy.)
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from ..agents.agentic import AgenticResult, AgenticSession, SessionConfig, ToolRegistry
from ..agents.base import BaseAgent

# A generous default budget so a casual chat doesn't run unbounded but won't surprise normal use.
_DEFAULT_TUI_CONFIG = SessionConfig(max_turns=8, max_total_tokens=200_000)


def agentic_mode_enabled(agent: BaseAgent) -> bool:
    """True iff the TUI should use the agentic loop for *agent* (opt-in + capability gate)."""
    flag = os.getenv("STARTD8_TUI_AGENTIC", "").strip().lower()
    opted_in = flag in {"1", "true", "yes", "on"}
    return opted_in and agent.supports_tool_use()


def make_chat_session(
    agent: BaseAgent,
    *,
    system_prompt: Optional[str] = None,
    config: Optional[SessionConfig] = None,
) -> AgenticSession:
    """Build a persistent, tool-less chat session (pure multi-turn memory) over *agent*."""
    return AgenticSession(
        agent,
        ToolRegistry([]),  # no tools: conversation memory only
        system_prompt=system_prompt,
        config=config or _DEFAULT_TUI_CONFIG,
    )


def reply(session: AgenticSession, user_input: str) -> AgenticResult:
    """Sync bridge: send a user line through the async session and return the result.

    Keeps the synchronous `questionary` REPL unchanged — it calls this once per line, and the session
    carries history across calls.
    """
    return asyncio.run(session.send(user_input))


def stream_reply(session: AgenticSession, user_input: str, on_text) -> AgenticResult:
    """Live-render bridge (FR-S11): drive the async event stream from the sync REPL, calling
    ``on_text(chunk)`` for each text delta as it arrives, and return the terminal result.

    Uses ``stream_sync`` so the synchronous `questionary` loop can consume the async generator. A
    ``StreamReset`` (overflow retry) signals the caller to clear partial text by calling
    ``on_text(None)``.
    """
    from ..agents.agentic import stream_sync
    from ..models import RunComplete, StreamReset, TextDelta

    result: Optional[AgenticResult] = None
    for ev in stream_sync(session.stream(user_input)):
        if isinstance(ev, TextDelta):
            on_text(ev.text)
        elif isinstance(ev, StreamReset):
            on_text(None)  # caller clears already-rendered partial text before the retry
        elif isinstance(ev, RunComplete):
            result = ev.result
    return result


def cost_suffix(result: AgenticResult) -> str:
    """A compact per-turn cost line for the chat panel subtitle (parity with the legacy token line)."""
    return f"tokens: {result.total_tokens} · cost≈${result.total_cost_usd:.4f} · turn {result.turns}"
