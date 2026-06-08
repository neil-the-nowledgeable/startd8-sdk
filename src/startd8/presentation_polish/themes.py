"""Curated theme presets for Presentation Polish.

These are *internalized* from the ``theme-factory`` skill's palette/typography sensibility — adapted
to plain-CSS custom properties for the server-rendered Jinja2/HTMX stack. No skill runs at use-time;
the knowledge is baked into deterministic :class:`ThemeTokens`.

Every theme here is gated by ``tests/unit/presentation_polish/test_themes.py`` to meet WCAG 2.2 AA
contrast on all critical pairs. Add a theme → the test proves it before it ships.

(Tier-1 ships a small set; the full theme-factory breadth and a $0 preview are follow-ups — OQ-5.)
"""

from __future__ import annotations

from typing import Dict, List

from .tokens import ThemeTokens

PROFESSIONAL = ThemeTokens(
    name="professional",
    label="Clean, trustworthy SaaS — blue accent, neutral grays.",
    bg="#ffffff",
    surface="#f5f7fa",
    text="#1a2230",
    muted="#515b6b",
    primary="#1d4ed8",
    on_primary="#ffffff",
    border="#d7dde6",
    success="#15803d",
    success_bg="#ecfdf3",
    danger="#b42318",
    danger_bg="#fef3f2",
    focus="#2563eb",
)

EDITORIAL = ThemeTokens(
    name="editorial",
    label="Warm, literary — serif headings, burnt-orange accent.",
    bg="#fffdf8",
    surface="#f7f1e6",
    text="#241c12",
    muted="#5b5040",
    primary="#9a3412",
    on_primary="#fffdf8",
    border="#d8c9ac",
    success="#3f6212",
    success_bg="#eef5e2",
    danger="#9f1239",
    danger_bg="#fdf2f4",
    focus="#b45309",
    heading_font="var(--font-serif)",
    scale_ratio=1.333,  # perfect-fourth — more editorial drama
)

MINIMAL = ThemeTokens(
    name="minimal",
    label="Monochrome, restrained — ink on paper, no chrome.",
    bg="#ffffff",
    surface="#fafafa",
    text="#111111",
    muted="#595959",
    primary="#111111",
    on_primary="#ffffff",
    border="#d4d4d4",
    success="#15803d",
    success_bg="#ecfdf3",
    danger="#b42318",
    danger_bg="#fef3f2",
    focus="#111111",
    radius="0.25rem",
    shadow="none",
)

THEMES: Dict[str, ThemeTokens] = {
    PROFESSIONAL.name: PROFESSIONAL,
    EDITORIAL.name: EDITORIAL,
    MINIMAL.name: MINIMAL,
}

DEFAULT_THEME = PROFESSIONAL.name


def theme_names() -> List[str]:
    """Available theme names, default first."""
    return [DEFAULT_THEME] + [n for n in THEMES if n != DEFAULT_THEME]


def get_theme(name: str) -> ThemeTokens:
    """Resolve a theme by name. Raises :class:`KeyError` with the valid set on a miss."""
    try:
        return THEMES[name]
    except KeyError:
        raise KeyError(
            f"unknown theme {name!r}; available: {', '.join(theme_names())}"
        ) from None
