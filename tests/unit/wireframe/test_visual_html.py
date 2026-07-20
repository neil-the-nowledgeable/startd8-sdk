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
    payload = _embedded_json(render_html(plan))  # QW-1: {default, variants} — all audiences embedded
    assert payload["default"] == "end_user|intermediate"                       # default shown (FR-AUD-2)
    assert payload["variants"]["end_user|intermediate"] == compose(plan, role="end_user", fluency="intermediate")
    assert payload["variants"]["architect|intermediate"] == compose(plan, role="architect")
    assert payload["variants"]["end_user|beginner"] == compose(plan, role="end_user", fluency="beginner")


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


def _end_user_rendered_strings(vm: dict) -> list:
    """Every string the end_user template actually renders — hidden raw detail and `technical` items
    (which the template drops for end_user) are excluded, mirroring the renderer."""
    s = vm["summary"]
    out = list(s.get("meta", [])) + list(s.get("steps", [])) + [
        s.get("headline", ""), s.get("lead", ""), s.get("closing", ""),
        s.get("plain_status", ""), s.get("plain_shape", ""), s.get("plain_content", ""),
        s.get("plain_ready", ""), s.get("why", ""), s.get("do", ""),
    ]
    for sec in vm["sections"]:
        out.append(sec["title"])
        out += list(sec.get("need_items", []))
        n = sec.get("narration") or {}
        out += [n.get(k) or "" for k in ("what", "wont", "need", "do", "next")]
        for it in sec["items"]:
            if it.get("technical"):
                continue                     # hidden from the end_user render (R1-F7)
            out.append(it["label"])          # detail is hidden for end_user, so it is NOT rendered
            m = it.get("mockup")
            if m:
                out.append(m.get("entity", ""))
                out += list(m.get("shown", []))
                out += list(m.get("columns", []))  # LH-1 list mockup columns
                out += list(m.get("omitted", {}).get("server_managed", []))
                out += list(m.get("omitted", {}).get("owned", []))
    return out


def test_end_user_rendered_surface_has_no_banned_jargon(golden_root: Path) -> None:
    """R1-F7 — the FR-AUD-C1 jargon ban as a deterministic acceptance check, using the composer's own
    single-source matcher over exactly what the end_user template renders."""
    from startd8.wireframe_view import compose
    from startd8.wireframe_view.compose import has_jargon

    vm = compose(_plan(golden_root), role="end_user", fluency="intermediate")
    for text in _end_user_rendered_strings(vm):
        assert not has_jargon(text), f"FR-AUD-C1 banned jargon reached the end_user surface: {text!r}"


def test_end_user_surface_has_no_process_meta(golden_root: Path) -> None:
    """R2-F1 — the end_user surface must not narrate the tool/process: no filesystem paths, no
    build-pipeline framing. The app's own NAME is shown instead of its path."""
    from startd8.wireframe_view import compose

    vm = compose(_plan(golden_root), role="end_user", fluency="intermediate")
    # include every rendered item label too (structural labels are worded plain / path-free)
    strings = _end_user_rendered_strings(vm) + [vm.get("app_name", "")]
    for sec in vm["sections"]:
        strings += [it["label"] for it in sec["items"] if not it.get("technical")]
    blob = " ".join(strings)
    assert "/Users/" not in blob and vm["project_root"] not in blob    # no absolute path
    for frag in (".md", ".py", ".yaml", "app/", "prompts/", "templates/"):  # no relative filesystem path (R2-F1)
        assert frag not in blob, f"filesystem path fragment reached the end_user surface: {frag!r}"
    low = blob.lower()
    for phrase in ("about to build", "line of code", "generat", "pipeline", "deterministic", "$0", "no llm"):
        assert phrase not in low, f"process-meta phrase reached the end_user surface: {phrase!r}"
    # app name is shown (not a path); project_root stays in the embed for provenance only
    assert vm["app_name"] and "/" not in vm["app_name"]


def test_cli_view_json_emits_the_view_model(golden_root: Path) -> None:
    """LH-2: --view-json emits the composed view-model as parseable JSON, honoring --audience/--fluency."""
    import json

    from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
    from startd8.wireframe_view import compose

    # the CLI builds with authoring=False by default — compare against the same
    plan = build_wireframe_plan(load_assembly_inputs(project_root=golden_root), authoring=False)
    r = runner.invoke(app, ["--project", str(golden_root), "--view-json",
                            "--audience", "end_user", "--fluency", "beginner"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == compose(plan, role="end_user", fluency="beginner")
    # a different audience yields a different (architect) view-model
    ra = runner.invoke(app, ["--project", str(golden_root), "--view-json", "--audience", "architect"])
    assert json.loads(ra.stdout)["audience"] == {"role": "architect", "fluency": "intermediate"}


def test_signoff_scaffold_is_present_and_offline(golden_root: Path) -> None:
    """EC-2 — the approve/flag/annotate sign-off is wired, persists client-side (localStorage, no server),
    and exports a JSON artifact. Deterministic + self-contained is covered by the tests above; here we
    guard the scaffold so a regression that drops it is caught."""
    html = render_html(_plan(golden_root))
    # per-section controls + summary bar + header marker
    for hook in (".signoff", "so-ok", "so-flag", "so-note", 'id="signbar"', "sig-mark", "signRow("):
        assert hook in html, f"EC-2 sign-off hook missing: {hook!r}"
    # persisted client-side under an app-scoped key, never a network call
    assert "startd8:wf-signoff:" in html and "localStorage" in html
    # export produces a downloadable JSON artifact (feeds the kickoff loop), no external asset
    assert "Export sign-off" in html and "signoff.json" in html and "application/json" in html
    assert "http://" not in html.lower() and "https://" not in html.lower()


def test_cli_html_flag_writes_preview(tmp_path: Path, golden_root: Path) -> None:
    out = tmp_path / "wf.html"
    result = runner.invoke(app, ["--project", str(golden_root), "--html", str(out), "--no-write"])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("<!doctype html>") and 'id="plan-data"' in body
