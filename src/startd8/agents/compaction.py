"""Context-overflow detection + pairing-safe compaction (FR-3 / FR-4).

When a turn's transcript outgrows the model's context window, the loop summarizes the older history
and retries. The **load-bearing invariant** (CRP OQ-6 / R1-F2 / R5-D2): compaction must never orphan
a tool call from its result — both Anthropic and OpenAI hard-reject an assistant ``tool_use`` /
``tool_calls`` with no matching ``tool_result`` / ``tool`` message (and vice-versa). A naive "drop the
oldest N messages" can split a pair and turn a recoverable overflow into a permanent 400.

Strategy (OQ-6 resolved): keep the most-recent messages intact, summarize the older head into a
single text message — but **snap the cut to a clean boundary** so every kept ``tool_result`` still has
its ``tool_use`` in the kept tail. The head becomes prose (no tool blocks), so it cannot orphan
anything; the only risk is the tail, which :func:`find_clean_cut` guarantees against.

Detection (FR-3): :func:`is_context_window_error` maps a provider's overflow error (today surfaced as
a generic wrapped ``APIError``) to one boolean, per-provider signatures — Anthropic 400
``invalid_request_error`` "prompt is too long"; OpenAI ``context_length_exceeded``.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

# Provider overflow signatures (substring/regex match against the error text chain).
_OVERFLOW_PATTERNS = (
    re.compile(r"context[_ ]length[_ ]exceeded", re.I),          # OpenAI error code
    re.compile(r"maximum context length", re.I),                  # OpenAI message
    re.compile(r"prompt is too long", re.I),                      # Anthropic message
    re.compile(r"exceeds?\s+the\s+(maximum|context)", re.I),      # Anthropic-ish
    re.compile(r"context window", re.I),
    re.compile(r"too many tokens", re.I),
)


def is_context_window_error(exc: BaseException) -> bool:
    """True if *exc* (or any error in its ``__cause__`` / ``original_error`` chain) is a
    context-window overflow. Conservative: unknown errors are NOT treated as overflow."""
    seen: set[int] = set()
    cur: Any = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        text = f"{type(cur).__name__}: {cur}"
        if any(p.search(text) for p in _OVERFLOW_PATTERNS):
            return True
        # follow common wrapping links
        nxt = getattr(cur, "original_error", None) or getattr(cur, "__cause__", None)
        cur = nxt
    return False


# --------------------------------------------------------------------------- pairing invariant
def _is_tool_result_msg(m: dict, fmt: str) -> bool:
    if fmt == "anthropic":
        c = m.get("content")
        return m.get("role") == "user" and isinstance(c, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in c
        )
    return m.get("role") == "tool"


def _is_assistant_with_calls(m: dict, fmt: str) -> bool:
    if fmt == "anthropic":
        c = m.get("content")
        return m.get("role") == "assistant" and isinstance(c, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in c
        )
    return m.get("role") == "assistant" and bool(m.get("tool_calls"))


def _use_ids(m: dict, fmt: str) -> list[str]:
    if fmt == "anthropic":
        c = m.get("content")
        if m.get("role") == "assistant" and isinstance(c, list):
            return [b.get("id") for b in c if isinstance(b, dict) and b.get("type") == "tool_use"]
        return []
    if m.get("role") == "assistant" and m.get("tool_calls"):
        return [tc.get("id") for tc in m["tool_calls"]]
    return []


def _result_ids(m: dict, fmt: str) -> list[str]:
    if fmt == "anthropic":
        c = m.get("content")
        if m.get("role") == "user" and isinstance(c, list):
            return [b.get("tool_use_id") for b in c if isinstance(b, dict) and b.get("type") == "tool_result"]
        return []
    if m.get("role") == "tool":
        return [m.get("tool_call_id")]
    return []


def pairing_is_valid(messages: list[dict], fmt: str) -> bool:
    """Every ``tool_result`` references a ``tool_use`` that appeared earlier, and every ``tool_use``
    has a later ``tool_result``. The invariant compaction must preserve."""
    declared: set[str] = set()
    resolved: set[str] = set()
    for m in messages:
        for rid in _result_ids(m, fmt):
            if rid not in declared:
                return False  # orphaned result (its call was dropped)
            resolved.add(rid)
        for uid in _use_ids(m, fmt):
            declared.add(uid)
    return declared == resolved  # no dangling call without a result


def find_clean_cut(messages: list[dict], fmt: str, keep_recent: int) -> int:
    """Index ``i`` such that ``messages[:i]`` (head, to summarize) and ``messages[i:]`` (tail, to keep)
    split on a boundary that keeps every tool-call/result **pair intact in the tail**.

    Starts from "keep the last ``keep_recent``" and moves the boundary earlier while (a) the first
    kept message is a tool-result (its call is in the head → orphan), or (b) the message just before
    the cut is an assistant-with-calls (its results are in the tail → split). Returns 0 when nothing
    can be safely summarized.
    """
    n = len(messages)
    cut = max(0, n - keep_recent)
    while cut > 0:
        if _is_tool_result_msg(messages[cut], fmt):
            cut -= 1
            continue
        if _is_assistant_with_calls(messages[cut - 1], fmt):
            cut -= 1
            continue
        break
    return cut


def render_head(head: list[dict], fmt: str) -> str:
    """Flatten head messages into a readable transcript for the summarizer."""
    lines: list[str] = []
    for m in head:
        role = m.get("role", "?")
        content = m.get("content")
        parts: list[str] = []
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    parts.append(str(b))
                elif b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "tool_use":
                    parts.append(f"[called {b.get('name')}({b.get('input')})]")
                elif b.get("type") == "tool_result":
                    parts.append(f"[tool result: {b.get('content')}]")
        elif content:
            parts.append(str(content))
        for tc in m.get("tool_calls") or []:
            parts.append(f"[called {tc.get('function', {}).get('name')}]")
        lines.append(f"{role}: {' '.join(p for p in parts if p)}".rstrip())
    return "\n".join(lines)


_SUMMARY_PREFIX = "[Earlier conversation, summarized to fit the context window]\n"


def _summary_message(summary: str, fmt: str) -> dict:
    # Injected as a user message (uniform across dialects); a no-tool text block can never orphan.
    if fmt == "anthropic":
        return {"role": "user", "content": _SUMMARY_PREFIX + summary}
    return {"role": "user", "content": _SUMMARY_PREFIX + summary}


async def compact(
    messages: list[dict],
    fmt: str,
    summarizer: Callable[[str], Awaitable[str]],
    keep_recent: int,
) -> list[dict]:
    """Return a compacted transcript: older head → one summary message, recent tail kept verbatim.

    Pairing is preserved by construction (:func:`find_clean_cut`). Returns the input unchanged when no
    safe cut exists (transcript already minimal)."""
    cut = find_clean_cut(messages, fmt, keep_recent)
    if cut <= 0:
        return messages
    head, tail = messages[:cut], messages[cut:]
    summary = await summarizer(render_head(head, fmt))
    return [_summary_message(summary, fmt)] + tail
