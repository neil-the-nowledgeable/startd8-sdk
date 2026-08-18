"""REQ-navigator-cross-topology-links (Move 1) — FR-keyed regression pins.

The cross-topology links are an authored, opt-in, byte-identical-off affordance on the full-page
requirement view. These pin: the opt-in embed (FR-1), the client-side render + {key} substitution
(FR-2), the CLI authoring path (FR-3), no-fabrication/verbatim (FR-4), and byte-identity (FR-6).
"""

from __future__ import annotations

import re
import tempfile

import pytest
from typer.testing import CliRunner

from startd8.navigator.cli_navigator import navigator_app
from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    DEFINITION_REGISTRY,
    resolve,
    to_render_profile,
)
from startd8.wireframe_view import render_html
from tests.unit.wireframe.test_render_profile import _plan

pytestmark = pytest.mark.unit

runner = CliRunner()


def _profile():
    return to_render_profile(resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY))


# ── FR-1: opt-in embed, byte-identical off ─────────────────────────────────────────────────────────


def test_fr1_cross_links_embedded_only_under_profile_and_nonempty():
    P = _profile()
    with_xl = render_html(_plan(), profile=P, cross_links={"a11y": "r.a11y.html#{key}"})
    assert re.search(r'"cross_links"\s*:', with_xl)
    # absent map (even under a profile) → not embedded
    assert '"cross_links"' not in render_html(_plan(), profile=P)
    assert '"cross_links"' not in render_html(_plan(), profile=P, cross_links={})


# ── FR-2: the client render + {key} substitution ───────────────────────────────────────────────────


def test_fr2_full_view_renders_from_cross_links_and_substitutes_key():
    P = _profile()
    h = render_html(_plan(), profile=P, cross_links={"a11y": "r.a11y.html#{key}"})
    band = h.split("function buildFullView")[1].split("function findItemByKey")[0]
    assert "payload.cross_links" in band
    assert "fv-xlinks" in band
    # {key} is substituted per requirement (client-side), and the topology label + url are emitted.
    assert re.search(r"replace\(/\\\{key\\\}/g", band)


def test_fr2_no_cross_links_no_row():
    # A profile without a cross_links map → no cross-topology row is emitted at runtime (the JS guards on it).
    h = render_html(_plan(), profile=_profile())
    band = h.split("function buildFullView")[1].split("function findItemByKey")[0]
    # the guard is present so an absent map renders nothing
    assert "payload.cross_links)||null" in band


# ── FR-3: CLI authoring ────────────────────────────────────────────────────────────────────────────


def test_fr3_cli_authors_cross_links():
    out = tempfile.mktemp(suffix=".html")
    res = runner.invoke(
        navigator_app,
        [
            "build",
            "--source",
            "frame",
            "--format",
            "html",
            "--renderer",
            "wireframe",
            "--cross-link",
            "a11y=r.a11y.html#{key}",
            "--cross-link",
            "graph=g.html#{key}",
            "--out",
            out,
        ],
    )
    assert res.exit_code == 0, res.output
    h = open(out, encoding="utf-8").read()
    assert '"cross_links"' in h
    assert "r.a11y.html#{key}" in h and "g.html#{key}" in h


# ── FR-4: no fabrication / verbatim + validation ────────────────────────────────────────────────────


def test_fr4_url_is_verbatim_no_fabrication():
    P = _profile()
    h = render_html(_plan(), profile=P, cross_links={"x": "SENTINEL/{key}.html"})
    # the authored template is embedded verbatim (the navigator invents no basename/anchor).
    assert "SENTINEL/{key}.html" in h
    # only the ONE configured topology is present — nothing auto-added for graph/index/diff.
    m = re.search(r'"cross_links"\s*:\s*(\{[^}]*\})', h)
    assert m and "graph" not in m.group(1) and "index" not in m.group(1)


def test_fr4_malformed_cross_link_errors():
    res = runner.invoke(
        navigator_app,
        [
            "build",
            "--source",
            "frame",
            "--format",
            "html",
            "--cross-link",
            "no-equals-sign",
            "--out",
            tempfile.mktemp(suffix=".html"),
        ],
    )
    assert res.exit_code != 0


# ── FR-6: byte-identity ──────────────────────────────────────────────────────────────────────────────


def test_fr6_app_scaffold_byte_identical():
    assert render_html(_plan()) == render_html(_plan(), profile=None)
