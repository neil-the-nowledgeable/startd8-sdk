"""REQ-07 FR-2/FR-3/FR-4/FR-6/FR-7/FR-8/FR-10 — the standalone diff renderer."""

from __future__ import annotations

import re
from pathlib import Path

from startd8.navigator.diff import diff_nodes
from startd8.navigator.models import Node, NodeEvidence, NodeStatus
from startd8.navigator.render_diff import render_navigator_diff_html


def _n(key, does="d", status=NodeStatus.SPEC, **kw):
    return Node(key=key, does=does, status=status, **kw)


def _render(before, after, tmp_path, **kw):
    out = tmp_path / "delta.html"
    render_navigator_diff_html(diff_nodes(before, after, repo_root=tmp_path), out, **kw)
    return out.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# FR-2 self-contained, no CDN, no wireframe import
# --------------------------------------------------------------------------- #
def test_self_contained_no_external_urls(tmp_path):
    html = _render([_n("A")], [_n("A", does="x"), _n("B")], tmp_path)
    assert "<script src" not in html
    assert "cdn" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "<!doctype html>" in html


def test_render_diff_source_has_no_wireframe_view_import():
    src = Path(render_navigator_diff_html.__code__.co_filename)
    text = src.read_text(encoding="utf-8")
    # the only wireframe_view reference allowed is the guarded node_lenses soft-import
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue  # skip docstring / comment prose
        if "wireframe_view" in stripped and "node_lenses" not in stripped:
            raise AssertionError(f"unexpected wireframe_view coupling: {line!r}")


def test_no_reforked_lens_helpers():
    """FR-6 — no re-forked lens logic in the renderer."""
    src = Path(render_navigator_diff_html.__code__.co_filename)
    text = src.read_text(encoding="utf-8")
    assert text.count("_display_label") == 0
    assert text.count("has_jargon") == 0
    assert text.count("_END_USER_ORDER") == 0


# --------------------------------------------------------------------------- #
# FR-2/FR-7 sections + roll-up
# --------------------------------------------------------------------------- #
def test_sections_and_rollup_present(tmp_path):
    html = _render(
        [_n("A"), _n("KEEP")],
        [_n("A", does="new"), _n("KEEP"), _n("NEW")],
        tmp_path,
    )
    assert "<h2>Added</h2>" in html
    assert "<h2>Removed</h2>" in html
    assert "<h2>Changed</h2>" in html
    # roll-up +1 / -0 / ~1
    assert re.search(r">1\s*added<", html.replace("\n", " ")) or "1 added" in html
    assert "1 changed" in html


def test_rollup_counts_match_bucket_sizes(tmp_path):
    before = [_n("A"), _n("B"), _n("DROP")]
    after = [_n("A", does="x"), _n("B"), _n("NEW1"), _n("NEW2")]
    d = diff_nodes(before, after, repo_root=tmp_path)
    out = tmp_path / "d.html"
    render_navigator_diff_html(d, out)
    html = out.read_text(encoding="utf-8")
    assert f"{d.rollup['added']} added" in html
    assert f"{d.rollup['removed']} removed" in html
    assert f"{d.rollup['changed']} changed" in html


# --------------------------------------------------------------------------- #
# FR-3 a11y — colour + glyph + word (greyscale-decodable)
# --------------------------------------------------------------------------- #
def test_greyscale_disambiguation(tmp_path):
    html = _render([_n("A"), _n("DROP")], [_n("A", does="x"), _n("NEW")], tmp_path)
    # strip all CSS colour declarations
    stripped = re.sub(r"color\s*:\s*[^;\"}]+", "", html)
    stripped = re.sub(r"--\w+:\s*#[0-9a-fA-F]+;", "", stripped)
    # each class still disambiguated by its WORD (+ glyph)
    assert "added" in stripped
    assert "removed" in stripped
    assert "changed" in stripped
    assert "+" in stripped and "−" in stripped and "~" in stripped


