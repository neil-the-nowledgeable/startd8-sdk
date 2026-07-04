"""Canonical multi-turn message contract + per-provider renderers (FR-NC-1/1a/1b/2).

The provider-uniform, tool-free "multi-turn text (+image)" primitive the codebase lacked (distinct
from the tool-shaped ``agenerate_tools`` list). A :class:`Message` is ``{role, content}`` where
``content`` is a string or a list of parts (``str`` text or :class:`~.multimodal.ImageInput`). This
module **owns** the contract; each provider renders it to its native shape here, reusing the M1
image helpers. ``system`` is **not** a role — system content is routed to each provider's own sink
by the agents (Anthropic ``system`` param / OpenAI system message / Gemini ``system_instruction``),
per FR-NC-1a.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .multimodal import ImageInput, to_anthropic_block, to_gemini_part, to_openai_part

SCHEMA_VERSION = 1  # FR-NC-1b — bump on a breaking part/role change
ROLES = ("user", "assistant")

Part = Union[str, ImageInput]


@dataclass(frozen=True)
class Message:
    role: str                       # "user" | "assistant"
    content: "Union[str, list[Part]]"


class MessageContractError(ValueError):
    """Raised for an unknown role or part kind (FR-NC-1b — reject-loud, never silently drop)."""


def _parts(content) -> "list[tuple[str, object]]":
    """Normalize content to ``[(kind, value)]`` with kind in {'text','image'}; reject unknowns."""
    if isinstance(content, str):
        return [("text", content)]
    out: list = []
    for p in content:
        if isinstance(p, str):
            out.append(("text", p))
        elif isinstance(p, ImageInput):
            out.append(("image", p))
        else:
            raise MessageContractError(f"unknown message part kind: {type(p).__name__}")
    return out


def _text_only(content) -> str:
    """Flatten content to text (assistant turns are text-only in v1 — FR-NC-8)."""
    return " ".join(v for k, v in _parts(content) if k == "text").strip()


def validate(messages: "list[Message]") -> None:
    """Structural well-formedness (FR-NC-8): known roles, alternating, starts user, no empty assistant."""
    if not messages:
        return
    prev = None
    for i, m in enumerate(messages):
        if m.role not in ROLES:
            raise MessageContractError(f"unknown role: {m.role!r}")
        if i == 0 and m.role != "user":
            raise MessageContractError("message list must start with a user turn")
        if m.role == prev:
            raise MessageContractError(f"non-alternating roles at index {i} ({m.role})")
        if m.role == "assistant" and not _text_only(m.content):
            raise MessageContractError(f"empty assistant turn at index {i}")
        prev = m.role


# ── per-provider renderers (turns only; agents route system to their own sink) ──
def render_anthropic(messages: "list[Message]") -> "list[dict]":
    """Anthropic content-block messages."""
    validate(messages)
    out = []
    for m in messages:
        content = []
        for kind, val in _parts(m.content):
            content.append({"type": "text", "text": val} if kind == "text" else to_anthropic_block(val))
        out.append({"role": m.role, "content": content})
    return out


def render_openai_turns(messages: "list[Message]") -> "list[dict]":
    """OpenAI role-tagged messages; assistant is text-only, user carries parts (FR-NC-8)."""
    validate(messages)
    out = []
    for m in messages:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": _text_only(m.content)})
            continue
        parts = []
        for kind, val in _parts(m.content):
            parts.append({"type": "text", "text": val} if kind == "text" else to_openai_part(val))
        # A single text part can be a bare string; a parts list carries images.
        content = parts[0]["text"] if len(parts) == 1 and parts[0].get("type") == "text" else parts
        out.append({"role": "user", "content": content})
    return out


def render_gemini(messages: "list[Message]") -> "list[dict]":
    """Gemini ``contents`` — role is ``model`` for assistant (NOT ``assistant``) — FR-NC-2."""
    validate(messages)
    out = []
    for m in messages:
        role = "model" if m.role == "assistant" else "user"
        parts = []
        for kind, val in _parts(m.content):
            parts.append({"text": val} if kind == "text" else to_gemini_part(val))
        out.append({"role": role, "parts": parts})
    return out
