"""kickoff readout --full — the richer, shareable single artifact (status + retrospective + activation).

Guards the HARD invariant that the *default* (non-``--full``) JSON readout stays byte-identical to
``status --json``, and covers the additive ``--full`` behavior across json / md / html (incl. the
HTML XSS gate).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience import schemas

pytestmark = pytest.mark.unit
runner = CliRunner()


def _seed_inbox(tmp_path):
    env = {
        "kind": "vipp-proposal-envelope", "protocol_version": "1.0", "project_id": "p",
        "envelope_seq": 1, "generated_at": "t", "content_checksum": "",
        "proposals": [{"kind": "capture", "params": {"value_path": "conventions.tz", "value": "UTC"}, "id": "P-1", "base_sha": None}],
    }
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env), encoding="utf-8")


# --- (a) the invariant: default JSON readout is still byte-identical to status --json --------------


def test_default_readout_json_still_matches_status(tmp_path):
    _seed_inbox(tmp_path)
    ro = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "json"])
    st = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path), "--json"])
    assert ro.exit_code == 0 and st.exit_code == 0
    assert json.loads(ro.output) == json.loads(st.output)


# --- (b) --full json has the combined schema and nests status/activation/retrospective ------------


def test_full_readout_json_combined_payload(tmp_path):
    _seed_inbox(tmp_path)
    ro = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "json", "--full"])
    assert ro.exit_code == 0
    d = json.loads(ro.output)
    assert d["schema"] == schemas.READOUT == "startd8.kickoff.readout.v1"
    assert d["status"]["schema"] == schemas.STATUS
    assert d["activation"]["schema"] == schemas.ACTIVATION
    assert d["retrospective"]["schema"] == schemas.RETROSPECTIVE
    # The nested status is exactly the standalone status oracle.
    st = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path), "--json"])
    assert d["status"] == json.loads(st.output)


def test_full_readout_json_differs_from_default(tmp_path):
    _seed_inbox(tmp_path)
    default = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "json"])
    full = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "json", "--full"])
    assert json.loads(default.output) != json.loads(full.output)


# --- (c) --full md has journey/decisions + a what's-left/activation section -----------------------


def test_full_readout_md_has_sections(tmp_path):
    _seed_inbox(tmp_path)
    md = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "md", "--full"])
    assert md.exit_code == 0
    body = md.output
    assert "## How it got here" in body
    assert "## What's left" in body


def test_default_readout_md_has_no_full_sections(tmp_path):
    _seed_inbox(tmp_path)
    md = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "md"])
    assert md.exit_code == 0
    assert "How it got here" not in md.output
    assert "What's left" not in md.output


# --- (d) --full html is XSS-safe: a planted <script> renders escaped, and the sections render ------


def _seed_xss_project(tmp_path):
    """Seed a proposal + a project field whose values carry a <script> payload."""
    env = {
        "kind": "vipp-proposal-envelope", "protocol_version": "1.0",
        "project_id": "<script>alert('xss')</script>",
        "envelope_seq": 1, "generated_at": "t", "content_checksum": "",
        "proposals": [{
            "kind": "capture",
            "params": {"value_path": "conventions.tz", "value": "<script>alert(1)</script>"},
            "id": "<script>alert('id')</script>", "base_sha": None,
        }],
    }
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env), encoding="utf-8")


def test_full_readout_html_is_xss_safe(tmp_path):
    _seed_xss_project(tmp_path)
    html_out = runner.invoke(
        kickoff_kernel_app, ["readout", str(tmp_path), "--format", "html", "--full"]
    )
    assert html_out.exit_code == 0
    body = html_out.output
    # No raw executable payload anywhere in the document.
    assert "<script>alert" not in body
    # The payload IS present, but escaped.
    assert "&lt;script&gt;alert" in body
    # The additive full sections rendered.
    assert "<h2>How it got here</h2>" in body
    assert "What&#39;s left" in body
