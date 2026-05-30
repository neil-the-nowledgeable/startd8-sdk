"""Unit tests for the model_catalog user overlay (PL-TMM-4, REQ-TMM-130/131)."""

from __future__ import annotations

import startd8.model_catalog as mc
from startd8.model_catalog import (
    ModelInfo,
    Models,
    get_escalation_target,
    get_latest_model,
    get_model_info,
    is_known_model,
    list_models_by_capability,
    list_models_by_tier,
)
from startd8.user_models import UserModelStore


def _set_overlay(monkeypatch, mapping):
    monkeypatch.setattr(mc, "_load_user_overlay", lambda: mapping)


def test_overlay_model_resolves_via_get_model_info(monkeypatch):
    _set_overlay(
        monkeypatch,
        {"my-user-model": ModelInfo("anthropic", "my-user-model", "flagship", {"text"})},
    )
    info = get_model_info("my-user-model")
    assert info is not None and info.tier == "flagship"
    assert is_known_model("anthropic:my-user-model")


def test_overlay_takes_precedence_over_baseline(monkeypatch):
    # override a real catalog id with a different tier (REQ-TMM-131)
    _set_overlay(
        monkeypatch,
        {"claude-opus-4-8": ModelInfo("anthropic", "claude-opus-4-8", "mini", {"text"})},
    )
    assert get_model_info("claude-opus-4-8").tier == "mini"


def test_get_latest_model_ignores_overlay(monkeypatch):
    # NR-6: overlay models resolvable but never auto-selected as a tier default
    _set_overlay(
        monkeypatch,
        {"my-flagship": ModelInfo("anthropic", "my-flagship", "flagship", {"text"})},
    )
    assert get_latest_model("anthropic", "flagship") == Models.CLAUDE_OPUS_LATEST
    assert get_latest_model("anthropic", "flagship") != "anthropic:my-flagship"


def test_escalation_honors_overlay_tier(monkeypatch):
    # a user 'fast' model escalates to the balanced constant
    _set_overlay(
        monkeypatch,
        {"my-fast": ModelInfo("anthropic", "my-fast", "fast", {"text"})},
    )
    assert get_escalation_target("anthropic:my-fast") == Models.CLAUDE_SONNET_LATEST


def test_list_by_tier_and_capability_include_overlay(monkeypatch):
    _set_overlay(
        monkeypatch,
        {"ov-flag": ModelInfo("anthropic", "ov-flag", "flagship", {"text", "code"})},
    )
    assert "anthropic:ov-flag" in list_models_by_tier("flagship")
    assert "anthropic:ov-flag" in list_models_by_capability("code")


def test_empty_overlay_leaves_baseline_intact(monkeypatch):
    _set_overlay(monkeypatch, {})
    assert get_model_info("claude-opus-4-8") is not None
    assert get_model_info("claude-opus-4-8").tier == "flagship"


def test_load_user_overlay_reads_real_store(monkeypatch, tmp_path):
    # end-to-end: _load_user_overlay -> UserModelStore.as_catalog_overlay
    seed = UserModelStore(config_dir=tmp_path)
    seed.add("anthropic", "real-user-model", tier="balanced", capabilities=["text"])
    monkeypatch.setattr(
        "startd8.user_models.UserModelStore",
        lambda: UserModelStore(config_dir=tmp_path),
    )
    overlay = mc._load_user_overlay()
    assert "real-user-model" in overlay
    assert overlay["real-user-model"].tier == "balanced"
    # and an invalid-tier record is excluded (R1-S3) — write one directly
    import json

    bad = {
        "version": 1,
        "models": {"anthropic": [{"model_id": "bad", "tier": "bogus"}]},
        "suppressed": {},
    }
    seed.config_file.write_text(json.dumps(bad))
    assert "bad" not in mc._load_user_overlay()
