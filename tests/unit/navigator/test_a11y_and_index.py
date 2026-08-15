"""A11y requirements renderer + corpus index (REQ-03) — standalone, a11y contract, port hazards, XSS.

Mirrors tests/unit/navigator/test_tree_renderer.py (the REQ-02 precedent)."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.render_a11y import (
    ReqView,
    check_no_bleed,
    render_a11y_to_file,
    render_html,
)
from startd8.navigator.render_index import _req_summary, render_index_to_file
from startd8.navigator.sources_requirements import nodes_from_requirements

FIXTURE = Path(__file__).parent / "fixtures" / "REQ-fixture-minimal.md"
RUNNER = CliRunner()

_A11Y_SRC = Path("src/startd8/navigator/render_a11y.py")
_INDEX_SRC = Path("src/startd8/navigator/render_index.py")


# ---- FR-1 / round-trip: sources_requirements output feeds render_a11y --------
def test_a11y_renders_requirements_nodes(tmp_path):
    """FR-1: nodes_from_requirements → ReqView → render_html produces per-FR rows."""
    nodes = nodes_from_requirements(FIXTURE)
    out = render_a11y_to_file(nodes, tmp_path / "a.html", title="Fixture")
    html = Path(out).read_text(encoding="utf-8")
    assert "FR-1" in html and "FR-2" in html and "FR-3" in html
    assert "Capabilities" in html


# ---- FR-4: accessibility contract -------------------------------------------
def test_a11y_contract_landmarks_headings_disclosures(tmp_path):
    """FR-4: one <main>, a skip-link, ordered headings, aria on disclosures, nav landmark."""
    nodes = nodes_from_requirements(FIXTURE)
    html = Path(render_a11y_to_file(nodes, tmp_path / "a.html", title="Fixture")).read_text("utf-8")
    assert html.count("<main") == 1                        # exactly one main landmark
    assert 'class="skip-link"' in html                     # skip link present
    assert '<nav class="toc"' in html and 'aria-label="Sections"' in html
    # heading order: exactly one h1, then h1 appears before any h2/h3
    assert html.count("<h1>") == 1
    h1 = html.index("<h1>")
    for tag in ("<h2", "<h3"):
        if tag in html:
            assert html.index(tag) > h1
    # disclosures are keyboard-reachable native <details>/<summary> with aria-hidden decorative glyphs
    assert "<details" in html and "<summary" in html
    assert 'aria-hidden="true"' in html                    # decorative glyphs/icons hidden from SR


def test_a11y_status_not_colour_only(tmp_path):
    """FR-4: status is conveyed by text+glyph, never colour alone (WCAG 1.4.1)."""
    nodes = nodes_from_requirements(FIXTURE)
    html = Path(render_a11y_to_file(nodes, tmp_path / "a.html")).read_text("utf-8")
    # every status pill carries a word label
    assert '<span class="tag' in html
    assert "spec" in html or "unknown" in html or "grounded" in html
    # the legend spells out the glyph→meaning mapping in words
    assert "needs attention" in html and "your call" in html


# ---- FR-5 / FR-1: standalone (no wireframe import) --------------------------
def test_render_a11y_is_standalone_no_wireframe_import():
    """FR-5: the a11y renderer must not import wireframe (check import lines, not prose)."""
    src = _A11Y_SRC.read_text(encoding="utf-8")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert not any("wireframe" in ln for ln in import_lines), "a11y renderer must not import wireframe"


def test_render_index_is_standalone_no_wireframe_import():
    """FR-5: the corpus index must not import wireframe either."""
    src = _INDEX_SRC.read_text(encoding="utf-8")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert not any("wireframe" in ln for ln in import_lines), "index must not import wireframe"


# ---- FR-6: single-live-def gate (port hazard — no shadowed dupes) -----------
def test_no_shadowed_dead_defs_a11y():
    """FR-6: every ported top-level a11y symbol is defined exactly once (CC dead-code hazard)."""
    src = _A11Y_SRC.read_text(encoding="utf-8")
    assert len(re.findall(r"^class ReqView\b", src, re.M)) == 1, "ReqView defined more than once"
    for sym in ("render_html", "render_a11y_to_file", "esc", "status_label",
                "_evidence_lines", "_row", "render_text", "by_kind", "check_no_bleed"):
        assert src.count(f"def {sym}(") == 1, f"{sym} defined more than once (dead-code hazard)"


def test_no_shadowed_dead_defs_index():
    """FR-6: every ported top-level index symbol is defined exactly once."""
    src = _INDEX_SRC.read_text(encoding="utf-8")
    for sym in ("render_index_to_file", "_doc_title", "_req_summary", "_render_leaf"):
        assert src.count(f"def {sym}(") == 1, f"{sym} defined more than once (dead-code hazard)"


# ---- FR-6: XSS mitigations (decision-1 — REQ-02 _safe_href/_safe_color) -----
def test_xss_href_in_evidence_not_a_live_link(tmp_path):
    """FR-6: a javascript: ref in Lives evidence must never render as a live href."""
    from startd8.navigator.models import Node, NodeEvidence, NodeStatus

    n = Node(key="FR-9", does="evil", status=NodeStatus.SPEC,
             lives=(NodeEvidence(type="link", ref="javascript:alert(1)", note="authored"),),
             attributes={"kind": "fr", "status_key": "spec"})
    html = render_html(ReqView([n]))
    assert 'href="javascript:' not in html                  # never a live href


def test_xss_breadcrumb_href_sanitized(tmp_path):
    """FR-6: a javascript: up_href (breadcrumb) is dropped, not rendered as a live href."""
    from startd8.navigator.models import Node, NodeStatus

    n = Node(key="FR-1", does="d", status=NodeStatus.SPEC, attributes={"kind": "fr"})
    html = render_html(ReqView([n]), up_href="javascript:alert(1)", up_label="back")
    assert 'href="javascript:' not in html


def test_xss_injecting_text_is_escaped(tmp_path):
    """FR-6: authored text with markup is escaped, not an unescaped sink."""
    from startd8.navigator.models import Node, NodeStatus

    n = Node(key="FR-1", does="<script>alert(1)</script>", status=NodeStatus.SPEC,
             attributes={"kind": "fr", "verify": "<img src=x onerror=alert(1)>",
                         "status_key": "spec"})
    html = render_html(ReqView([n]))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "onerror=alert" not in html or "&lt;img" in html


# ---- FR-6: no wireframe summary-chrome tell (check_no_bleed) ----------------
def test_check_no_bleed_passes_on_a11y_output(tmp_path):
    """FR-6: the a11y shell carries no wireframe summary-chrome tell (Entities/CRUD/0/0/0)."""
    nodes = nodes_from_requirements(FIXTURE)
    html = Path(render_a11y_to_file(nodes, tmp_path / "a.html")).read_text("utf-8")
    verdict = check_no_bleed(html)
    assert verdict["pass"], verdict
    assert verdict["leaked_tokens"] == []
    assert not verdict["zero_shape_row"]


def test_check_no_bleed_flags_a_wireframe_tell():
    """FR-6: check_no_bleed is a real guard — it FAILS on wireframe summary chrome / a 0/0/0 row."""
    assert not check_no_bleed("<p>Entities 0 / 0 / 0</p>")["pass"]
    assert "Entities" in check_no_bleed("<p>Entities</p>")["leaked_tokens"]


# ---- FR-2: corpus index drills to N leaves ----------------------------------
def _corpus(tmp: Path, n: int = 3) -> Path:
    """Write a small corpus of parseable REQ-*.md docs + one unparseable doc."""
    d = tmp / "corpus"
    d.mkdir()
    body = FIXTURE.read_text(encoding="utf-8")
    for i in range(1, n + 1):
        (d / f"REQ-0{i}-fixture.md").write_text(
            body.replace("# Fixture REQ", f"# Fixture REQ {i}"), encoding="utf-8"
        )
    # a doc that yields no det-req sections → degrades to a non-linked span
    (d / "REQ-99-empty.md").write_text("# Empty REQ\n\nNo sections here.\n", encoding="utf-8")
    return d


def test_index_drills_to_n_leaves(tmp_path):
    """FR-2: the index writes an index page + one a11y leaf per parseable doc with resolving hrefs."""
    d = _corpus(tmp_path, n=3)
    out = tmp_path / "idx" / "index.html"
    render_index_to_file(d, out, title="Corpus")
    html = out.read_text(encoding="utf-8")
    leaves = out.parent / "leaves"
    leaf_files = sorted(leaves.glob("*.html"))
    assert len(leaf_files) == 3                             # one leaf per parseable doc
    # every leaf href in the index resolves to a real file on disk
    for m in re.finditer(r'href="(leaves/[^"]+)"', html):
        assert (out.parent / m.group(1)).is_file(), m.group(1)
    # each leaf carries a breadcrumb back to the index (round-trippable, not a dead-end)
    for lf in leaf_files:
        assert "../index.html" in lf.read_text(encoding="utf-8")


def test_index_unparseable_doc_degrades_gracefully(tmp_path):
    """FR-2: an unparseable/empty doc renders as a non-linked span, never breaking the index."""
    d = _corpus(tmp_path, n=2)
    out = tmp_path / "idx" / "index.html"
    render_index_to_file(d, out, title="Corpus")
    # the empty doc yields an 'info' row with no det-req sections and NO leaf link
    summ = _req_summary(d / "REQ-99-empty.md")
    assert summ["health"] == "info"
    leaves = out.parent / "leaves"
    assert not (leaves / "REQ-99-empty.html").exists()      # no dead leaf generated
    html = out.read_text(encoding="utf-8")
    assert "Empty REQ" in html                              # still listed, as a plain span


def test_index_has_one_main_and_skip_link(tmp_path):
    """FR-4 (index shares the a11y shell): one <main>, a skip-link."""
    d = _corpus(tmp_path, n=1)
    out = tmp_path / "idx" / "index.html"
    render_index_to_file(d, out)
    html = out.read_text(encoding="utf-8")
    assert html.count("<main") == 1
    assert 'class="skip-link"' in html


# ---- FR-3: CLI seam (additive; html/json unchanged) -------------------------
def test_cli_build_format_a11y(tmp_path):
    """FR-3: `build --format a11y` routes to the a11y renderer and requires --out."""
    out = tmp_path / "a.html"
    result = RUNNER.invoke(
        app,
        ["navigator", "build", "--source", "requirements", "--requirements", str(FIXTURE),
         "--format", "a11y", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "FR-1" in html
    assert html.count("<main") == 1


def test_cli_build_a11y_requires_out():
    """FR-3: `--format a11y` without --out errors (mirrors html)."""
    result = RUNNER.invoke(
        app,
        ["navigator", "build", "--source", "requirements", "--requirements", str(FIXTURE),
         "--format", "a11y"],
    )
    assert result.exit_code != 0
    assert "--out is required" in result.output


def test_cli_index_command(tmp_path):
    """FR-3: `navigator index --dir --out` writes an index + leaves."""
    d = _corpus(tmp_path, n=2)
    out = tmp_path / "idx" / "index.html"
    result = RUNNER.invoke(app, ["navigator", "index", "--dir", str(d), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert (out.parent / "leaves").is_dir()


def test_cli_index_listed_in_help():
    """FR-3: `navigator --help` lists the new index command."""
    result = RUNNER.invoke(app, ["navigator", "--help"])
    assert result.exit_code == 0
    assert "index" in result.output


def test_cli_build_html_json_unchanged(tmp_path):
    """FR-3 back-compat: `--format html` and `--format json` still work."""
    for fmt, ext in (("html", "html"), ("json", "json")):
        out = tmp_path / f"o.{ext}"
        result = RUNNER.invoke(
            app,
            ["navigator", "build", "--source", "requirements", "--requirements", str(FIXTURE),
             "--format", fmt, "--out", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert out.is_file()
