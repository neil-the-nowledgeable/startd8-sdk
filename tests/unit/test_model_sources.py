"""Unit tests for classify_model_id four-source reconciliation (PL-TMM-3)."""

from __future__ import annotations

import pytest

from startd8.model_sources import classify_model_id
from startd8.user_models import UserModelStore


class _StubProvider:
    def __init__(self, models):
        self.supported_models = list(models)


@pytest.fixture
def store(tmp_path):
    return UserModelStore(config_dir=tmp_path)


def test_user_overlay_classifies_as_user(store):
    store.add("anthropic", "my-model", tier="fast")
    result = classify_model_id(
        "anthropic", "my-model",
        store=store, provider_obj=_StubProvider([]), catalog_lookup=lambda m: False,
    )
    assert result == "user"


def test_catalog_hit_classifies_as_known(store):
    result = classify_model_id(
        "anthropic", "catalog-model",
        store=store, provider_obj=_StubProvider([]),
        catalog_lookup=lambda m: m == "catalog-model",
    )
    assert result == "known"


def test_supported_models_hit_classifies_as_known(store):
    # source #2/#3 via provider.supported_models
    result = classify_model_id(
        "anthropic", "claude-opus-4-8",
        store=store, provider_obj=_StubProvider(["claude-opus-4-8"]),
        catalog_lookup=lambda m: False,
    )
    assert result == "known"


def test_absent_everywhere_is_unrecognized(store):
    result = classify_model_id(
        "anthropic", "claude-opus-4-9-typo",
        store=store, provider_obj=_StubProvider(["claude-opus-4-8"]),
        catalog_lookup=lambda m: False,
    )
    assert result == "unrecognized"


def test_user_precedence_over_baseline_collision(store):
    # id in BOTH user overlay and provider baseline -> 'user' (checked first)
    store.add("anthropic", "dup", tier="flagship")
    result = classify_model_id(
        "anthropic", "dup",
        store=store, provider_obj=_StubProvider(["dup"]),
        catalog_lookup=lambda m: True,
    )
    assert result == "user"


def test_real_sources_smoke():
    # Integration smoke against the real catalog/provider (no overlay).
    # claude-opus-4-8 was added to the catalog + HARDCODED_MODELS this session.
    assert classify_model_id("anthropic", "claude-opus-4-8") == "known"
    assert classify_model_id("anthropic", "definitely-not-a-real-model-xyz") == "unrecognized"
