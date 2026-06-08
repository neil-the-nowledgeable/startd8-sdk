"""The {% import %} seam: theme partials + backend base.html hooks (FR-12 macros, FR-13 shell)."""

import jinja2
import pytest

from startd8.backend_codegen.htmx_generator import render_base_template
from startd8.presentation_polish import (
    render_components_macros,
    render_footer_partial,
    render_head_extra,
    render_header_partial,
)
from startd8.presentation_polish.css import POLISH_MARKER

pytestmark = []

SCHEMA = "model Note {\n  id String @id\n  title String\n}\n"


def test_base_template_carries_tolerant_theme_hooks():
    base = render_base_template(SCHEMA)
    # the three seam hooks, all `ignore missing` (no-op until polish fills them)
    assert '{% include "theme/_head_extra.html" ignore missing %}' in base
    assert '{% include "theme/_header.html" ignore missing %}' in base
    assert '{% include "theme/_footer.html" ignore missing %}' in base
    # skip-link target added to main for accessibility
    assert 'id="main-content"' in base


def test_partials_carry_marker():
    for render in (
        render_components_macros,
        render_header_partial,
        render_footer_partial,
        render_head_extra,
    ):
        assert POLISH_MARKER in render()


def test_header_and_footer_import_the_macro_lib():
    assert '{% import "theme/_components.html" as ui %}' in render_header_partial()
    assert '{% import "theme/_components.html" as ui %}' in render_footer_partial()


def test_partials_render_through_jinja_with_the_macro_lib():
    """The seam actually works: a loader with the partials resolves the import and renders markup."""
    env = jinja2.Environment(
        loader=jinja2.DictLoader(
            {
                "theme/_components.html": render_components_macros(),
                "theme/_header.html": render_header_partial(),
                "theme/_footer.html": render_footer_partial(),
            }
        )
    )
    header = env.get_template("theme/_header.html").render()
    footer = env.get_template("theme/_footer.html").render()
    assert 'class="app-header"' in header and 'class="brand"' in header
    assert "skip-link" in header  # accessibility skip-link present
    assert 'class="app-footer"' in footer and "startd8" in footer


def test_macro_lib_is_valid_jinja():
    # parsing the macro library must not raise (it's pure macro defs)
    jinja2.Environment().parse(render_components_macros())
