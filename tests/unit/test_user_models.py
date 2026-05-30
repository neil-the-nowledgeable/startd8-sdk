"""Unit tests for the user model overlay store (PL-TMM-2)."""

from __future__ import annotations

import json

import pytest

from startd8.user_models import (
    ModelCollisionError,
    ModelIdError,
    SCHEMA_VERSION,
    UserModelStore,
    normalize_model_id,
    normalize_tier,
)


@pytest.fixture
def store(tmp_path):
    return UserModelStore(config_dir=tmp_path)


# -- normalization (REQ-TMM-107, R1-S8) ------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "a\nb", "a:b", "x\x00y", "y\x7f", "x" * 201])
def test_normalize_model_id_rejects(bad):
    with pytest.raises(ModelIdError):
        normalize_model_id(bad)


@pytest.mark.parametrize(
    "good",
    ["claude-opus-4-8", "nvidia/nemotron-3-nano-30b-a3b", "meta-llama/Llama-3.3-70B"],
)
def test_normalize_model_id_allows_slashes_and_trims(good):
    assert normalize_model_id(f"  {good}  ") == good


def test_normalize_tier():
    assert normalize_tier("Flagship") == "flagship"
    with pytest.raises(ModelIdError):
        normalize_tier("supreme")


# -- add / list / persistence (REQ-TMM-101/104/105) ------------------------


def test_add_persists_with_metadata_and_survives_reopen(store, tmp_path):
    store.add("anthropic", "claude-opus-4-8", tier="flagship", source="custom-entry")
    reopened = UserModelStore(config_dir=tmp_path)
    records = reopened.list("anthropic")
    assert len(records) == 1
    rec = records[0]
    assert rec["model_id"] == "claude-opus-4-8"
    assert rec["tier"] == "flagship"
    assert rec["capabilities"] == ["text", "code"]  # OQ-B default
    assert rec["source"] == "custom-entry"
    assert "added_at" in rec  # provenance (R1-S6)


def test_add_is_idempotent_upsert(store):
    store.add("anthropic", "m1", tier="fast")
    store.add("anthropic", "m1", tier="flagship", capabilities=["text"])
    records = store.list("anthropic")
    assert len(records) == 1
    assert records[0]["tier"] == "flagship"
    assert records[0]["capabilities"] == ["text"]


def test_add_requires_valid_tier(store):
    with pytest.raises(ModelIdError):
        store.add("anthropic", "m1", tier="nope")


def test_schema_shape_on_disk(store):
    store.add("anthropic", "m1", tier="fast")
    raw = json.loads(store.config_file.read_text())
    assert raw["version"] == SCHEMA_VERSION
    assert "last_updated" in raw
    assert "models" in raw and "suppressed" in raw


# -- remove + suppression + resurrection (REQ-TMM-102, R1-S7) --------------


def test_remove_user_model(store):
    store.add("anthropic", "m1", tier="fast")
    assert store.remove("anthropic", "m1") == "removed"
    assert store.list("anthropic") == []


def test_remove_baseline_suppresses_then_resurrects(store):
    # m-base is not a user model -> remove records a suppression
    assert store.remove("anthropic", "m-base") == "suppressed"
    assert "m-base" in store.suppressed("anthropic")
    # re-adding the same id clears the suppression (resurrection)
    store.add("anthropic", "m-base", tier="balanced")
    assert "m-base" not in store.suppressed("anthropic")


def test_remove_noop_when_already_suppressed(store):
    store.remove("anthropic", "m-base")
    assert store.remove("anthropic", "m-base") == "noop"


# -- edit + collision (REQ-TMM-103, R1-F7) ---------------------------------


def test_edit_id_and_tier(store):
    store.add("anthropic", "m1", tier="fast")
    rec = store.edit("anthropic", "m1", new_id="m2", tier="flagship")
    assert rec["model_id"] == "m2"
    assert rec["tier"] == "flagship"
    assert {r["model_id"] for r in store.list("anthropic")} == {"m2"}


