"""Presentation Polish (Tier 1) — deterministic, $0 design-system for generated all-Python apps.

Takes a structurally-complete-but-bare app (FastAPI + Jinja2 + HTMX + plain CSS, as emitted by
``backend_codegen``) and makes it *presentable*: a real mounted stylesheet built from design tokens,
a curated theme, a responsive layout, and a WCAG 2.2 AA accessibility baseline — applied to the
**existing** semantic HTML with **zero edits to owned template bodies**.

This is "applicational completion of the presentation layer" (CLAUDE.md bucket 1): a well-dressed
skeleton, not brand content. It is fully deterministic ($0, no LLM) and byte-stable for a given
(theme, SDK version). The optional skill-driven bespoke tier (Tier 2) is a separate, gated path and
is **not** part of this package yet.

Public surface:
    - :class:`ThemeTokens`, :func:`contrast_ratio`, :func:`verify_contrast` (``tokens``)
    - :data:`THEMES`, :func:`get_theme`, :func:`theme_names` (``themes``)
    - :func:`render_stylesheet`, :func:`render_static_setup`, :data:`POLISH_MARKER` (``css``)
    - :class:`PolishConfig`, :class:`PolishResult`, :func:`apply_polish` (``engine``)
    - :class:`PresentationPolishFileProvider` (``provider``)
"""

from __future__ import annotations

from .css import POLISH_MARKER, render_static_setup, render_stylesheet
from .engine import PolishConfig, PolishResult, apply_polish
from .provider import PresentationPolishFileProvider
from .themes import THEMES, get_theme, theme_names
from .tokens import ThemeTokens, contrast_ratio, verify_contrast

__all__ = [
    "ThemeTokens",
    "contrast_ratio",
    "verify_contrast",
    "THEMES",
    "get_theme",
    "theme_names",
    "render_stylesheet",
    "render_static_setup",
    "POLISH_MARKER",
    "PolishConfig",
    "PolishResult",
    "apply_polish",
    "PresentationPolishFileProvider",
]
