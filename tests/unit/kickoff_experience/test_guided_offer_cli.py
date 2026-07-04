"""GE-M0 — the guided offer at the kernel `assess` surface (FR-GE-1 byte-identity).

Two guarantees at the CLI seam:

* **Byte-identity (FR-GE-1):** the kernel `assess` stdout is byte-identical whether or not a
  `guided:` preference is set, and whether guided is off or unset — the offer only ever adds a
  line on *stderr*, and only when interactive. `--json` stdout is never touched.
* **Placement:** when the offer does surface (interactive), it lands on stderr, not stdout.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

import startd8.cli_concierge as cli_concierge
from startd8.cli_concierge import concierge_app

runner = CliRunner()


def _make_project(tmp_path, *, guided=None):
    root = tmp_path / "proj"
    inputs = root / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\nCoverage\n", encoding="utf-8"
    )
    body = "domain: build-preferences\n"
    if guided is not None:
        body += f"guided: {guided}\n"
    (inputs / "build-preferences.yaml").write_text(body, encoding="utf-8")
    return root


def test_assess_json_byte_identical_regardless_of_guided(tmp_path):
    """FR-GE-1: --json stdout is byte-identical across guided unset / off / on.

    The three variants reuse the SAME project dir (rewritten between runs) so the only difference
    is the `guided:` line in build-preferences.yaml — the project_root path is invariant.
    """
    root = _make_project(tmp_path, guided=None)
    outs = []
    for guided in (None, "false", "true"):
        _make_project(tmp_path, guided=guided)  # rewrite prefs in place; same root path
        result = runner.invoke(concierge_app, ["assess", str(root), "--json"])
        assert result.exit_code == 0
        outs.append(result.stdout)
    assert outs[0] == outs[1] == outs[2]


def test_assess_stdout_byte_identical_across_guided_states(tmp_path):
    """FR-GE-1: human-readable stdout unchanged by the guided preference (offer is stderr-only)."""
    root = _make_project(tmp_path, guided=None)
    outs = []
    for guided in (None, "false", "true"):
        _make_project(tmp_path, guided=guided)  # same root path; only prefs change
        result = runner.invoke(concierge_app, ["assess", str(root)])
        assert result.exit_code == 0
        outs.append(result.stdout)
    assert outs[0] == outs[1] == outs[2]
    # under CliRunner stdout is not a TTY ⇒ offer suppressed; the tip never leaks into stdout
    assert "guided kickoff" not in outs[0]


def test_offer_lands_on_stderr_not_stdout_when_interactive(tmp_path, monkeypatch):
    """When interactive + a signal fires, the one offer line goes to STDERR, never stdout."""
    captured = {"stderr": []}
    monkeypatch.setattr(
        cli_concierge._stderr_console, "print", lambda *a, **k: captured["stderr"].append(a)
    )

    # Force interactive so the routing seam emits; greenfield-blank project ⇒ a quiet offer.
    class _Term:
        is_terminal = True

    monkeypatch.setattr(cli_concierge, "console", _Term(), raising=False)
    # _Term has no .print; the assess body already ran and returned `result` — call the seam directly.
    root = _make_project(tmp_path, guided=None)
    assess_payload = {"kickoff_inputs": {"domains": {"stakeholders": {"status": "absent"}}}}
    cli_concierge._maybe_offer_guided(root, assess=assess_payload)

    assert captured["stderr"], "expected an offer line on stderr for a greenfield-blank interactive run"
    joined = " ".join(str(a) for a in captured["stderr"])
    assert "guided kickoff" in joined


def test_offer_seam_is_defensive(tmp_path, monkeypatch):
    """A failure inside the seam must never raise into the kernel path (courtesy-only)."""
    import startd8.kickoff_experience.guided_routing as gr

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(gr, "decide_guided_routing", _boom)
    # Should swallow the error and return None, not raise.
    cli_concierge._maybe_offer_guided(tmp_path, assess={"kickoff_inputs": {"domains": {}}})
