"""Light integration tests for the TUI Manage-Models flows (PL-TMM-5/6/7).

The TUI is heavy to construct, so we bypass __init__ via object.__new__ and set
only the attributes the model-management helpers touch (``console``). questionary
prompts are scripted; the UserModelStore is redirected to a temp dir.
"""

from __future__ import annotations

import pytest
from rich.console import Console

import startd8.tui_improved as tui_mod
import startd8.user_models as um


def _ask(value):
    class _A:
        def ask(self):
            return value
    return _A()


class _Script:
    """Scripted questionary: each prompt type pops its next return value."""

    def __init__(self, *, selects=None, texts=None, confirms=None):
        self.selects = list(selects or [])
        self.texts = list(texts or [])
        self.confirms = list(confirms or [])

    def install(self, monkeypatch):
        q = tui_mod.questionary
        monkeypatch.setattr(q, "select", lambda *a, **k: _ask(self.selects.pop(0)))
        monkeypatch.setattr(q, "text", lambda *a, **k: _ask(self.texts.pop(0)))
        monkeypatch.setattr(q, "confirm", lambda *a, **k: _ask(self.confirms.pop(0)))
        monkeypatch.setattr(
            q, "press_any_key_to_continue", lambda *a, **k: _ask(None)
        )


@pytest.fixture
def tui(tmp_path, monkeypatch):
    # Redirect every UserModelStore() to the temp dir (matches the global
    # default convention; classify/_load_user_overlay pick it up too).
    real = um.UserModelStore
    monkeypatch.setattr(um, "UserModelStore", lambda *a, **k: real(config_dir=tmp_path))
    inst = object.__new__(tui_mod.ImprovedTUI)
    inst.console = Console()
    return inst


def test_manage_models_add_persists(tui, tmp_path, monkeypatch):
    # add "my-custom-model": unrecognized -> confirm yes, tier balanced
    _Script(texts=["my-custom-model"], confirms=[True], selects=["balanced"]).install(monkeypatch)
    tui._manage_models_add("anthropic")

    from startd8.user_models import UserModelStore
    records = UserModelStore(config_dir=tmp_path).list("anthropic")
    assert [r["model_id"] for r in records] == ["my-custom-model"]
    assert records[0]["tier"] == "balanced"
    assert records[0]["source"] == "manual"


def test_manage_models_add_invalid_id_rejected(tui, tmp_path, monkeypatch):
    _Script(texts=["bad:id"]).install(monkeypatch)  # ':' is forbidden
    tui._manage_models_add("anthropic")
    from startd8.user_models import UserModelStore
    assert UserModelStore(config_dir=tmp_path).list("anthropic") == []


def test_maybe_persist_custom_model_saves_with_source(tui, tmp_path, monkeypatch):
    # unrecognized -> "use anyway" yes -> "save?" yes -> tier fast
    _Script(confirms=[True, True], selects=["fast"]).install(monkeypatch)
    result = tui._maybe_persist_custom_model("anthropic", "foo-model")
    assert result == "foo-model"

    from startd8.user_models import UserModelStore
    records = UserModelStore(config_dir=tmp_path).list("anthropic")
    assert records[0]["model_id"] == "foo-model"
    assert records[0]["source"] == "custom-entry"
    assert records[0]["tier"] == "fast"


def test_maybe_persist_declined_returns_id_without_saving(tui, tmp_path, monkeypatch):
    # known model (no unrecognized confirm) -> "save?" no
    monkeypatch.setattr(
        "startd8.model_sources.classify_model_id", lambda p, m, **k: "known"
    )
    _Script(confirms=[False]).install(monkeypatch)
    result = tui._maybe_persist_custom_model("anthropic", "claude-opus-4-8")
    assert result == "claude-opus-4-8"
    from startd8.user_models import UserModelStore
    assert UserModelStore(config_dir=tmp_path).list("anthropic") == []


def test_model_view_groups_origins(tui, tmp_path, monkeypatch):
    # stub baseline + discovered so the view is deterministic
    class _Prov:
        HARDCODED_MODELS = ["base-1", "base-2"]

    monkeypatch.setattr(tui, "_get_provider_safe", lambda name: _Prov())

    class _Disc:
        def get_discovered_models(self, provider):
            return ["disc-1"]

    monkeypatch.setattr("startd8.model_discovery.ModelDiscoveryService", _Disc)

    from startd8.user_models import UserModelStore
    UserModelStore(config_dir=tmp_path).add("anthropic", "user-1", tier="flagship")

    view = tui._model_view_for_provider("anthropic")
    by_origin = {}
    for v in view:
        by_origin.setdefault(v["origin"], []).append(v["model_id"])
    assert by_origin["user-added"] == ["user-1"]
    assert by_origin["discovered"] == ["disc-1"]
    assert set(by_origin["baseline"]) == {"base-1", "base-2"}


def test_manage_models_remove_suppresses_baseline(tui, tmp_path, monkeypatch):
    view = [{"model_id": "claude-opus-4-8", "origin": "baseline"}]
    _Script(selects=["claude-opus-4-8"]).install(monkeypatch)
    tui._manage_models_remove("anthropic", view)
    from startd8.user_models import UserModelStore
    assert "claude-opus-4-8" in UserModelStore(config_dir=tmp_path).suppressed("anthropic")
