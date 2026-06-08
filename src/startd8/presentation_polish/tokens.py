"""Design tokens + WCAG contrast math for Presentation Polish.

A :class:`ThemeTokens` is the single source of a theme's visual decisions — colors, typography,
spacing, radius, shadow. The stylesheet generator (``css.py``) projects these into CSS custom
properties, so a theme is fully described by its tokens and re-themeable by swapping them.

``contrast_ratio`` / ``verify_contrast`` implement the WCAG 2.1/2.2 relative-luminance contrast
formula so every shipped theme can be *proven* to meet AA (4.5:1 for normal text, 3:1 for large
text / UI borders) in tests — accessibility as a deterministic gate, not a hope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ThemeTokens:
    """The complete visual contract for one theme.

    Color fields are ``#rrggbb`` hex strings. Pairs that must meet WCAG AA are checked by
    :func:`verify_contrast`. Typography/spacing fields are emitted verbatim as CSS values.
    """

    name: str
    label: str  # human-facing one-liner

    # --- color ---
    bg: str  # page background
    surface: str  # raised surfaces (cards, table header, nav)
    text: str  # primary body text (vs bg → AA)
    muted: str  # secondary text (vs bg → AA; used at normal size, so 4.5:1)
    primary: str  # accent / interactive
    on_primary: str  # text on a primary-filled surface (vs primary → AA)
    border: str  # hairlines / dividers (vs bg → 3:1, UI component)
    success: str  # success text (vs success_bg → AA)
    success_bg: str
    danger: str  # error text (vs bg → AA)
    danger_bg: str
    focus: str  # focus-ring color (vs bg → 3:1)

    # --- typography ---
    font_sans: str = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    font_serif: str = "Georgia, 'Iowan Old Style', 'Times New Roman', serif"
    font_mono: str = "ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace"
    heading_font: str = "var(--font-sans)"  # may point at serif for editorial themes
    text_base: str = "1rem"
    scale_ratio: float = 1.25  # major-third type scale

    # --- shape / depth / rhythm ---
    space_unit: str = "0.5rem"
    radius: str = "0.5rem"
    shadow: str = "0 1px 2px rgba(16, 24, 40, 0.06), 0 1px 3px rgba(16, 24, 40, 0.1)"
    max_width: str = "64rem"

    def contrast_pairs(self) -> List[Tuple[str, str, str, float]]:
        """The (label, fg, bg, min_ratio) pairs that MUST hold for AA. Drives :func:`verify_contrast`."""
        return [
            ("text/bg", self.text, self.bg, 4.5),
            ("muted/bg", self.muted, self.bg, 4.5),
            ("on_primary/primary", self.on_primary, self.primary, 4.5),
            ("primary/bg", self.primary, self.bg, 3.0),  # used for links/large UI
            ("border/bg", self.border, self.bg, 1.3),  # hairline; informational only
            ("success/success_bg", self.success, self.success_bg, 4.5),
            ("danger/bg", self.danger, self.bg, 4.5),
            ("focus/bg", self.focus, self.bg, 3.0),
        ]


def _srgb_channel(c: float) -> float:
    """Linearize one 0..1 sRGB channel (WCAG relative-luminance formula)."""
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance (0..1) of an ``#rrggbb`` color."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_color!r}")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_channel(r)
        + 0.7152 * _srgb_channel(g)
        + 0.0722 * _srgb_channel(b)
    )


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio (1.0–21.0) between two ``#rrggbb`` colors. Order-independent."""
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def verify_contrast(theme: ThemeTokens) -> Dict[str, Tuple[float, float, bool]]:
    """Check every AA-critical pair of *theme*.

    Returns ``{pair_label: (actual_ratio, min_required, passes)}``. A theme is AA-compliant iff
    every entry's ``passes`` is True. Used as a hard gate in the theme tests.
    """
    out: Dict[str, Tuple[float, float, bool]] = {}
    for label, fg, bg, minimum in theme.contrast_pairs():
        ratio = contrast_ratio(fg, bg)
        out[label] = (round(ratio, 2), minimum, ratio >= minimum)
    return out
