# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""`startd8 workflow describe` must render input schemas with list-valued `type`.

Regression: convergent-review has Optional fields whose JSON-Schema `type` is a list
(e.g. ["string", "null"]); rich's Table.add_row crashed on the non-string cell.
"""

from typer.testing import CliRunner

from startd8.cli_workflow import workflow_app

runner = CliRunner()


def test_describe_convergent_review_renders_list_typed_schema():
    result = runner.invoke(workflow_app, ["describe", "convergent-review"])
    assert result.exit_code == 0, result.stdout
    # the panel + inputs table rendered (no traceback)
    assert "convergent-review" in result.stdout
    assert "Traceback" not in result.stdout
    # a list-typed field is shown with its types joined, not as a raw list
    assert "[" not in result.stdout.split("Inputs")[-1] or "string | null" in result.stdout


def test_describe_unknown_workflow_exits_cleanly():
    result = runner.invoke(workflow_app, ["describe", "no-such-workflow"])
    assert result.exit_code == 1
    assert "Unknown workflow" in result.stdout
