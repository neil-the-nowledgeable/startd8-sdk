"""M-web tests — render_html safety/structure + `startd8 consult web` command (FR-WUI)."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from startd8.cli_consult import consult_app
from startd8.consultation import (
    ConsultationSession,
    ConsultationStore,
    SessionImageRef,
    Turn,
    TurnError,
    TurnRole,
    TurnStatus,
    render_html,
)

runner = CliRunner()


def _session() -> ConsultationSession:
    s = ConsultationSession(
        id="20260703T000000-1-abcdef",
        prompt="help me open my door",
        roster=["anthropic:claude-opus-4-8", "openai:gpt-5.5", "openai:gpt-3.5-turbo"],
        images=[
            SessionImageRef(
                sha256="deadbeefcafe1234",
                mime_type="image/jpeg",
                source_path="/Users/secret/private/front-picture.jpeg",
                size_bytes=3700990,
            )
        ],
    )
    s.turns_by_model = {
        "anthropic:claude-opus-4-8": [
            Turn(role=TurnRole.user, text="help me open my door", images=[s.images[0]]),
            Turn(
                role=TurnRole.assistant,
                text="### Steps\n\n1. Grip the **spindle**.\nBeware `<script>alert(1)</script>` — must be inert.",
                status=TurnStatus.ok,
                input_tokens=9638,
                output_tokens=805,
                time_ms=21240,
            ),
        ],
        "openai:gpt-5.5": [
            Turn(role=TurnRole.user, text="help me open my door"),
            Turn(role=TurnRole.assistant, status=TurnStatus.failed,
                 error=TurnError(type="RateLimitError", code="429", message="TPM exceeded")),
        ],
        "openai:gpt-3.5-turbo": [
            Turn(role=TurnRole.user, text="help me open my door"),
            Turn(role=TurnRole.assistant, status=TurnStatus.skipped_non_vision),
        ],
    }
    return s


def _json_block(html: str) -> str:
    return html.split('id="session-data">', 1)[1].split("</script>", 1)[0]


class TestRenderHtml:
    def test_is_complete_standalone_document(self):
        html = render_html(_session())
        assert html.startswith("<!DOCTYPE html>")
        assert "__SESSION_JSON__" not in html  # placeholder filled
        assert "<style>" in html and "application/json" in html  # self-contained

    def test_embedded_json_has_no_raw_closing_script(self):
        # The </script> inside the model answer must be neutralized (<), or the
        # <script type=application/json> container breaks in a real browser.
        block = _json_block(render_html(_session()))
        assert "</script>" not in block
        assert "\\u003cscript" in block  # payload escaped, not raw

    def test_no_absolute_image_path_leaks(self):
        html = render_html(_session())
        assert "/Users/secret/private" not in html  # FR-WUI-9: basename only
        assert "front-picture.jpeg" in html
        assert "deadbeef" in html  # short hash shown

    def test_contains_all_models_and_statuses(self):
        html = render_html(_session())
        for m in ("anthropic:claude-opus-4-8", "openai:gpt-5.5", "openai:gpt-3.5-turbo"):
            assert m in html
        block = _json_block(html)
        assert '"failed"' in block and '"429"' in block
        assert '"skipped-non-vision"' in block
        assert '"input_tokens": 9638' in block

    def test_embedded_json_parses_after_unescaping(self):
        # Simulate the browser: < decodes back to '<'; the doc must still be valid JSON.
        import json

        block = _json_block(render_html(_session()))
        data = json.loads(block.replace("\\u003c", "<"))
        assert len(data["roster"]) == 3
        claude = data["turns_by_model"]["anthropic:claude-opus-4-8"][1]["text"]
        assert "<script>alert(1)</script>" in claude  # present in data; client re-escapes on render


class TestConsultWebCommand:
    def _seed(self, tmp_path):
        store = ConsultationStore(base_dir=tmp_path / ".startd8")
        s = _session()
        store.create_session_dir(s.id)
        store.save(s)
        return s

    def test_web_writes_view_html_into_session_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = self._seed(tmp_path)
        result = runner.invoke(consult_app, ["web", s.id])
        assert result.exit_code == 0, result.output
        view = tmp_path / ".startd8" / "consultations" / s.id / "view.html"
        assert view.exists()
        assert "anthropic:claude-opus-4-8" in view.read_text(encoding="utf-8")

    def test_web_out_override(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = self._seed(tmp_path)
        out = tmp_path / "custom.html"
        result = runner.invoke(consult_app, ["web", s.id, "--out", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists() and out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    def test_web_unknown_session(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(consult_app, ["web", "nope-999"])
        assert result.exit_code == 2
        assert "no such session" in result.output
