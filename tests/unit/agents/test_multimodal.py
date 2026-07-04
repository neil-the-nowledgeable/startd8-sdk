"""M1 tests — multimodal image support (FR-MMC-2).

Two layers:
1. Pure pre-adapter tests (validation, encoding, render helpers, vision heuristic) —
   no provider packages needed.
2. Per-provider payload-threading + **byte-identity** tests — construct each agent with a
   throwaway key, mock its client, and inspect the request the provider would send:
   * images present  → the provider-native image shape appears in the payload
   * images absent    → the payload is byte-identical to the text-only path

Guarded with ``importorskip`` per provider so the suite runs wherever the SDK does.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from startd8.agents import multimodal as mm

# ── Fixtures: minimal valid magic-byte payloads (enough for header sniffing) ──
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20
GIF_STATIC = b"GIF89a" + b"\x00" * 20
GIF_ANIMATED = b"GIF89a" + (b"\x21\xf9\x04\x00\x00\x00\x00\x00") * 2 + b"\x00" * 8
WEBP_STATIC = b"RIFF" + b"\x20\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 16
WEBP_ANIMATED = b"RIFF" + b"\x20\x00\x00\x00" + b"WEBP" + b"VP8X" + b"ANIM" + b"\x00" * 16


def _png() -> mm.ImageInput:
    return mm.image_from_bytes(PNG_BYTES, source_path="/tmp/door.png")


# ─────────────────────────── Layer 1: pure pre-adapter ───────────────────────
class TestValidation:
    def test_accepts_png_jpeg_gif_webp(self):
        assert mm.image_from_bytes(PNG_BYTES).mime_type == "image/png"
        assert mm.image_from_bytes(JPEG_BYTES).mime_type == "image/jpeg"
        assert mm.image_from_bytes(GIF_STATIC).mime_type == "image/gif"
        assert mm.image_from_bytes(WEBP_STATIC).mime_type == "image/webp"

    def test_rejects_non_image_bytes(self):
        with pytest.raises(mm.ImageValidationError, match="magic-byte"):
            mm.image_from_bytes(b"NOT-AN-IMAGE-AT-ALL-just-text")

    def test_rejects_renamed_non_image(self):
        # A file that claims .png by extension but is actually text/HEIC-ish bytes.
        with pytest.raises(mm.ImageValidationError):
            mm.image_from_bytes(b"ftypheic" + b"\x00" * 20)

    def test_rejects_animated_gif(self):
        with pytest.raises(mm.ImageValidationError, match="animated"):
            mm.image_from_bytes(GIF_ANIMATED)

    def test_rejects_animated_webp(self):
        with pytest.raises(mm.ImageValidationError, match="animated"):
            mm.image_from_bytes(WEBP_ANIMATED)

    def test_rejects_over_ceiling(self):
        with pytest.raises(mm.ImageValidationError, match="ceiling"):
            mm.image_from_bytes(PNG_BYTES, max_bytes=4)

    def test_rejects_empty(self):
        with pytest.raises(mm.ImageValidationError, match="empty"):
            mm.image_from_bytes(b"")

    def test_content_hash_is_sha256(self):
        import hashlib

        img = _png()
        assert img.sha256 == hashlib.sha256(PNG_BYTES).hexdigest()

    def test_validate_images_caps_count(self):
        img = _png()
        assert mm.validate_images(None) == []
        assert mm.validate_images([]) == []
        assert len(mm.validate_images([img, img])) == 2
        with pytest.raises(mm.ImageValidationError, match="per-turn limit"):
            mm.validate_images([img, img, img])


class TestImageRef:
    def test_to_ref_drops_bytes(self):
        ref = _png().to_ref()
        assert isinstance(ref, mm.ImageRef)
        assert not hasattr(ref, "data")
        assert ref.mime_type == "image/png"
        assert ref.source_path == "/tmp/door.png"
        assert ref.size_bytes == len(PNG_BYTES)


class TestLoadImage:
    def test_load_and_validate_from_path(self, tmp_path):
        p = tmp_path / "door.png"
        p.write_bytes(PNG_BYTES)
        img = mm.load_image(p)
        assert img.mime_type == "image/png"
        assert img.source_path == str(p.resolve())

    def test_rejects_symlink(self, tmp_path):
        real = tmp_path / "real.png"
        real.write_bytes(PNG_BYTES)
        link = tmp_path / "link.png"
        link.symlink_to(real)
        with pytest.raises(mm.ImageValidationError, match="symlink"):
            mm.load_image(link)


class TestRenderHelpers:
    def test_anthropic_block_shape(self):
        block = mm.to_anthropic_block(_png())
        assert block == {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(PNG_BYTES).decode("ascii"),
            },
        }

    def test_openai_part_shape(self):
        part = mm.to_openai_part(_png())
        b64 = base64.standard_b64encode(PNG_BYTES).decode("ascii")
        assert part == {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        }

    def test_gemini_part_shape_uses_raw_bytes(self):
        part = mm.to_gemini_part(_png())
        assert part == {"inline_data": {"mime_type": "image/png", "data": PNG_BYTES}}


class TestVisionHeuristic:
    @pytest.mark.parametrize(
        "model",
        ["claude-opus-4-8", "claude-3-haiku", "gpt-4o", "gpt-4.1", "gemini-2.5-pro", "gemini-1.5-flash"],
    )
    def test_vision_capable_models(self, model):
        assert mm.model_supports_vision(model) is True

    @pytest.mark.parametrize("model", ["gpt-3.5-turbo", "text-embedding-3-small", "unknown-model", ""])
    def test_non_vision_models(self, model):
        assert mm.model_supports_vision(model) is False


# ─────────────── Layer 2: per-provider payload threading + byte-identity ──────
class TestAnthropicPayload:
    def _agent(self):
        pytest.importorskip("anthropic")
        from startd8.agents.claude import ClaudeAgent

        agent = ClaudeAgent(api_key="test-key")
        create = AsyncMock(return_value=object())
        agent.async_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        return agent, create

    @pytest.mark.asyncio
    async def test_text_only_is_byte_identical(self):
        agent, create = self._agent()
        await agent._make_api_call("open my door")
        assert create.call_args.kwargs["messages"] == [
            {"role": "user", "content": "open my door"}
        ]

    @pytest.mark.asyncio
    async def test_images_become_content_blocks(self):
        agent, create = self._agent()
        await agent._make_api_call("open my door", images=[_png()])
        content = create.call_args.kwargs["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "open my door"}
        assert content[1]["type"] == "image"
        assert content[1]["source"]["media_type"] == "image/png"


class TestOpenAIPayload:
    def _gpt4_agent(self):
        pytest.importorskip("openai")
        from startd8.agents.openai import GPT4Agent

        agent = GPT4Agent(api_key="test-key")
        create = AsyncMock(return_value=object())
        agent.async_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        return agent, create

    def _compat_agent(self):
        pytest.importorskip("openai")
        from startd8.agents.openai import OpenAICompatibleAgent

        agent = OpenAICompatibleAgent(api_key="test-key", base_url="https://api.openai.com/v1")
        create = AsyncMock(return_value=object())
        agent.async_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        return agent, create

    @pytest.mark.asyncio
    async def test_gpt4_text_only_is_byte_identical(self):
        agent, create = self._gpt4_agent()
        await agent._make_api_call("open my door")
        assert create.call_args.kwargs["messages"][-1]["content"] == "open my door"

    @pytest.mark.asyncio
    async def test_gpt4_images_become_content_parts(self):
        agent, create = self._gpt4_agent()
        await agent._make_api_call("open my door", images=[_png()])
        content = create.call_args.kwargs["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "open my door"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_compatible_second_site_also_wires_images(self):
        # R2-S4: the second OpenAI construction site must receive image parts too.
        agent, create = self._compat_agent()
        await agent._make_api_call("open my door", images=[_png()])
        content = create.call_args.kwargs["messages"][-1]["content"]
        assert content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_compatible_text_only_is_byte_identical(self):
        agent, create = self._compat_agent()
        await agent._make_api_call("open my door")
        assert create.call_args.kwargs["messages"][-1]["content"] == "open my door"


class TestGeminiPayload:
    def _agent(self):
        pytest.importorskip("google.genai")
        from startd8.agents.gemini import GeminiAgent

        agent = GeminiAgent(api_key="test-key")
        gen = Mock(return_value=object())
        agent.client = SimpleNamespace(models=SimpleNamespace(generate_content=gen))
        return agent, gen

    @pytest.mark.asyncio
    async def test_text_only_is_byte_identical(self):
        agent, gen = self._agent()
        await agent._make_api_call("open my door")
        assert gen.call_args.kwargs["contents"] == "open my door"

    @pytest.mark.asyncio
    async def test_images_become_inline_parts(self):
        agent, gen = self._agent()
        await agent._make_api_call("open my door", images=[_png()])
        contents = gen.call_args.kwargs["contents"]
        assert contents[0] == "open my door"
        assert contents[1] == {"inline_data": {"mime_type": "image/png", "data": PNG_BYTES}}
