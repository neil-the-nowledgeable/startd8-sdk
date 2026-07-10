"""kickoff status / proposals / readout-json — the oracle-as-API front doors (A1+A2)."""

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


def test_status_human_and_json(tmp_path):
    _seed_inbox(tmp_path)
    human = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path)])
    assert human.exit_code == 0 and "proposals" in human.output
    js = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path), "--json"])
    assert js.exit_code == 0
    d = json.loads(js.output)
    assert d["schema"] == "startd8.kickoff.status.v1"
    assert len(d["proposals"]) == 1 and d["proposals"][0]["id"] == "P-1"


def test_proposals_list_and_json(tmp_path):
    _seed_inbox(tmp_path)
    lst = runner.invoke(kickoff_kernel_app, ["proposals", str(tmp_path)])
    assert lst.exit_code == 0 and "P-1" in lst.output and "1." in lst.output
    js = runner.invoke(kickoff_kernel_app, ["proposals", str(tmp_path), "--json"])
    assert js.exit_code == 0 and json.loads(js.output)["count"] == 1


def test_proposals_empty_state(tmp_path):
    out = runner.invoke(kickoff_kernel_app, ["proposals", str(tmp_path)])
    assert out.exit_code == 0 and "No proposals" in out.output


def test_readout_json_matches_status(tmp_path):
    _seed_inbox(tmp_path)
    ro = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "json"])
    st = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path), "--json"])
    assert ro.exit_code == 0 and json.loads(ro.output) == json.loads(st.output)


def test_readout_rejects_bad_format(tmp_path):
    out = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "pdf"])
    assert out.exit_code == 2
