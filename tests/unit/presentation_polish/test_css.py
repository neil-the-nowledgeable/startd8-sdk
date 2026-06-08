"""Stylesheet + static-setup generators: deterministic, marked, token-driven (FR-9, FR-10, FR-15)."""

from startd8.presentation_polish import render_static_setup, render_stylesheet
from startd8.presentation_polish.css import POLISH_MARKER, POLISH_VERSION
from startd8.presentation_polish.themes import THEMES, get_theme

pytestmark = []


def test_stylesheet_is_deterministic():
    a = render_stylesheet(get_theme("professional"))
    b = render_stylesheet(get_theme("professional"))
    assert a == b  # byte-stable for a given theme (FR-15)


def test_stylesheet_carries_marker_and_theme():
    css = render_stylesheet(get_theme("editorial"))
    assert POLISH_MARKER in css
    assert "theme=editorial" in css
    assert f"v{POLISH_VERSION}" in css


def test_stylesheet_is_token_driven():
    theme = get_theme("professional")
    css = render_stylesheet(theme)
    # tokens surface as CSS custom properties, and the theme's actual values appear
    assert "--color-primary:" in css and theme.primary in css
    assert "--font-sans:" in css
    # rules reference the variables (not hardcoded colors)
    assert "color: var(--color-text)" in css
    assert "background: var(--color-bg)" in css


def test_stylesheet_targets_existing_html_and_a11y():
    css = render_stylesheet(get_theme("minimal"))
    for selector in ["nav", "table", "th, td", ".flash", ".field-error", "button"]:
        assert selector in css, f"missing styling for existing element: {selector}"
    # WCAG baseline present
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert ".sr-only" in css


def test_stylesheet_styles_component_classes():
    css = render_stylesheet(get_theme("professional"))
    for selector in [".app-header", ".brand", ".app-footer", ".badge", ".card", ".skip-link:focus"]:
        assert selector in css, f"missing component style: {selector}"


def test_themes_produce_distinct_stylesheets():
    sheets = {name: render_stylesheet(t) for name, t in THEMES.items()}
    assert len(set(sheets.values())) == len(sheets)  # each theme is visually distinct


def test_static_setup_is_mountable_module():
    src = render_static_setup()
    assert POLISH_MARKER in src
    assert "def mount_static(app" in src
    assert "StaticFiles" in src
    # it must at least parse as Python
    compile(src, "static_setup.py", "exec")
