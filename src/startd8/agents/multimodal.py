"""Multimodal image input for agent generation (FR-MMC-2).

This is the **shared pre-adapter** (CRP R1-S1): it owns image loading, magic-byte
format validation, size/frame checks, base64 encoding, and mime resolution — so the
three per-provider render helpers (:func:`to_anthropic_block`, :func:`to_openai_part`,
:func:`to_gemini_part`) assemble *shape only* and never re-implement encoding/validation.

Design invariants:

* **Byte-identity (FR-MMC-2):** this module is only consulted when an agent actually
  receives images. When ``images`` is absent/empty the agent's request payload is
  byte-identical to today's text-only path — the provider agents branch on truthiness.
* **Validate before any model call (FR-MMC-1):** format is checked by decoding the
  header (magic bytes), **not** by trusting the file extension; a renamed HEIC, a
  non-image, an over-ceiling image, or a **multi-frame/animated** image is rejected here,
  before a single token is spent.
* **Distinct persisted type (FR-MMC-6 / R1-S4):** :class:`ImageInput` carries the
  in-flight *bytes*; :class:`ImageRef` is the persist-safe reference (path + hash + mime,
  **no bytes**). ``ImageInput.to_ref()`` bridges the two so a session never stores base64.

The full untrusted-path trust boundary (canonicalize, reject ``..``/symlink escapes,
allowed-root, bounded directory scan) is the selection layer's job (FR-MMC-14, M3.3);
:func:`load_image` still refuses non-regular files and symlinks as defense in depth.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Limits (FR-MMC-1) ────────────────────────────────────────────────────────
# 5 MB matches the Anthropic Messages API per-image base64 ceiling and is a good
# provider-portable default; the effective cap is the min across selected providers,
# resolved at the selection layer (OQ-6). This module enforces the local byte ceiling.
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_TURN = 2  # FR-MMC-1 (stored as a list so N-image is a config bump)

# Provider-portable formats (FR-MMC-1): PNG / JPEG / WebP / GIF.
_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})


class ImageValidationError(ValueError):
    """Raised when an image fails format/size/frame validation (FR-MMC-1)."""


# ── In-flight vs persisted types (R1-S4 / FR-MMC-6) ──────────────────────────
@dataclass(frozen=True)
class ImageRef:
    """Persist-safe image reference — path + content hash + mime, **no bytes**.

    This is what a :class:`ConsultationSession` stores (M2), so a session JSON never
    contains base64 (FR-MMC-6a). ``source_path`` may be ``None`` for images supplied as
    raw bytes with no on-disk origin.
    """

    sha256: str
    mime_type: str
    source_path: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass(frozen=True)
class ImageInput:
    """An in-flight image: validated bytes + resolved mime + content hash.

    Construct via :func:`load_image` (from a path) or :func:`image_from_bytes` (from
    raw bytes) so validation always runs. The three ``to_*`` helpers render this into a
    provider's native content shape.
    """

    data: bytes
    mime_type: str
    sha256: str
    source_path: Optional[str] = None

    @property
    def size_bytes(self) -> int:
        return len(self.data)

    @property
    def base64_data(self) -> str:
        """Base64 (ASCII) of the raw bytes — the shared encoding step (R1-S1)."""
        return base64.standard_b64encode(self.data).decode("ascii")

    def to_ref(self) -> ImageRef:
        """Downcast to the persist-safe :class:`ImageRef` (drops the bytes)."""
        return ImageRef(
            sha256=self.sha256,
            mime_type=self.mime_type,
            source_path=self.source_path,
            size_bytes=self.size_bytes,
        )


# ── Validation / construction ────────────────────────────────────────────────
def _sniff(data: bytes) -> tuple[str, bool]:
    """Return ``(mime_type, is_animated)`` by decoding the header (magic bytes).

    Raises :class:`ImageValidationError` if the bytes are not a recognised
    PNG/JPEG/WebP/GIF. Animation is detected so multi-frame inputs can be rejected
    (providers handle animation inconsistently — FR-MMC-1 / R2-F2).
    """
    if len(data) < 12:
        raise ImageValidationError("image is too small to be a valid PNG/JPEG/WebP/GIF")

    # PNG — 8-byte signature; APNG carries an 'acTL' chunk before IDAT.
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", (b"acTL" in data.split(b"IDAT", 1)[0])

    # JPEG — SOI marker; no animation.
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", False

    # GIF — 87a/89a; >1 Graphic Control Extension ⇒ animated.
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", data.count(b"\x21\xf9\x04") > 1

    # WebP — RIFF....WEBP; ANIM/ANMF chunk ⇒ animated.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", (b"ANIM" in data[:64] or b"ANMF" in data[:64])

    raise ImageValidationError(
        "unrecognised image format (magic-byte check failed); "
        "only PNG, JPEG, WebP, and GIF are supported"
    )


def image_from_bytes(
    data: bytes,
    *,
    source_path: Optional[str] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ImageInput:
    """Validate raw bytes and build an :class:`ImageInput` (the core entry point).

    Enforces: recognised format (magic bytes), allowed mime, byte ceiling, and
    single-frame (rejects animated GIF/WebP and APNG). Raises
    :class:`ImageValidationError` on any failure — *before* any model call.
    """
    if not data:
        raise ImageValidationError("image is empty")
    if len(data) > max_bytes:
        raise ImageValidationError(
            f"image is {len(data)} bytes, exceeds the {max_bytes}-byte ceiling"
        )

    mime, is_animated = _sniff(data)
    if mime not in _ALLOWED_MIME:  # defensive; _sniff only returns allowed mimes
        raise ImageValidationError(f"unsupported image mime type: {mime}")
    if is_animated:
        raise ImageValidationError(
            "multi-frame/animated images are not supported; supply a single-frame image"
        )

    return ImageInput(
        data=data,
        mime_type=mime,
        sha256=hashlib.sha256(data).hexdigest(),
        source_path=source_path,
    )


def load_image(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ImageInput:
    """Load and validate an image from a path.

    Defense in depth (partial FR-MMC-14): the path is resolved and must be a **regular
    file** — symlinks, FIFOs, and device nodes are rejected. The full trust boundary
    (allowed-root, ``..`` traversal, bounded directory scan) is enforced by the
    selection layer (M3.3) before this is called.
    """
    p = Path(path)
    # Reject symlinks explicitly (do not follow) before resolving.
    if p.is_symlink():
        raise ImageValidationError(f"refusing to read a symlinked image path: {p}")
    resolved = p.resolve()
    if not resolved.is_file():
        raise ImageValidationError(f"not a regular file: {resolved}")
    data = resolved.read_bytes()
    return image_from_bytes(data, source_path=str(resolved), max_bytes=max_bytes)


def validate_images(
    images: "list[ImageInput] | None",
    *,
    max_images: int = MAX_IMAGES_PER_TURN,
) -> "list[ImageInput]":
    """Normalise/validate a per-turn image list: cap count, return ``[]`` for falsy.

    The count cap (FR-MMC-1) is enforced here so every provider path shares it.
    """
    if not images:
        return []
    if len(images) > max_images:
        raise ImageValidationError(
            f"{len(images)} images supplied, exceeds the per-turn limit of {max_images}"
        )
    return list(images)


# ── Per-provider render helpers (shape only — R1-S1) ─────────────────────────
def to_anthropic_block(img: ImageInput) -> dict:
    """Anthropic Messages API image content block (base64 ``source``)."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": img.mime_type,
            "data": img.base64_data,
        },
    }