def test_edit_to_existing_user_id_rejected(store):
    store.add("anthropic", "m1", tier="fast")
    store.add("anthropic", "m2", tier="fast")
    with pytest.raises(ModelCollisionError):
        store.edit("anthropic", "m1", new_id="m2")
    # state unchanged
    assert {r["model_id"] for r in store.list("anthropic")} == {"m1", "m2"}


def test_edit_collision_via_external_check(store):
    store.add("anthropic", "m1", tier="fast")
    # simulate baseline/discovered collision via callback
    with pytest.raises(ModelCollisionError):
        store.edit(
            "anthropic", "m1", new_id="claude-opus-4-8",
            collision_check=lambda p, mid: mid == "claude-opus-4-8",
        )


def test_edit_missing_model_raises(store):
    with pytest.raises(ModelIdError):
        store.edit("anthropic", "ghost", tier="fast")


# -- merge_view dedup + precedence (REQ-TMM-131) ---------------------------


def test_merge_view_precedence_and_dedup(store):
    store.add("anthropic", "dup", tier="flagship", capabilities=["text", "vision"])
    view = store.merge_view(
        "anthropic",
        baseline=["dup", "base-only"],
        discovered=["dup", "disc-only"],
    )
    by_id = {v["model_id"]: v for v in view}
    # 'dup' present once, as user-added, with user metadata authoritative (R1-F5)
    assert by_id["dup"]["origin"] == "user-added"
    assert by_id["dup"]["tier"] == "flagship"
    assert by_id["dup"]["capabilities"] == ["text", "vision"]
    assert by_id["disc-only"]["origin"] == "discovered"
    assert by_id["base-only"]["origin"] == "baseline"
    # no duplicates
    assert len(view) == len({v["model_id"] for v in view})


def test_merge_view_hides_suppressed(store):
    store.remove("anthropic", "base-x")  # suppress
    view = store.merge_view("anthropic", baseline=["base-x", "base-y"], discovered=[])
    assert {v["model_id"] for v in view} == {"base-y"}


# -- catalog overlay + tier validation (REQ-TMM-130, R1-S3) ----------------


def test_as_catalog_overlay_valid(store):
    store.add("anthropic", "m1", tier="flagship", capabilities=["text", "code"])
    overlay = store.as_catalog_overlay()
    assert overlay["m1"]["provider"] == "anthropic"
    assert overlay["m1"]["tier"] == "flagship"
    assert overlay["m1"]["capabilities"] == {"text", "code"}


def test_as_catalog_overlay_drops_invalid_tier(store, tmp_path):
    # hand-write a record with a bad tier (bypassing add()'s validation)
    bad = {
        "version": SCHEMA_VERSION,
        "models": {"anthropic": [{"model_id": "m1", "tier": "bogus"}]},
        "suppressed": {},
    }
    store.config_file.write_text(json.dumps(bad))
    assert store.as_catalog_overlay() == {}


# -- corruption recovery (REQ-TMM-106) -------------------------------------


def test_malformed_file_recovers_to_empty(store):
    store.config_file.write_text("{not json")
    assert store.list("anthropic") == []
    # store remains usable after recovery
    store.add("anthropic", "m1", tier="fast")
    assert {r["model_id"] for r in store.list("anthropic")} == {"m1"}


# -- concurrency: reload-before-write (R1-S4) ------------------------------


def test_interleaved_adds_from_two_instances_preserve_both(tmp_path):
    a = UserModelStore(config_dir=tmp_path)
    b = UserModelStore(config_dir=tmp_path)
    a.add("anthropic", "from-a", tier="fast")
    b.add("anthropic", "from-b", tier="fast")  # reloads a's write first
    final = UserModelStore(config_dir=tmp_path).list("anthropic")
    assert {r["model_id"] for r in final} == {"from-a", "from-b"}


# -- version migration (R1-S9) ---------------------------------------------


def test_future_version_read_best_effort(store):
    future = {
        "version": 99,
        "models": {"anthropic": [{"model_id": "m1", "tier": "fast",
                                  "capabilities": ["text"]}]},
        "suppressed": {},
    }
    store.config_file.write_text(json.dumps(future))
    # does not treat as corrupt; reads records best-effort
    assert {r["model_id"] for r in store.list("anthropic")} == {"m1"}
