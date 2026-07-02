# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""`startd8 panel import` CLI tests (FR-6): exit-code contract + clobber guard."""

from __future__ import annotations

from typer.testing import CliRunner

from startd8.cli_panel import panel_app
from startd8.stakeholder_panel.ingest import GENERATED_MARKER

runner = CliRunner()

_SRC = (
    "roles:\n"
    "  - key: SRE\n"
    "    label: Site Reliability Engineer\n"
    "    lens: operability\n"
    "    coverage: {scope: per_cell, mandatory: true}\n"
    "    rubric:\n"
    "      - {name: operability, description: 'prod-ready?'}\n"
)


def _src_file(tmp_path, text=_SRC, name="reviewer_roles.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_import_writes_a_valid_roster_then_list_works(tmp_path):
    src = _src_file(tmp_path)
    out = tmp_path / "roster.yaml"
    result = runner.invoke(
        panel_app, ["import", str(src), "--format", "role-rubric", "--out", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    written = out.read_text(encoding="utf-8")
    assert written.startswith(GENERATED_MARKER)
    # The imported roster is loadable by the panel: `list` on its project succeeds.
    project = tmp_path / "proj"
    dest = project / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
    dest.parent.mkdir(parents=True)
    dest.write_text(written, encoding="utf-8")
    listed = runner.invoke(panel_app, ["list", str(project)])
    assert listed.exit_code == 0 and "sre" in listed.stdout


def test_import_default_out_is_project_roster(tmp_path):
    src = _src_file(tmp_path)
    result = runner.invoke(
        panel_app,
        ["import", str(src), "--format", "role-rubric", "--project", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert (tmp_path / "docs" / "kickoff" / "inputs" / "stakeholders.yaml").is_file()


def test_unknown_format_exits_2(tmp_path):
    result = runner.invoke(
        panel_app, ["import", str(_src_file(tmp_path)), "--format", "bogus"]
    )
    assert result.exit_code == 2 and "bogus" in result.stdout


def test_malformed_source_exits_3(tmp_path):
    bad = _src_file(tmp_path, text="- not a mapping\n")
    result = runner.invoke(
        panel_app,
        [
            "import",
            str(bad),
            "--format",
            "role-rubric",
            "--out",
            str(tmp_path / "o.yaml"),
        ],
    )
    assert result.exit_code == 3


def test_unreadable_source_exits_3(tmp_path):
    missing = tmp_path / "nope.yaml"
    result = runner.invoke(
        panel_app, ["import", str(missing), "--format", "role-rubric"]
    )
    assert result.exit_code == 3


def test_clobber_generated_file_needs_force(tmp_path):
    src = _src_file(tmp_path)
    out = tmp_path / "roster.yaml"
    runner.invoke(
        panel_app, ["import", str(src), "--format", "role-rubric", "--out", str(out)]
    )
    # Second import onto the (now GENERATED) file: refused without --force...
    again = runner.invoke(
        panel_app, ["import", str(src), "--format", "role-rubric", "--out", str(out)]
    )
    assert again.exit_code == 5
    # ...succeeds with --force.
    forced = runner.invoke(
        panel_app,
        ["import", str(src), "--format", "role-rubric", "--out", str(out), "--force"],
    )
    assert forced.exit_code == 0


def test_dest_is_a_directory_exits_5_not_traceback(tmp_path):
    # Regression (review MED): a directory at the out path must exit cleanly, not raise IsADirectoryError.
    src = _src_file(tmp_path)
    out_dir = tmp_path / "a-directory"
    out_dir.mkdir()
    result = runner.invoke(
        panel_app,
        ["import", str(src), "--format", "role-rubric", "--out", str(out_dir)],
    )
    # Normalize Rich's word-wrap before matching the message.
    assert result.exit_code == 5
    assert "not a regular file" in " ".join(result.stdout.split())


def test_clobber_hand_authored_warns_under_force(tmp_path):
    src = _src_file(tmp_path)
    out = tmp_path / "hand.yaml"
    out.write_text(
        "domain: stakeholders\npersonas: []\n", encoding="utf-8"
    )  # no GENERATED header
    refused = runner.invoke(
        panel_app, ["import", str(src), "--format", "role-rubric", "--out", str(out)]
    )
    assert refused.exit_code == 5 and "hand-authored" in refused.stdout
    forced = runner.invoke(
        panel_app,
        ["import", str(src), "--format", "role-rubric", "--out", str(out), "--force"],
    )
    assert (
        forced.exit_code == 0 and "hand-authored" in forced.stdout
    )  # warned, then wrote
