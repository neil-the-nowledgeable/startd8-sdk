"""Native-message builder for consultation continuity (FR-NC-5/6/8).

Builds the canonical ``messages.Message`` list for a model's thread from its **valid history**
(ok turns only, alternating) plus the new user turn — the native replacement for the transcript
prefix. Prior-turn images are **re-sent with integrity** (FR-NC-6): reloaded from the persisted
``SessionImageRef.source_path`` and the bytes actually read are re-hashed against the stored hash;
any of the three failure cases (no path / missing / mismatch) degrades to an ``[image unavailable]``
marker and never sends different bytes than the audit trail claims. A cumulative byte ceiling caps
re-sent-image cost, dropping oldest-first.
"""

from __future__ import annotations

from typing import Optional

from ..agents.messages import Message
from ..agents.multimodal import ImageInput, ImageValidationError, load_image
from ..logging_config import get_logger
from .models import ConsultationSession, TurnRole

logger = get_logger(__name__)

RESEND_IMAGE_BYTE_CEILING = 8 * 1024 * 1024  # cap on cumulative re-sent image bytes per request
IMAGE_UNAVAILABLE = "[image unavailable]"
# Approx text-context ceiling for the rebuilt thread (FR-NC-8a). ~4 chars/token → ~120k tokens;
# generous but bounded so a long thread degrades by truncation rather than a provider hard-error.
DEFAULT_TEXT_CHAR_BUDGET = 480_000


def _text_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    return sum(len(p) for p in content if isinstance(p, str))


def reload_image(ref) -> "Optional[ImageInput]":
    """Reload + revalidate a persisted image ref; ``None`` if unavailable (FR-NC-6, TOCTOU read-once).

    ``load_image`` hashes the bytes it actually reads, so comparing that hash to the stored ref is
    TOCTOU-safe: the hashed bytes are the bytes that would be sent.
    """
    if not getattr(ref, "source_path", None):
        return None  # pasted image / no on-disk origin — can't reload
    try:
        img = load_image(ref.source_path)
    except (ImageValidationError, OSError):
        return None  # missing / moved / unreadable
    if img.sha256 != ref.sha256:
        return None  # bytes changed since capture — never send different bytes
    return img


def build_messages(
    session: ConsultationSession,
    model_id: str,
    new_prompt: str,
    new_images: "Optional[list[ImageInput]]" = None,
    *,
    resend_images: bool = True,
    byte_ceiling: int = RESEND_IMAGE_BYTE_CEILING,
    char_budget: int = DEFAULT_TEXT_CHAR_BUDGET,
) -> "list[Message]":
    """Canonical messages from valid history + the new user turn (FR-NC-5/6/8/8a)."""
    history: list[Message] = []
    budget = byte_ceiling

    for turn in session.valid_history(model_id):
        if turn.role == TurnRole.user:
            text = turn.text or ""
            imgs: list = []
            degraded = 0
            if resend_images and turn.images:
                for ref in turn.images:
                    img = reload_image(ref)
                    if img is not None and img.size_bytes <= budget:
                        imgs.append(img)
                        budget -= img.size_bytes
                    else:
                        degraded += 1  # FR-NC-6 degrade: mark, never send wrong bytes
            if degraded:
                logger.warning(
                    "consultation %s/%s: %d prior image(s) unavailable on re-send (degraded)",
                    session.id, model_id, degraded,
                )
                text = (text + " " + IMAGE_UNAVAILABLE).strip()
            history.append(Message(role="user", content=([text, *imgs] if imgs else text)))
        else:  # assistant — text-only in v1 (FR-NC-8)
            history.append(Message(role="assistant", content=turn.text or ""))

    # The new user turn: fresh in-flight images carry their own bytes (no reload needed).
    new_turn = (
        Message(role="user", content=[new_prompt, *new_images])
        if new_images else Message(role="user", content=new_prompt)
    )

    # FR-NC-8a: bound the rebuilt thread. Drop oldest user+assistant PAIRS from the front (keeps
    # the alternation + starts-with-user invariant, FR-NC-8) until the text fits, always keeping
    # the new turn. Image bytes aren't counted here — those are bounded by byte_ceiling above.
    def total_chars() -> int:
        return _text_len(new_turn.content) + sum(_text_len(m.content) for m in history)

    while history and total_chars() > char_budget and len(history) >= 2:
        dropped = history[:2]  # a (user, assistant) pair
        history = history[2:]
        logger.warning(
            "consultation %s/%s: thread over %d chars — dropped %d oldest turn(s) (FR-NC-8a)",
            session.id, model_id, char_budget, len(dropped),
        )

    return [*history, new_turn]
