"""REQ-09 — shared-lens adoption in the tree + a11y renderers.

Mirrors the REQ-05 graph-renderer lens tests (test_graph_renderer.py ~201-232): a jargon/structural
node renders HUMANISED under a role and RAW under role=None, for BOTH the tree and the a11y renderer;
a soft-import fallback (transform monkeypatched to None) still exits 0 with raw labels; neither renderer
re-forks the lens helpers (FR-6); and apply_node_lenses is now a WIRED direct consumer (FR-4).
"""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.models import Node, NodeStatus
from startd8.navigator.render_a11y import render_a11y_to_file
from startd8.navigator.render_tree import render_navigator_tree_html

_TREE_SRC = Path(__file__).resolve().parents[3] / "src" / "startd8" / "navigator" / "render_tree.py"
_A11Y_SRC = Path(__file__).resolve().parents[3] / "src" / "startd8" / "navigator" / "render_a11y.py"
_LENS_SRC = (
    Path(__file__).resolve().parents[3]
    / "src" / "startd8" / "wireframe_view" / "node_lenses.py"
)


# A `does` that the shared lens rewrites for end_user ("run: local" → "Runs on your computer") AND
# that carries no false structural collision — the clean lensed≠raw discriminator.
def _tree_node() -> Node:
    return Node(key="svc.run", does="run: local", status=NodeStatus.BUILT)


# A jargon-bearing does ("entities"/"FastAPI") to exercise the technical-flag path alongside a
# structural does that humanises, for the a11y requirement shape (needs kind attributes).
def _req_nodes() -> list:
    obj = Node(
        key="O-1", does="run: local", status=NodeStatus.BUILT,
        attributes={"kind": "objective", "status_key": "goal"},
    )
    fr = Node(
        key="FR-1", does="view: dashboard", status=NodeStatus.BUILT,
        attributes={"kind": "fr", "status_key": "grounded", "serves": "O-1", "verify": "x"},
    )
    fr_jargon = Node(
        key="FR-2", does="export endpoints for the FastAPI entities", status=NodeStatus.BUILT,
        attributes={"kind": "fr", "status_key": "grounded", "serves": "O-1", "verify": "y"},
    )
    return [obj, fr, fr_jargon]


# ---- FR-1: tree renderer lensed vs raw --------------------------------------------

def test_tree_lensed_vs_raw(tmp_path):
    """FR-1: a structural-label node renders HUMANISED under role=end_user and RAW under role=None."""
    node = _tree_node()
    raw = render_navigator_tree_html([node], tmp_path / "raw.html").read_text("utf-8")
    lensed = render_navigator_tree_html(
        [node], tmp_path / "lens.html", role="end_user"
    ).read_text("utf-8")
    # raw path keeps the source does verbatim in the visible does span
    assert '<span class="does">run: local</span>' in raw
    # lensed path humanises the visible does span (the search blob still carries the raw text,
    # which is correct — the lens substitutes only the display label, not the search index)
    assert '<span class="does">Runs on your computer</span>' in lensed
    assert '<span class="does">run: local</span>' not in lensed


def test_tree_role_none_is_byte_identical_to_default(tmp_path):
    """FR-1/FR-5: role=None is byte-for-byte the same as the pre-REQ-09 default (no role kwarg)."""
    node = _tree_node()
    default = render_navigator_tree_html([node], tmp_path / "d.html").read_text("utf-8")
    explicit_none = render_navigator_tree_html(
        [node], tmp_path / "n.html", role=None
    ).read_text("utf-8")
    assert default == explicit_none


def test_tree_soft_import_fallback(tmp_path, monkeypatch):
    """FR-1: with apply_node_lenses import-guarded away, the tree still exits 0 with raw labels."""
    import startd8.navigator.render_tree as rt

    monkeypatch.setattr(rt, "apply_node_lenses", None)
    out = rt.render_navigator_tree_html([_tree_node()], tmp_path / "raw.html", role="end_user")
    html = out.read_text("utf-8")
    assert '<span class="does">run: local</span>' in html   # raw label survives the fallback
    assert "Runs on your computer" not in html


# ---- FR-2: a11y renderer lensed vs raw --------------------------------------------

def test_a11y_lensed_vs_raw(tmp_path):
    """FR-2: a jargon/structural requirement renders HUMANISED under role=end_user, RAW under None."""
    nodes = _req_nodes()
    raw = Path(render_a11y_to_file(nodes, tmp_path / "raw.html")).read_text("utf-8")
    lensed = Path(
        render_a11y_to_file(nodes, tmp_path / "lens.html", role="end_user")
    ).read_text("utf-8")
    # raw keeps the structural does verbatim
    assert "run: local" in raw and "view: dashboard" in raw
    # lensed humanises both, dropping the raw structural text
    assert "Runs on your computer" in lensed
    assert "run: local" not in lensed
    assert "view: dashboard" not in lensed


def test_a11y_role_none_is_byte_identical_to_default(tmp_path):
    """FR-2/FR-5: role=None is byte-for-byte the same as the pre-REQ-09 default (no role kwarg)."""
    nodes = _req_nodes()
    default = Path(render_a11y_to_file(nodes, tmp_path / "d.html")).read_text("utf-8")
    explicit_none = Path(
        render_a11y_to_file(nodes, tmp_path / "n.html", role=None)
    ).read_text("utf-8")
    assert default == explicit_none


def test_a11y_soft_import_fallback(tmp_path, monkeypatch):
    """FR-2: with apply_node_lenses import-guarded away, the a11y view still exits 0 with raw labels."""
    import startd8.navigator.render_a11y as ra

    monkeypatch.setattr(ra, "apply_node_lenses", None)
    out = render_a11y_to_file(_req_nodes(), tmp_path / "raw.html", role="end_user")
    html = Path(out).read_text("utf-8")
    assert "run: local" in html                      # raw label survives
    assert "Runs on your computer" not in html


# ---- FR-6: no re-fork of the lens helpers -----------------------------------------

def test_no_lens_logic_reforked_in_tree_or_a11y():
    """FR-6: neither renderer re-implements the lens helpers (grep == 0 for each token)."""
    for src in (_TREE_SRC, _A11Y_SRC):
        text = src.read_text(encoding="utf-8")
        for token in ("_display_label", "has_jargon", "_END_USER_ORDER"):
            assert text.count(token) == 0, f"{token} must not be re-forked into {src.name}"


# ---- FR-4: apply_node_lenses is now a wired direct consumer ------------------------

def test_apply_node_lenses_is_wired():
    """FR-4: the reachability probe reports apply_node_lenses `wired` (>=1 real call site), not
    `export-only`/`DORMANT` — the tree + a11y renderers are its direct consumers now."""
    import importlib.util

    loop_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "navigator_spec_delivery_loop.py"
    )
    spec = importlib.util.spec_from_file_location("_sdl_probe", loop_path)
    sdl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdl)  # type: ignore[union-attr]

    rows = {r["symbol"]: r for r in sdl.reachability([_LENS_SRC])}
    assert "apply_node_lenses" in rows
    assert rows["apply_node_lenses"]["status"] == "wired", rows["apply_node_lenses"]
    assert rows["apply_node_lenses"]["real"] >= 1
    # no public lens symbol is dormant after adoption
    assert all(r["status"] != "DORMANT" for r in rows.values()), rows
