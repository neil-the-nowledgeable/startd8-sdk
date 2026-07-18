"""M-WV5 — the wireframe-visual HTML shell (FR-WV-1/6/7) + CLI wiring (FR-WV-1).

Guards the delivery layer over the M-WV0 view-model:
  - self-contained (no external assets/CDN) — FR-WV-1;
  - deterministic (same plan ⇒ byte-identical HTML) — FR-WV-6;
  - escape-first embed (a ``<`` in any label can't break out of the JSON container) — FR-WV-7 security;
  - the embedded view-model round-trips to ``compose(plan)`` — provenance;
  - the viewer's expected schema stays in lockstep with the plan JSON contract — FR-WV-7;
  - ``render_to_file`` / ``--html`` write atomically, create the parent dir, degrade advisory.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from startd8.cli_wireframe import wireframe
from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.render import SCHEMA_VERSION
from startd8.wireframe_view import (
    EXPECTED_SCHEMA_VERSION,
    compose,
    render_html,
    render_to_file,
)
from startd8.wireframe_view.view import _embed_json

app = typer.Typer()
app.command()(wireframe)
runner = CliRunner()


def _plan(root: Path):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), authoring=True)


def _embedded_json(html: str) -> dict:
    """Extract + un-escape the view-model embedded in the page."""
    start = html.index('id="plan-data">') + len('id="plan-data">')
    end = html.index("</script>", start)
    blob = html[start:end].strip().replace("\\u003c", "<")
    return json.loads(blob)


def test_html_is_self_contained(golden_root: Path) -> None:
    html = render_html(_plan(golden_root))
    low = html.lower()
    for external in ("http://", "https://", "src=", "<link", "cdn", "//unpkg", "//cdn"):
        assert external not in low, f"HTML must have no external asset: {external!r}"
    assert html.startswith("<!doctype html>")
    assert "<style>" in html and "<script>" in html  # CSS + JS inline


def test_html_is_deterministic(golden_root: Path) -> None:
    plan = _plan(golden_root)
    assert render_html(plan) == render_html(plan)  # no timestamp in the body (FR-WV-6)


def test_embed_is_escape_first() -> None:
    # A `</script>` inside untrusted text must be neutralized on embed (FR-WV-7 security).
    payload = {"label": "evil</script><script>alert(1)"}
    embedded = _embed_json(payload)
    assert "<" not in embedded            # every `<` became <
    assert "\\u003c/script" in embedded


def test_embedded_view_model_roundtrips(golden_root: Path) -> None:
    plan = _plan(golden_root)
    html = render_html(plan)
    assert _embedded_json(html) == compose(plan)  # provenance by construction (the data IS the source)


def test_viewer_schema_tracks_the_contract(golden_root: Path) -> None:
    # If the plan JSON bumps SCHEMA_VERSION, the viewer constant must move with it (else it banners).
    assert EXPECTED_SCHEMA_VERSION == SCHEMA_VERSION
    html = render_html(_plan(golden_root))
    assert f"EXPECTED_SCHEMA = {SCHEMA_VERSION}" in html  # guard baked into the client


def test_render_to_file_creates_parent_and_leaves_no_tmp(tmp_path: Path, golden_root: Path) -> None:
    out = tmp_path / "nested" / "dir" / "preview.html"
    written = render_to_file(_plan(golden_root), out)
    assert written == out and out.is_file()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not (tmp_path / "nested" / "dir" / "preview.html.tmp").exists()


def test_cli_html_flag_writes_preview(tmp_path: Path, golden_root: Path) -> None:
    out = tmp_path / "wf.html"
    result = runner.invoke(app, ["--project", str(golden_root), "--html", str(out), "--no-write"])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("<!doctype html>") and 'id="plan-data"' in body
