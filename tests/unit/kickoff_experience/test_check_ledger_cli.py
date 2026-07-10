"""kickoff check / ledger — the activation gate + transition history (Tier B)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app

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


def test_check_empty_project_is_attention_exit_one(tmp_path):
    out = runner.invoke(kickoff_kernel_app, ["check", str(tmp_path)])
    assert out.exit_code == 1 and "ATTENTION" in out.output
    assert "No kickoff inputs" in out.output


def test_check_json_carries_verdict_and_exit_code(tmp_path):
    _seed_inbox(tmp_path)
    out = runner.invoke(kickoff_kernel_app, ["check", str(tmp_path), "--json"])
    d = json.loads(out.output)
    assert d["schema"] == "startd8.kickoff.activation.v1"
    assert d["exit_code"] == out.exit_code
    assert any(c["key"] == "pending_proposals" for c in d["open"])


def test_check_record_writes_ledger_then_ledger_shows_it(tmp_path):
    _seed_inbox(tmp_path)
    chk = runner.invoke(kickoff_kernel_app, ["check", str(tmp_path), "--record"])
    assert chk.exit_code == 1
    led = runner.invoke(kickoff_kernel_app, ["ledger", str(tmp_path), "--json"])
    d = json.loads(led.output)
    assert d["count"] == 1 and d["entries"][0]["proposals_pending"] == 1


def test_ledger_empty_state(tmp_path):
    out = runner.invoke(kickoff_kernel_app, ["ledger", str(tmp_path)])
    assert out.exit_code == 0 and "No activation history" in out.output
