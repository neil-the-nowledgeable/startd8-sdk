"""Tests for query_prime.routing_overrides — REQ-KQP-601."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.routing_overrides import (
    RoutingOverride,
    RoutingOverrideStore,
)


class TestRoutingOverrideStore:
    """Tests for RoutingOverrideStore."""

    def test_empty_store(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        assert len(store) == 0
        assert store.get_minimum_tier("wi-1") is None

    def test_exact_match(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        store.add(RoutingOverride(
            pattern="wi-1",
            minimum_tier="moderate",
            reason="test",
        ))
        assert store.get_minimum_tier("wi-1") == ComplexityTier.MODERATE

    def test_prefix_match(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        store.add(RoutingOverride(
            pattern="payment-",
            minimum_tier="complex",
            reason="payment queries need T1",
        ))
        assert store.get_minimum_tier("payment-checkout") == ComplexityTier.COMPLEX
        assert store.get_minimum_tier("cart-add") is None

    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "overrides.json"
        store = RoutingOverrideStore(path=path)
        store.add(RoutingOverride(
            pattern="wi-1", minimum_tier="moderate",
        ))
        store.save()

        store2 = RoutingOverrideStore(path=path)
        store2.load()
        assert len(store2) == 1
        assert store2.get_minimum_tier("wi-1") == ComplexityTier.MODERATE

    def test_remove(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        store.add(RoutingOverride(pattern="wi-1", minimum_tier="moderate"))
        assert store.remove("wi-1")
        assert len(store) == 0
        assert not store.remove("nonexistent")

    def test_load_missing_file(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "missing.json")
        store.load()
        assert len(store) == 0

    def test_invalid_tier_returns_none(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        store.add(RoutingOverride(
            pattern="wi-1", minimum_tier="invalid_tier",
        ))
        assert store.get_minimum_tier("wi-1") is None

    def test_exact_match_takes_precedence(self, tmp_path: Path):
        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        store.add(RoutingOverride(
            pattern="wi-", minimum_tier="complex",
        ))
        store.add(RoutingOverride(
            pattern="wi-1", minimum_tier="simple",
        ))
        assert store.get_minimum_tier("wi-1") == ComplexityTier.SIMPLE

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "nested" / "dir" / "overrides.json"
        store = RoutingOverrideStore(path=path)
        store.add(RoutingOverride(pattern="x", minimum_tier="simple"))
        store.save()
        assert path.is_file()


class TestRoutingOverride:
    """Tests for RoutingOverride dataclass."""

    def test_roundtrip(self):
        override = RoutingOverride(
            pattern="wi-1",
            minimum_tier="moderate",
            reason="test reason",
        )
        d = override.to_dict()
        restored = RoutingOverride.from_dict(d)
        assert restored == override

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "pattern": "wi-1",
            "minimum_tier": "simple",
            "reason": "",
            "extra": "ignored",
        }
        override = RoutingOverride.from_dict(d)
        assert override.pattern == "wi-1"
