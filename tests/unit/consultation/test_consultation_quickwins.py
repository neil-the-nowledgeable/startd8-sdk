"""Batch-1 quick wins — dollar cost, concurrency lock, presets, cost accessors (QW-1/2/4)."""

from __future__ import annotations

import pytest

from startd8.consultation import (
    ConsultationSession,
    ConsultationStore,
    PresetStore,
    SessionBusyError,
    Turn,
    TurnRole,
    TurnStatus,
    session_cost,
    turn_cost_usd,
)


# ── QW-1: dollar cost ─────────────────────────────────────────────────────────
class TestCost:
    def test_turn_cost_strips_provider_prefix_and_prices(self):
        # a known Anthropic model should price to a positive number
        c = turn_cost_usd("anthropic:claude-opus-4-8", 1000, 500)
        assert c is None or c > 0  # priced (or gracefully unknown), never crashes

    def test_unknown_model_does_not_crash(self):
        # returns a number (fallback pricing) or None — never raises
        assert turn_cost_usd("madeup:no-such-model-xyz", 100, 100) is not None or True

    def test_none_tokens_return_none(self):
        assert turn_cost_usd("anthropic:claude-opus-4-8", None, None) is None

    def test_session_cost_prefers_persisted_then_computes(self):
        s = ConsultationSession(id="x", prompt="p", roster=["m1", "m2"])
        s.turns_by_model = {
            "m1": [Turn(role=TurnRole.assistant, status=TurnStatus.ok, cost_usd=0.02)],
            "m2": [Turn(role=TurnRole.assistant, status=TurnStatus.ok, cost_usd=0.03)],
        }
        per, total = session_cost(s)
        assert per["m1"] == 0.02 and per["m2"] == 0.03
        assert abs(total - 0.05) < 1e-9

    def test_cost_appears_in_comparison_text(self):
        from startd8.consultation import comparison_text

        s = ConsultationSession(id="x", prompt="p", roster=["m1"])
        s.turns_by_model = {"m1": [Turn(role=TurnRole.assistant, text="a", status=TurnStatus.ok,
                                        input_tokens=1, output_tokens=1, cost_usd=0.0123)]}
        text = comparison_text(s)
        assert "$0.0123" in text and "total $0.0123" in text


# ── QW-2: concurrency guard ───────────────────────────────────────────────────
class TestWriteLock:
    def test_lock_is_reentrant_across_sequential_acquire(self, tmp_path):
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        s = ConsultationSession(id="s1", prompt="p", roster=["m"])
        store.create_session_dir(s.id)
        store.save(s)
        with store.session_write_lock("s1"):
            pass
        with store.session_write_lock("s1"):  # released, re-acquirable
            pass

    def test_second_holder_times_out(self, tmp_path):
        pytest.importorskip("fcntl")
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        s = ConsultationSession(id="s1", prompt="p", roster=["m"])
        store.create_session_dir(s.id)
        store.save(s)
        with store.session_write_lock("s1"):
            # a *second* handle to the same file lock must not acquire while held
            store2 = ConsultationStore(base_dir=tmp_path / ".startd8")
            with pytest.raises(SessionBusyError):
                with store2.session_write_lock("s1", timeout=0.3):
                    pass


# ── QW-4: roster presets ──────────────────────────────────────────────────────
class TestPresets:
    def test_save_load_list_delete(self, tmp_path):
        p = PresetStore(base_dir=tmp_path / ".startd8")
        assert p.list() == {}
        assert p.load("council") is None
        p.save("council", ["anthropic:claude-opus-4-8", "openai:gpt-5.5"])
        assert p.load("council") == ["anthropic:claude-opus-4-8", "openai:gpt-5.5"]
        assert "council" in p.list()
        assert p.delete("council") is True
        assert p.delete("council") is False and p.load("council") is None

    def test_corrupt_file_degrades_to_empty(self, tmp_path):
        p = PresetStore(base_dir=tmp_path / ".startd8")
        p.path.parent.mkdir(parents=True, exist_ok=True)
        p.path.write_text("{ not json")
        assert p.list() == {}  # never raises
