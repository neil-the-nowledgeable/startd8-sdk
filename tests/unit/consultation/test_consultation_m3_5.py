"""M3.5 tests — ``startd8 consult`` CLI + the TUI≡CLI no-fork golden fixture (FR-MMC-13, R1-S10).

The roster resolver is monkeypatched to deterministic fake agents, so the CLI runs fully
offline. The golden-fixture test drives the SAME ``ConsultationService`` two ways — through the
CLI command and directly (as the TUI does) — over the §4 front-door images, and asserts the two
persisted sessions are identical (modulo id/timestamps).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from startd8.agents.base import BaseAgent
from startd8.cli_consult import consult_app
from startd8.consultation import ConsultationService

runner = CliRunner()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


class FakeAgent(BaseAgent):
    def __init__(self, name, model):
        super().__init__(name, model)

    async def agenerate(self, prompt, **kwargs):  # pragma: no cover
        return SimpleNamespace(text="x", time_ms=1, token_usage=None)

    async def acreate_response(self, prompt_id, prompt, images=None, **kwargs):
        return SimpleNamespace(
            response=f"answer-from:{self.model}",
            token_usage=SimpleNamespace(input=7, output=3),
            response_time_ms=11,
        )


@pytest.fixture(autouse=True)
def _fake_roster(monkeypatch):
    """Make roster resolution offline + deterministic."""
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(ar, "resolve_agent_spec", lambda spec, **k: FakeAgent(spec, spec))


@pytest.fixture(autouse=True)
def _in_tmp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return tmp_path


DOOR_PROMPT = (
    "My front door is broken. Look at these 2 images — the handle no longer opens the door "
    "even when unlocked, and I can't turn the inner knob either. Help me open it."
)


def _door_images(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    (d / "front.png").write_bytes(PNG)
    (d / "inside.png").write_bytes(PNG)
    return d


# ─────────────────────────── CLI behavior ────────────────────────────────────
class TestConsultRun:
    def test_run_creates_session(self):
        result = runner.invoke(
            consult_app,
            ["run", "--prompt", "help", "--models", "openai:gpt-4o", "--models", "anthropic:claude-opus-4-8"],
        )
        assert result.exit_code == 0, result.output
        assert "session:" in result.output
        assert "answer-from:openai:gpt-4o" in result.output

    def test_run_requires_prompt(self):
        result = runner.invoke(consult_app, ["run", "--models", "openai:gpt-4o"])
        assert result.exit_code == 2
        assert "provide --prompt" in result.output

    def test_run_image_and_dir_mutually_exclusive(self, tmp_path):
        d = _door_images(tmp_path)
        result = runner.invoke(
            consult_app,
            ["run", "--prompt", "x", "--models", "openai:gpt-4o",
             "--image", str(d / "front.png"), "--image-dir", str(d)],
        )
        assert result.exit_code == 2
        assert "not both" in result.output

    def test_run_with_images_skips_non_vision(self, tmp_path):
        d = _door_images(tmp_path)
        result = runner.invoke(
            consult_app,
            ["run", "--prompt", DOOR_PROMPT, "--image-dir", str(d),
             "--models", "openai:gpt-4o", "--models", "openai:gpt-3.5-turbo"],
        )
        assert result.exit_code == 0, result.output
        assert "skipping openai:gpt-3.5-turbo" in result.output  # non-vision gated


class TestConsultReply:
    def test_reply_continues_session(self, tmp_path):
        run = runner.invoke(consult_app, ["run", "--prompt", "q1", "--models", "openai:gpt-4o"])
        sid = run.output.strip().split("session:")[-1].strip()

        reply = runner.invoke(
            consult_app, ["reply", sid, "--prompt", "q2", "--to", "openai:gpt-4o"]
        )
        assert reply.exit_code == 0, reply.output

        session = ConsultationService(base_dir=".startd8").load(sid)
        assert len(session.turns_by_model["openai:gpt-4o"]) == 4  # user,asst,user,asst

    def test_reply_unknown_session(self):
        result = runner.invoke(consult_app, ["reply", "nope-123", "--prompt", "q"])
        assert result.exit_code == 2
        assert "no such session" in result.output

    def test_show_and_list(self):
        run = runner.invoke(consult_app, ["run", "--prompt", "q", "--models", "openai:gpt-4o"])
        sid = run.output.strip().split("session:")[-1].strip()
        assert runner.invoke(consult_app, ["show", sid]).exit_code == 0
        listing = runner.invoke(consult_app, ["list"])
        assert sid in listing.output


# ─────────────────────────── TUI ≡ CLI (R1-S10) ──────────────────────────────
class TestNoLogicFork:
    def test_cli_and_direct_service_produce_identical_session(self, tmp_path):
        """The §4 front-door case: CLI and the direct (TUI) path yield identical sessions."""
        d = _door_images(tmp_path)
        models = ["openai:gpt-4o", "anthropic:claude-opus-4-8"]

        # Path A — the CLI command.
        cli = runner.invoke(
            consult_app,
            ["run", "--prompt", DOOR_PROMPT, "--image-dir", str(d)]
            + sum([["--models", m] for m in models], []),
        )
        assert cli.exit_code == 0, cli.output
        cli_sid = cli.output.strip().split("session:")[-1].strip()
        cli_session = ConsultationService(base_dir=".startd8").load(cli_sid)

        # Path B — drive the shared service directly, exactly as the TUI mixin does.
        from startd8.consultation import build_roster, resolve_images

        imgs = resolve_images(image_dir=str(d))
        roster, _ = build_roster(models, require_vision=True)
        tui_session = ConsultationService(base_dir=".startd8").start(DOOR_PROMPT, imgs, roster)

        # Identical image selection (same folder → same 2 hashes, R2-F3/R1-S10).
        assert [i.sha256 for i in cli_session.images] == [i.sha256 for i in tui_session.images]
        assert len(cli_session.images) == 2

        # Identical roster + per-model answers (fake agents are deterministic).
        assert cli_session.roster == tui_session.roster
        for m in models:
            cli_ans = [t.text for t in cli_session.turns_by_model[m] if t.text]
            tui_ans = [t.text for t in tui_session.turns_by_model[m] if t.text]
            assert cli_ans == tui_ans
