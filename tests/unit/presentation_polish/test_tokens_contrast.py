"""Every shipped theme MUST meet WCAG 2.2 AA — accessibility as a deterministic gate (FR-14)."""

import pytest

from startd8.presentation_polish.themes import THEMES, theme_names
from startd8.presentation_polish.tokens import contrast_ratio, verify_contrast


def test_known_contrast_anchors():
    # Sanity-check the formula against WCAG-documented extremes.
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert round(contrast_ratio("#ffffff", "#ffffff"), 1) == 1.0


@pytest.mark.parametrize("theme_name", list(THEMES))
def test_theme_meets_aa(theme_name):
    theme = THEMES[theme_name]
    report = verify_contrast(theme)
    failures = {k: v for k, v in report.items() if not v[2]}
    assert not failures, f"{theme_name} fails AA on: {failures}"


def test_default_theme_present():
    assert "professional" in theme_names()
    assert theme_names()[0] == "professional"  # default first