def to_openai_part(img: ImageInput) -> dict:
    """OpenAI chat-completions image content part (``image_url`` data-URL)."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{img.mime_type};base64,{img.base64_data}"},
    }


def to_gemini_part(img: ImageInput) -> dict:
    """Gemini inline-data content part.

    Returned as a ``PartDict`` (``{"inline_data": {"mime_type", "data"}}``) which the
    google-genai SDK coerces into a ``Part`` — keeps this module free of a genai import.
    Gemini takes raw bytes (it base64-encodes internally), so no base64 here.
    """
    return {"inline_data": {"mime_type": img.mime_type, "data": img.data}}


# ── Capability heuristic (FR-MMC-2a) ─────────────────────────────────────────
def model_supports_vision(model: str) -> bool:
    """Best-effort per-model vision capability (FR-MMC-2a).

    A **static** hint used to gate roster selection (M3/M4). It cannot guarantee a
    run-time success — a statically vision-capable model may still refuse a specific
    image (per-variant/entitlement), which is recorded as a per-model error, not a crash.
    Conservative: unknown models return ``False``.
    """
    m = (model or "").lower()
    # Anthropic: all Claude 3+ / 4.x are vision-capable.
    if "claude" in m:
        return any(t in m for t in ("claude-3", "opus", "sonnet", "haiku"))
    # OpenAI: 4o / 4-turbo / 4.1 / o-series / gpt-5 are multimodal; 3.5 is not.
    if m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        if "3.5" in m:
            return False
        return any(t in m for t in ("4o", "4-turbo", "4.1", "gpt-5", "o1", "o3", "o4", "vision"))
    # Google Gemini: 1.5 and 2.x are natively multimodal.
    if "gemini" in m:
        return any(t in m for t in ("1.5", "2.0", "2.5", "-pro", "-flash"))
    return False
