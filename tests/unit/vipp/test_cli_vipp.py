# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M5 CLI tests for `startd8 vipp` (FR-11): init / negotiate / apply, exit codes, registration."""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from startd8.cli_vipp import vipp_app
from startd8.kickoff_experience import vipp_seam as seam
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction

runner = CliRunner()


def _proj(tmp_path) -> str:
    proj = Path(os.path.realpath(tmp_path))
    (proj / ".startd8" / "vipp").mkdir(parents=True)
    return str(proj)


def _serialize_friction(proj: str) -> None:
    buf = ProposalBuffer()
    buf.add(
        ProposedAction(
            kind="friction",
            params={"friction": "slow", "what_happened": "x", "implication": "y"},
            id="f1",
        )
    )
    seam.serialize_buffer(buf, proj)


def test_init_creates_posting(tmp_path):
    proj = str(Path(os.path.realpath(tmp_path)))
    result = runner.invoke(vipp_app, ["init", "--project-root", proj])
    assert result.exit_code == 0
    assert (Path(proj) / ".startd8/vipp/vipp-context.json").exists()


def test_negotiate_without_inbox_exits_2(tmp_path):
    proj = _proj(tmp_path)
    result = runner.invoke(vipp_app, ["negotiate", "--project-root", proj])
    assert result.exit_code == 2
    assert "no proposals-inbox" in result.output


def test_negotiate_writes_dispositions(tmp_path):
    proj = _proj(tmp_path)
    _serialize_friction(proj)
    result = runner.invoke(vipp_app, ["negotiate", "--project-root", proj])
    assert result.exit_code == 0
    assert "ACCEPT 1" in result.output
    assert (Path(proj) / ".startd8/vipp/dispositions.json").exists()


def test_apply_preview_is_read_only(tmp_path):
    proj = _proj(tmp_path)
    _serialize_friction(proj)
    runner.invoke(vipp_app, ["negotiate", "--project-root", proj])

    result = runner.invoke(vipp_app, ["apply", "--project-root", proj])  # no --apply
    assert result.exit_code == 0
    assert "preview" in result.output.lower()
    assert seam.read_inbox(proj) is not None  # nothing consumed — still pending


def test_apply_with_apply_yes_writes_and_consumes(tmp_path):
    proj = _proj(tmp_path)
    _serialize_friction(proj)
    runner.invoke(vipp_app, ["negotiate", "--project-root", proj])

    result = runner.invoke(
        vipp_app, ["apply", "--apply", "--yes", "--project-root", proj]
    )
    assert result.exit_code == 0
    assert "wrote 1/1" in result.output
    assert seam.read_inbox(proj) is None  # inbox consumed
    assert (Path(proj) / "concierge-friction.jsonl").exists()  # real write


def test_apply_stale_exits_3(tmp_path):
    proj = _proj(tmp_path)
    _serialize_friction(proj)
    runner.invoke(
        vipp_app, ["negotiate", "--project-root", proj]
    )  # dispositions pin seq 1

    seam.shred_inbox(proj)
    _serialize_friction(proj)  # inbox now seq 2; dispositions still seq 1

    result = runner.invoke(
        vipp_app, ["apply", "--apply", "--yes", "--project-root", proj]
    )
    assert result.exit_code == 3
    assert "stale" in result.output.lower()


def test_apply_without_dispositions_exits_2(tmp_path):
    proj = _proj(tmp_path)
    result = runner.invoke(vipp_app, ["apply", "--project-root", proj])
    assert result.exit_code == 2
    assert "no dispositions" in result.output


def test_vipp_is_registered_on_the_root_cli():
    from startd8.cli import app

    result = runner.invoke(app, ["vipp", "--help"])
    assert result.exit_code == 0
    assert "negotiate" in result.output and "apply" in result.output
