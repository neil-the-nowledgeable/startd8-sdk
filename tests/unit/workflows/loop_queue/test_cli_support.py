# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FR-24 / FR-17 CLI support tests for WLQ root resolution and hygiene."""

from __future__ import annotations

import io
import json
from pathlib import Path

from startd8.workflows.loop_queue.cli_support import (
    DEFAULT_QUEUE_RELATIVE,
    STARTD8_WLOOP_ROOT_ENV,
    ensure_queue_marker,
    is_fresh_queue_root,
    print_json_stdout,
    resolve_cli_root,
    resolve_queue_root,
    warn_if_fresh_queue_root,
)


def test_resolve_queue_root_prefers_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-q"
    env = {STARTD8_WLOOP_ROOT_ENV: str(tmp_path / "from-env")}
    assert resolve_queue_root(explicit, env=env) == explicit.resolve()


def test_resolve_queue_root_uses_env(tmp_path: Path) -> None:
    env_root = tmp_path / "env-q"
    got = resolve_queue_root(
        None, env={STARTD8_WLOOP_ROOT_ENV: str(env_root)}, cwd=tmp_path
    )
    assert got == env_root.resolve()


def test_resolve_queue_root_cwd_default(tmp_path: Path) -> None:
    got = resolve_queue_root(None, env={}, cwd=tmp_path)
    assert got == (tmp_path / DEFAULT_QUEUE_RELATIVE).resolve()


def test_resolve_cli_root_default_defers_to_env(tmp_path: Path, monkeypatch) -> None:
    env_root = tmp_path / "loop-owning"
    monkeypatch.setenv(STARTD8_WLOOP_ROOT_ENV, str(env_root))
    assert resolve_cli_root(DEFAULT_QUEUE_RELATIVE) == env_root.resolve()


def test_resolve_cli_root_absolute_wins(tmp_path: Path, monkeypatch) -> None:
    env_root = tmp_path / "loop-owning"
    monkeypatch.setenv(STARTD8_WLOOP_ROOT_ENV, str(env_root))
    explicit = tmp_path / "other"
    assert resolve_cli_root(explicit) == explicit.resolve()


def test_fresh_queue_warn_then_marker_suppresses(tmp_path: Path) -> None:
    root = tmp_path / "new-q"
    assert is_fresh_queue_root(root) is True
    buf = io.StringIO()
    assert warn_if_fresh_queue_root(root, stream=buf) is True
    assert "NEW queue" in buf.getvalue()
    assert str(root.resolve()) in buf.getvalue()
    ensure_queue_marker(root)
    assert is_fresh_queue_root(root) is False
    buf2 = io.StringIO()
    assert warn_if_fresh_queue_root(root, stream=buf2) is False
    assert buf2.getvalue() == ""


def test_existing_jobs_not_fresh(tmp_path: Path) -> None:
    root = tmp_path / "q"
    jobs = root / "jobs"
    jobs.mkdir(parents=True)
    (jobs / "crp-x_startd8_wloop.json").write_text("{}", encoding="utf-8")
    assert is_fresh_queue_root(root) is False


def test_print_json_stdout_is_parseable(capsys) -> None:
    print_json_stdout({"ok": True, "n": 1})
    out = capsys.readouterr().out
    assert json.loads(out) == {"ok": True, "n": 1}
