"""Kickoff UX v0.5 — output hygiene & orientation (FR-UX-13..16 + UX-P6).

Covers the quiet-by-default logging seam, the --debug/env toggle and precedence, the per-step
what+why, and the intro banner (source-level budget + --json suppression). See
docs/design/kickoff/KICKOFF_UX_{REQUIREMENTS,PLAN}.md (v0.6 §3E / Steps 7-10).
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8.logging_config import configure_cli_logging, _env_debug

runner = CliRunner()


def _console_handlers(logger):
    return [
        h for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]


# ── FR-UX-13/14 — quiet-by-default console + --debug toggle (levels, not IO) ───────────────────────

class TestConfigureCliLogging:
    def test_quiet_default_logger_open_console_warning(self, monkeypatch):
        # Fidelity (CRP R2-S1): the logger must sit at DEBUG so file/OTel keep full records,
        # while the console handler gates terminal visibility at WARNING.
        monkeypatch.setattr("startd8.logging_config._ENV_LOG_LEVEL", None)
        configure_cli_logging(debug=False)
        root = logging.getLogger("startd8")
        assert root.level == logging.DEBUG
        chs = _console_handlers(root)
        assert chs and all(h.level == logging.WARNING for h in chs)

    def test_debug_raises_console_to_debug(self, monkeypatch):
        monkeypatch.setattr("startd8.logging_config._ENV_LOG_LEVEL", None)
        configure_cli_logging(debug=True)
        chs = _console_handlers(logging.getLogger("startd8"))
        assert chs and all(h.level == logging.DEBUG for h in chs)

    def test_env_log_level_wins_over_debug(self, monkeypatch):
        # STARTD8_LOG_LEVEL takes precedence over --debug (FR-UX-14 precedence).
        monkeypatch.setattr("startd8.logging_config._ENV_LOG_LEVEL", "ERROR")
        configure_cli_logging(debug=True)
        chs = _console_handlers(logging.getLogger("startd8"))
        assert chs and all(h.level == logging.ERROR for h in chs)

    def test_file_handler_retains_debug(self, monkeypatch):
        monkeypatch.setattr("startd8.logging_config._ENV_LOG_LEVEL", None)
        configure_cli_logging(debug=False)
        fhs = [h for h in logging.getLogger("startd8").handlers if isinstance(h, logging.FileHandler)]
        assert fhs and all(h.level == logging.DEBUG for h in fhs)

    def test_idempotent_no_duplicate_console_handler(self, monkeypatch):
        # Applied-once invariant (CRP R2-F2/S2): repeated calls don't accrue handlers.
        monkeypatch.setattr("startd8.logging_config._ENV_LOG_LEVEL", None)
        configure_cli_logging(debug=False)
        n = len(_console_handlers(logging.getLogger("startd8")))
        configure_cli_logging(debug=True)
        configure_cli_logging(debug=False)
        assert len(_console_handlers(logging.getLogger("startd8"))) == n


@pytest.mark.parametrize(
    "val,expected",
    [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("", False), ("no", False)],
)
def test_env_debug_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("STARTD8_DEBUG", val)
    assert _env_debug() is expected


# ── FR-UX-13/14 end-to-end (subprocess — the real console the user sees) ───────────────────────────

def _cli_env():
    import startd8

    src = str(Path(startd8.__file__).resolve().parent.parent)
    return {**os.environ, "PYTHONPATH": src}


def _run_cli(args, env_extra=None):
    env = _cli_env()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "startd8.cli", *args],
        capture_output=True, text=True, env=env, timeout=90,
    )


@pytest.mark.slow
def test_cli_quiet_by_default(tmp_path):
    r = _run_cli(["kickoff", "survey", str(tmp_path)])
    assert r.returncode == 0, r.stderr
    # No diagnostic plumbing on the default console (FR-UX-13) — including the otel banner.
    assert " - INFO - " not in r.stderr
    assert "startd8.concierge" not in r.stderr


@pytest.mark.slow
def test_cli_debug_flag_restores_plumbing(tmp_path):
    r = _run_cli(["--debug", "kickoff", "survey", str(tmp_path)])
    assert r.returncode == 0, r.stderr
    assert " - INFO - " in r.stderr and "concierge.survey" in r.stderr


@pytest.mark.slow
def test_cli_env_debug_restores_plumbing(tmp_path):
    r = _run_cli(["kickoff", "survey", str(tmp_path)], env_extra={"STARTD8_DEBUG": "1"})
    assert " - INFO - " in r.stderr


@pytest.mark.slow
def test_cli_log_level_error_overrides_debug(tmp_path):
    r = _run_cli(["--debug", "kickoff", "survey", str(tmp_path)], env_extra={"STARTD8_LOG_LEVEL": "ERROR"})
    assert " - INFO - " not in r.stderr


# ── FR-UX-15 — every step carries a plain-language what + why ──────────────────────────────────────

def test_next_action_carries_plain_why(tmp_path):
    from startd8.kickoff_experience.presentation import headline, has_jargon
    from startd8.kickoff_experience.red_carpet import build_red_carpet_state

    hl = headline(build_red_carpet_state(tmp_path))
    na = hl["next_action"]
    assert na.get("why"), "next action must carry a why (FR-UX-15)"
    assert has_jargon(na["why"]) is None
    assert has_jargon(na["title"]) is None


# ── FR-UX-16 — the intro banner (source-level budget + no-jargon + --json suppression) ─────────────

def test_banner_source_level_budget_and_no_jargon():
    # CRP R2-F3/S5: assert the packaged BANNER slice itself is bounded (compact fallbacks can't
    # silently blow the budget) and jargon-free.
    from startd8.concierge import load_experience_doc
    from startd8.kickoff_experience.presentation import has_jargon

    banner = load_experience_doc("intro", section="banner")
    assert banner, "packaged intro must expose a BANNER slice"
    assert len(banner.splitlines()) <= 6
    assert has_jargon(banner) is None


def test_red_carpet_shows_banner_first(tmp_path):
    res = runner.invoke(app, ["kickoff-legacy", "red-carpet", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert "sets up the inputs" in res.stdout          # the banner
    assert "Do next" in res.stdout                     # the focused next action
    # Banner precedes the status body.
    assert res.stdout.index("sets up the inputs") < res.stdout.index("Do next")


def test_json_suppresses_banner_and_stays_valid(tmp_path):
    import json

    res = runner.invoke(app, ["kickoff-legacy", "red-carpet", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.stdout
    assert "sets up the inputs" not in res.stdout       # FR-UX-16 --json suppression
    json.loads(res.stdout)                              # NR-3 — still a valid payload


def test_bare_kickoff_and_subcommand_share_one_banner(tmp_path):
    # CRP R2-S4 — one shared renderer: the same banner text appears on bare `kickoff` and red-carpet.
    bare = runner.invoke(app, ["kickoff"])
    rc = runner.invoke(app, ["kickoff-legacy", "red-carpet", str(tmp_path)])
    assert "sets up the inputs" in bare.stdout
    assert "sets up the inputs" in rc.stdout