# --------------------------------------------------------------------------- #
# FR-8 XSS
# --------------------------------------------------------------------------- #
def test_xss_script_in_does_escaped(tmp_path):
    html = _render(
        [_n("A", does="clean")],
        [_n("A", does="<script>alert(1)</script>")],
        tmp_path,
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_xss_javascript_href_in_lives_neutralized(tmp_path):
    evil = NodeEvidence(type="link", ref="javascript:alert(1)")
    html = _render([_n("A")], [_n("A", lives=(evil,))], tmp_path)
    # javascript: is not emitted as a live href
    assert 'href="javascript:' not in html
    # the ref text is still shown, escaped
    assert "javascript:alert(1)" in html.replace("&#", "")  # present as escaped text only


# --------------------------------------------------------------------------- #
# FR-4 transitions + dangling in the HTML
# --------------------------------------------------------------------------- #
def test_transition_and_new_dangling_in_html(tmp_path):
    before = [_n("A", status=NodeStatus.SPEC)]
    after = [
        _n("A", status=NodeStatus.BUILT, lives=(NodeEvidence(type="code", ref="src/ghost.py"),))
    ]
    html = _render(before, after, tmp_path)
    assert "Status transitions" in html
    assert "spec" in html and "built" in html
    assert "New dangling refs" in html
    assert "src/ghost.py" in html


def test_already_dangling_not_shown_as_new(tmp_path):
    ev = NodeEvidence(type="code", ref="src/ghost.py")
    before = [_n("A", lives=(ev,))]
    after = [_n("A", lives=(ev,), does="changed")]
    html = _render(before, after, tmp_path)
    assert "New dangling refs" not in html  # nothing NEW dangling


# --------------------------------------------------------------------------- #
# FR-7 altitude cap
# --------------------------------------------------------------------------- #
def test_max_detail_degrades_to_counts_only(tmp_path):
    before = [_n(f"K{i}", does="o") for i in range(10)]
    after = [_n(f"K{i}", does="n") for i in range(10)]
    html = _render(before, after, tmp_path, max_detail=3)
    assert "diff too large" in html
    assert "10 changed" in html
    # counts-only: no per-field before/after table under the cap
    assert "<table" not in html


def test_small_diff_renders_full_detail(tmp_path):
    html = _render([_n("A", does="o")], [_n("A", does="n")], tmp_path, max_detail=3)
    assert "diff too large" not in html
    assert "<table" in html  # field-level before/after table present


# --------------------------------------------------------------------------- #
# FR-10 determinism
# --------------------------------------------------------------------------- #
def test_render_twice_byte_identical(tmp_path):
    before = [_n("A", does="o"), _n("B"), _n("DROP")]
    after = [_n("A", does="n"), _n("B"), _n("NEW")]
    h1 = _render(before, after, tmp_path)
    h2 = _render(before, after, tmp_path)
    assert h1 == h2


# --------------------------------------------------------------------------- #
# FR-6 lens inheritance (soft) — role changes labelling via project_nodes
# --------------------------------------------------------------------------- #
def test_role_applies_lens_labels(tmp_path):
    # A node whose label the end_user lens would rewrite. We just assert the render still succeeds
    # and honors role=None as raw (byte-identical fallback path).
    before = [_n("KEEP", does="unchanged")]
    after = [_n("KEEP", does="unchanged"), _n("app:MyApp", does="an application")]
    raw = _render(before, after, tmp_path, role=None)
    lensed = _render(before, after, tmp_path, role="end_user")
    # raw path (role=None) shows the raw key; the lensed path routes it through the shared transform
    assert "app:MyApp" in raw
    assert isinstance(lensed, str) and "<!doctype html>" in lensed
    # the end_user lens rewrites "app:MyApp" → an "App name:" label (proves the transform is applied,
    # not re-forked); raw and lensed therefore differ on that row
    assert raw != lensed
