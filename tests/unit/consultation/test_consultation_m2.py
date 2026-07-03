"""M2 tests — consultation session model, storage, and parallel fan-out.

Uses a ``FakeAgent`` (no real providers) to drive the engine: it captures the prompt and
images each call receives and can be told to fail, so tests can assert parallelism, per-model
thread isolation, failure resilience, capability skipping, history threading, retry, and the
storage concurrency contract.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from startd8.agents.base import BaseAgent
from startd8.agents import multimodal as mm
from startd8.consultation import (
    ConsultationEngine,
    ConsultationSession,
    ConsultationStore,
    TurnRole,
    TurnStatus,
    new_session_id,
)
from startd8.consultation.store import SessionCollisionError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _img():
    return mm.image_from_bytes(PNG, source_path="/tmp/door.png")


class FakeAgent(BaseAgent):
    """Minimal agent: records calls, returns a canned reply, or raises on demand."""

    def __init__(self, name, model, *, reply="answer", fail_exc=None):
        super().__init__(name, model)
        self.reply = reply
        self.fail_exc = fail_exc
        self.calls: list[dict] = []

    async def agenerate(self, prompt, **kwargs):  # pragma: no cover - unused (acreate overridden)
        return SimpleNamespace(text=self.reply, time_ms=1, token_usage=None)

    async def acreate_response(self, prompt_id, prompt, images=None, **kwargs):
        self.calls.append({"prompt": prompt, "images": images})
        if self.fail_exc is not None:
            raise self.fail_exc
        return SimpleNamespace(
            response=f"{self.reply}:{self.model}",
            token_usage=SimpleNamespace(input=10, output=5),
            response_time_ms=42,
        )


def _engine(tmp_path):
    return ConsultationEngine(ConsultationStore(base_dir=tmp_path / ".startd8"))


# ─────────────────────────── storage / id contract ───────────────────────────
class TestStore:
    def test_session_id_is_sortable_and_process_unique(self):
        a, b = new_session_id(), new_session_id()
        assert a != b
        assert a.split("-")[0] <= b.split("-")[0]  # sortable ts prefix
        assert str(__import__("os").getpid()) in a  # process component

    def test_create_session_dir_is_exclusive(self, tmp_path):
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        sid = "20260703T000000-1-abc"
        store.create_session_dir(sid)
        with pytest.raises(SessionCollisionError):
            store.create_session_dir(sid)  # fail-loud, never clobber

    def test_save_is_atomic_and_roundtrips(self, tmp_path):
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        s = ConsultationSession(id="20260703T000000-1-abc", prompt="hi", roster=["m"])
        store.create_session_dir(s.id)
        store.save(s)
        d = store.session_dir(s.id)
        assert (d / "session.json").exists()
        assert (d / "summary.md").exists()
        assert not (d / "session.json.tmp").exists()  # no temp left behind
        assert store.load(s.id).prompt == "hi"


# ─────────────────────────── model helpers ───────────────────────────────────
class TestSessionModel:
    def test_valid_history_excludes_failed_turns(self):
        s = ConsultationSession(id="x", prompt="p", roster=["m"])
        from startd8.consultation import Turn, TurnError

        s.turns_by_model["m"] = [
            Turn(role=TurnRole.user, text="q1"),
            Turn(role=TurnRole.assistant, text="a1", status=TurnStatus.ok),
            Turn(role=TurnRole.user, text="q2"),
            Turn(role=TurnRole.assistant, status=TurnStatus.failed, error=TurnError(type="X")),
        ]
        hist = s.valid_history("m")
        assert [t.text for t in hist] == ["q1", "a1"]  # failed pair dropped
        assert s.failed_models() == ["m"]
        assert s.last_user_prompt("m") == "q2"


# ─────────────────────────── engine fan-out ──────────────────────────────────
class TestFanOut:
    @pytest.mark.asyncio
    async def test_start_fans_out_to_all_models(self, tmp_path):
        roster = {"anthropic:claude-opus-4-8": FakeAgent("a", "anthropic:claude-opus-4-8"),
                  "openai:gpt-4o": FakeAgent("o", "openai:gpt-4o")}
        eng = _engine(tmp_path)
        s = await eng.start("help me", images=None, roster=roster)

        assert set(s.turns_by_model) == set(roster)
        for m in roster:
            assert s.latest_status(m) == TurnStatus.ok
            assert s.turns_by_model[m][0].role == TurnRole.user
            assert s.turns_by_model[m][1].input_tokens == 10
        # persisted
        assert eng.store.load(s.id).latest_status("openai:gpt-4o") == TurnStatus.ok

    @pytest.mark.asyncio
    async def test_one_model_failure_does_not_sink_others(self, tmp_path):
        boom = RuntimeError("429 rate limited")
        boom.status_code = 429
        roster = {"good": FakeAgent("g", "anthropic:claude-3-haiku"),
                  "bad": FakeAgent("b", "anthropic:claude-3-haiku", fail_exc=boom)}
        eng = _engine(tmp_path)
        s = await eng.start("q", images=None, roster=roster)

        assert s.latest_status("good") == TurnStatus.ok
        assert s.latest_status("bad") == TurnStatus.failed
        err = s.turns_by_model["bad"][-1].error
        assert err.type == "RuntimeError" and err.code == "429"  # structured (R2-S8)

    @pytest.mark.asyncio
    async def test_non_vision_model_is_skipped_with_images(self, tmp_path):
        vision = FakeAgent("v", "openai:gpt-4o")
        blind = FakeAgent("b", "openai:gpt-3.5-turbo")
        roster = {"openai:gpt-4o": vision, "openai:gpt-3.5-turbo": blind}
        eng = _engine(tmp_path)
        s = await eng.start("look", images=[_img()], roster=roster)

        assert s.latest_status("openai:gpt-4o") == TurnStatus.ok
        assert s.latest_status("openai:gpt-3.5-turbo") == TurnStatus.skipped_non_vision
        assert blind.calls == []  # never called
        # vision model actually received the image, and it's persisted without bytes
        assert vision.calls[0]["images"] is not None
        assert s.images[0].sha256 and not hasattr(s.images[0], "data")


class TestFollowUp:
    @pytest.mark.asyncio
    async def test_followup_single_model_threads_history(self, tmp_path):
        a = FakeAgent("a", "anthropic:claude-opus-4-8")
        b = FakeAgent("b", "openai:gpt-4o")
        roster = {"anthropic:claude-opus-4-8": a, "openai:gpt-4o": b}
        eng = _engine(tmp_path)
        s = await eng.start("first question", images=None, roster=roster)

        await eng.follow_up(s, roster, "second question", target="anthropic:claude-opus-4-8")

        # Only the targeted model got a new turn.
        assert len(s.turns_by_model["anthropic:claude-opus-4-8"]) == 4  # user,asst,user,asst
        assert len(s.turns_by_model["openai:gpt-4o"]) == 2
        # The follow-up prompt carried the prior turn as history.
        followup_prompt = a.calls[-1]["prompt"]
        assert "<conversation-history>" in followup_prompt
        assert "first question" in followup_prompt
        assert "second question" in followup_prompt

    @pytest.mark.asyncio
    async def test_followup_all_hits_every_model(self, tmp_path):
        roster = {"m1": FakeAgent("m1", "anthropic:claude-3-haiku"),
                  "m2": FakeAgent("m2", "anthropic:claude-3-haiku")}
        eng = _engine(tmp_path)
        s = await eng.start("q1", images=None, roster=roster)
        await eng.follow_up(s, roster, "q2", target="all")
        for m in roster:
            assert len(s.turns_by_model[m]) == 4

    @pytest.mark.asyncio
    async def test_followup_rejects_unknown_target(self, tmp_path):
        roster = {"m1": FakeAgent("m1", "anthropic:claude-3-haiku")}
        eng = _engine(tmp_path)
        s = await eng.start("q1", images=None, roster=roster)
        with pytest.raises(ValueError, match="not a model"):
            await eng.follow_up(s, roster, "q2", target="nope")


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_failed_only_reinvokes_failed_model(self, tmp_path):
        boom = RuntimeError("temporary")
        good = FakeAgent("good", "anthropic:claude-3-haiku")
        bad = FakeAgent("bad", "anthropic:claude-3-haiku", fail_exc=boom)
        roster = {"good": good, "bad": bad}
        eng = _engine(tmp_path)
        s = await eng.start("q", images=None, roster=roster)
        assert s.failed_models() == ["bad"]

        # Heal the failed agent and retry.
        bad.fail_exc = None
        good_calls_before = len(good.calls)
        await eng.retry_failed(s, roster)

        assert s.latest_status("bad") == TurnStatus.ok
        assert len(good.calls) == good_calls_before  # succeeded model untouched (FR-MMC-11)
