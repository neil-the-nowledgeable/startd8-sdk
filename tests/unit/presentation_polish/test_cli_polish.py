"""CLI surface for `startd8 polish` (FR-1, FR-3, FR-7): apply / check / themes."""

from typer.testing import CliRunner

from startd8.cli_polish import polish_app
from startd8.presentation_polish.engine import STYLESHEET_RELPATH

runner = CliRunner()
pytestmark = []


def test_themes_lists_presets():
    result = runner.invoke(polish_app, ["themes"])
    assert result.exit_code == 0
    assert "professional" in result.stdout
    assert "editorial" in result.stdout


def test_apply_writes_and_reports_zero_cost(tmp_path):
    (tmp_path / "app").mkdir()
    result = runner.invoke(polish_app, ["apply", "--project", str(tmp_path), "--theme", "minimal"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / STYLESHEET_RELPATH).is_file()
    assert "$0.00" in result.stdout
    # outcome-framed UX (FR-7): no "skill" jargon leaks to the user
    assert "skill" not in result.stdout.lower()


def test_apply_unknown_theme_errors(tmp_path):
    (tmp_path / "app").mkdir()
    result = runner.invoke(polish_app, ["apply", "--project", str(tmp_path), "--theme", "bogus"])
    assert result.exit_code == 2
    assert "unknown theme" in result.stdout


def test_check_reports_drift_exit_code(tmp_path):
    (tmp_path / "app").mkdir()
    # nothing applied yet → drift (exit 1)
    result = runner.invoke(polish_app, ["check", "--project", str(tmp_path)])
    assert result.exit_code == 1
    # apply then check → in sync (exit 0)
    runner.invoke(polish_app, ["apply", "--project", str(tmp_path)])
    result2 = runner.invoke(polish_app, ["check", "--project", str(tmp_path)])
    assert result2.exit_code == 0
    assert "in_sync" in result2.stdout
