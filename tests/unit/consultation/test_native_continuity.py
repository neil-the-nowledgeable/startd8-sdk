"""M4 — native multi-turn continuity (FR-NC): message contract, renderers, agent wiring, engine."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from startd8.agents import multimodal as mm
from startd8.agents.messages import (
    Message,
    MessageContractError,
    render_anthropic,
    render_gemini,
    render_openai_turns,
    validate,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _img(path="/tmp/a.png"):
    return mm.image_from_bytes(PNG, source_path=path)


# ── FR-NC-1/1b/8: contract + validation ───────────────────────────────────────
class TestContract:
    def test_validate_rejects_bad_roles_and_non_alternating(self):
        with pytest.raises(MessageContractError):
            validate([Message(role="system", content="x")])
        with pytest.raises(MessageContractError, match="start with a user"):
            validate([Message(role="assistant", content="a")])
        with pytest.raises(MessageContractError, match="non-alternating"):
            validate([Message(role="user", content="a"), Message(role="user", content="b")])
        with pytest.raises(MessageContractError, match="empty assistant"):
            validate([Message(role="user", content="q"), Message(role="assistant", content="   ")])

    def test_unknown_part_kind_rejected(self):
        with pytest.raises(MessageContractError, match="unknown message part"):
            render_openai_turns([Message(role="user", content=[object()])])


# ── FR-NC-2: per-provider rendering fidelity ──────────────────────────────────
class TestRenderers:
    def _thread(self):
        return [
            Message(role="user", content=["look at this", _img()]),
            Message(role="assistant", content="I see a door."),
            Message(role="user", content="which screw?"),
        ]

    def test_anthropic_blocks_and_roles(self):
        out = render_anthropic(self._thread())
        assert [m["role"] for m in out] == ["user", "assistant", "user"]
        # user turn 0 has a text block + an image block
        kinds = [p["type"] for p in out[0]["content"]]
        assert kinds == ["text", "image"]
        assert out[0]["content"][1]["source"]["media_type"] == "image/png"

    def test_openai_roles_and_parts(self):
        out = render_openai_turns(self._thread())
        assert [m["role"] for m in out] == ["user", "assistant", "user"]
        assert out[0]["content"][1]["type"] == "image_url"  # image part
        assert out[1]["content"] == "I see a door."           # assistant text-only
        assert out[2]["content"] == "which screw?"            # single text ⇒ bare string

    def test_gemini_uses_model_role_not_assistant(self):
        out = render_gemini(self._thread())
        assert [m["role"] for m in out] == ["user", "model", "user"]  # NOT "assistant" (FR-NC-2)
        assert "inline_data" in out[0]["parts"][1]


# ── FR-NC-2 wiring: agenerate(messages=) reaches the client natively ──────────
class TestAgentWiring:
    @pytest.mark.asyncio
    async def test_claude_threads_native_messages(self):
        pytest.importorskip("anthropic")
        from startd8.agents.claude import ClaudeAgent

        agent = ClaudeAgent(api_key="test")
        assert agent.supports_messages() is True
        create = AsyncMock(return_value=object())
        agent.async_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        await agent._make_api_call("ignored", messages=render_anthropic([
            Message(role="user", content="q1"), Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
        ]))
        sent = create.call_args.kwargs["messages"]
        assert [m["role"] for m in sent] == ["user", "assistant", "user"]

    @pytest.mark.asyncio
    async def test_gemini_threads_role_tagged_contents(self):
        pytest.importorskip("google.genai")
        from startd8.agents.gemini import GeminiAgent
        from unittest.mock import Mock

        agent = GeminiAgent(api_key="test")
        assert agent.supports_messages() is True
        gen = Mock(return_value=object())
        agent.client = SimpleNamespace(models=SimpleNamespace(generate_content=gen))
        await agent._make_api_call("ignored", contents_override=render_gemini([
            Message(role="user", content="q1"), Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
        ]))
        contents = gen.call_args.kwargs["contents"]
        assert [c["role"] for c in contents] == ["user", "model", "user"]


# ── FR-NC-6: image re-send integrity ──────────────────────────────────────────
class TestImageResend:
    def _session(self, tmp_path, img_path):
        from startd8.consultation.models import (
            ConsultationSession, SessionImageRef, Turn, TurnRole, TurnStatus,
        )
        ref = SessionImageRef(sha256=mm.image_from_bytes(PNG).sha256, mime_type="image/png",
                              source_path=str(img_path))
        s = ConsultationSession(id="s", prompt="p", roster=["m"], continuity_mode="native")
        s.turns_by_model = {"m": [
            Turn(role=TurnRole.user, text="look", images=[ref]),
            Turn(role=TurnRole.assistant, text="ok", status=TurnStatus.ok),
        ]}
        return s

    def test_reloads_valid_image(self, tmp_path):
        from startd8.consultation import build_messages
        p = tmp_path / "a.png"; p.write_bytes(PNG)
        s = self._session(tmp_path, p)
        msgs = build_messages(s, "m", "follow up")
        # prior user turn's image reloaded → content is a parts list including an ImageInput
        first = msgs[0]
        assert isinstance(first.content, list) and any(isinstance(x, mm.ImageInput) for x in first.content)

    def test_missing_file_degrades_with_marker(self, tmp_path):
        from startd8.consultation import build_messages
        s = self._session(tmp_path, tmp_path / "gone.png")  # never written
        msgs = build_messages(s, "m", "follow up")
        assert "[image unavailable]" in (msgs[0].content if isinstance(msgs[0].content, str)
                                         else msgs[0].content[0])

    def test_hash_mismatch_degrades(self, tmp_path):
        from startd8.consultation import build_messages, reload_image
        from startd8.consultation.models import SessionImageRef
        p = tmp_path / "a.png"; p.write_bytes(PNG)
        bad_ref = SessionImageRef(sha256="0" * 64, mime_type="image/png", source_path=str(p))
        assert reload_image(bad_ref) is None  # bytes don't match stored hash

    def test_no_source_path_is_unavailable(self):
        from startd8.consultation import reload_image
        from startd8.consultation.models import SessionImageRef
        assert reload_image(SessionImageRef(sha256="x", mime_type="image/png", source_path=None)) is None


# ── FR-NC-5/5a/9: engine native vs transcript ─────────────────────────────────
class _Fake(__import__("startd8.agents.base", fromlist=["BaseAgent"]).BaseAgent):
    def __init__(self, name, model, native):
        super().__init__(name, model)
        self._native = native
        self.last = None

    def supports_messages(self):
        return self._native

    async def agenerate(self, prompt, **kwargs):  # pragma: no cover
        return SimpleNamespace(text="x", time_ms=1, token_usage=None)

    async def acreate_response(self, prompt_id, prompt, images=None, messages=None, **kwargs):
        self.last = {"prompt": prompt, "messages": messages}
        return SimpleNamespace(response=f"ans:{self.model}",
                               token_usage=SimpleNamespace(input=1, output=1), response_time_ms=1)


class TestEngineDispatch:
    @pytest.mark.asyncio
    async def test_native_agent_gets_messages_not_transcript(self, tmp_path):
        from startd8.consultation import ConsultationEngine, ConsultationStore
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        eng = ConsultationEngine(store)
        agent = _Fake("m", "anthropic:claude-opus-4-8", native=True)
        s = await eng.start("q1", None, {"m": agent})
        assert s.continuity_mode == "native"
        await eng.follow_up(store.load(s.id) if False else s, {"m": agent}, "q2", target="m")
        # follow-up call used messages=, not a transcript-prefixed prompt
        assert agent.last["messages"] is not None
        assert "<conversation-history>" not in (agent.last["prompt"] or "")

    @pytest.mark.asyncio
    async def test_non_native_agent_falls_back_to_transcript(self, tmp_path):
        from startd8.consultation import ConsultationEngine, ConsultationStore
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        eng = ConsultationEngine(store)
        agent = _Fake("m", "mock:mock-model", native=False)
        s = await eng.start("q1", None, {"m": agent})
        assert s.continuity_mode == "transcript"
        await eng.follow_up(s, {"m": agent}, "q2", target="m")
        assert agent.last["messages"] is None
        assert "<conversation-history>" in agent.last["prompt"]
