# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Adapter registry tests (FR-4/FR-9): resolution, unknown-format, built-in-wins, failure isolation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import startd8.stakeholder_panel.adapters as reg
from startd8.stakeholder_panel.adapters import AdapterError, AdaptResult, get_adapter
from startd8.stakeholder_panel.models import Roster


@pytest.fixture(autouse=True)
def _reset_registry():
    """Isolate the module-level registry state between tests."""
    saved, was = dict(reg._registered), reg._discovered
    reg._registered.clear()
    reg._discovered = False
    yield
    reg._registered.clear()
    reg._registered.update(saved)
    reg._discovered = was


class _EP:
    def __init__(self, name, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader()


class _FakeAdapter:
    name = "fake"

    def adapt(self, text):
        return AdaptResult(roster=Roster())


def test_builtin_role_rubric_resolves():
    adapter = get_adapter("role-rubric")
    assert adapter.name == "role-rubric"
    assert "role-rubric" in reg.available()


def test_unknown_format_raises_listing_available():
    with pytest.raises(AdapterError, match="role-rubric"):
        get_adapter("no-such-format")


def test_register_and_resolve_a_custom_adapter():
    reg.register(_FakeAdapter())
    assert get_adapter("fake").name == "fake"
    assert "fake" in reg.available()


def test_failure_isolation_skips_a_broken_entry_point(monkeypatch):
    def _boom():
        raise RuntimeError("broken adapter")

    class _GoodAdapter:
        name = "good"

        def adapt(self, text):
            return AdaptResult(roster=Roster())

    monkeypatch.setattr(
        reg,
        "_entry_points",
        lambda: [_EP("broken", _boom), _EP("good", lambda: _GoodAdapter)],
    )
    reg.discover(force=True)  # must not raise despite the broken EP
    assert "good" in reg.available()  # keyed by the adapter's .name
    assert "broken" not in reg.available()


def test_builtin_wins_a_name_collision(monkeypatch):
    class _Shadow:
        name = "role-rubric"

        def adapt(self, text):
            return AdaptResult(roster=Roster())

    monkeypatch.setattr(
        reg, "_entry_points", lambda: [_EP("role-rubric", lambda: _Shadow)]
    )
    reg.discover(force=True)
    # The built-in RoleRubricAdapter wins over the shadowing entry point.
    from startd8.stakeholder_panel.adapters.role_rubric import RoleRubricAdapter

    assert isinstance(get_adapter("role-rubric"), RoleRubricAdapter)


def test_role_rubric_is_not_imported_until_get_adapter():
    # R2-F4: importing the package (and even the registry) must not pull the adapter module.
    src = str(Path(__file__).resolve().parents[3] / "src")
    code = (
        "import sys; import startd8.stakeholder_panel; "
        "import startd8.stakeholder_panel.adapters as a; "
        "assert 'startd8.stakeholder_panel.adapters.role_rubric' not in sys.modules, 'eager import'; "
        "a.get_adapter('role-rubric'); "
        "assert 'startd8.stakeholder_panel.adapters.role_rubric' in sys.modules; "
        "print('ok')"
    )
    env = {**os.environ, "PYTHONPATH": src}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
