"""M3 tests — image selection (trust boundary + determinism), roster, view, TUI wiring."""

from __future__ import annotations

import os

import pytest

from startd8.consultation import (
    build_roster,
    comparison_text,
    resolve_images,
)
from startd8.consultation.selection import (
    ImageSelectionError,
    select_from_dir,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _write(p, data=PNG):
    p.write_bytes(data)
    return p


# ─────────────────────────── selection: determinism ──────────────────────────
class TestSelectFromDir:
    def test_deterministic_first_two_lexicographic(self, tmp_path):
        for name in ["c.png", "a.png", "b.png", "d.png"]:
            _write(tmp_path / name)
        imgs = select_from_dir(tmp_path)
        assert [os.path.basename(i.source_path) for i in imgs] == ["a.png", "b.png"]

    def test_skips_non_image_files_but_keeps_order(self, tmp_path):
        _write(tmp_path / "a.txt", b"not an image")
        _write(tmp_path / "b.png", PNG)
        _write(tmp_path / "c.jpg", JPEG)
        imgs = select_from_dir(tmp_path)
        assert [os.path.basename(i.source_path) for i in imgs] == ["b.png", "c.jpg"]

    def test_same_two_from_tui_and_cli_paths(self, tmp_path):
        # The no-fork guarantee: dir selection is a pure function of the folder.
        for name in ["z.png", "m.png", "a.png"]:
            _write(tmp_path / name)
        a = select_from_dir(tmp_path)
        b = resolve_images(image_dir=tmp_path)
        assert [i.sha256 for i in a] == [i.sha256 for i in b]


# ─────────────────────────── selection: trust boundary ───────────────────────
class TestTrustBoundary:
    def test_skips_symlinked_entries(self, tmp_path):
        real = _write(tmp_path / "real.png")
        (tmp_path / "link.png").symlink_to(real)
        # 'link.png' sorts before 'real.png' but must be skipped (symlink).
        imgs = select_from_dir(tmp_path)
        assert [os.path.basename(i.source_path) for i in imgs] == ["real.png"]

    def test_skips_fifo_and_non_regular(self, tmp_path):
        _write(tmp_path / "a.png")
        os.mkfifo(tmp_path / "b_pipe")  # named pipe — must not hang or be selected
        imgs = select_from_dir(tmp_path)
        assert [os.path.basename(i.source_path) for i in imgs] == ["a.png"]

    def test_allowed_root_rejects_escape(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        _write(outside / "a.png")
        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(ImageSelectionError, match="escapes allowed root"):
            select_from_dir(outside, allowed_root=root)

    def test_bounded_scan_does_not_hang(self, tmp_path):
        for i in range(50):
            _write(tmp_path / f"img_{i:03d}.png")
        imgs = select_from_dir(tmp_path, max_dir_entries=5)
        assert len(imgs) <= 2  # bounded + capped


class TestResolveImagesMutualExclusion:
    def test_paths_and_dir_are_mutually_exclusive(self, tmp_path):
        p = _write(tmp_path / "a.png")
        with pytest.raises(ImageSelectionError, match="not both"):
            resolve_images(paths=[str(p)], image_dir=str(tmp_path))

    def test_empty_returns_empty(self):
        assert resolve_images() == []

    def test_too_many_paths_rejected(self, tmp_path):
        ps = [str(_write(tmp_path / f"{c}.png")) for c in "abc"]
        with pytest.raises(ImageSelectionError, match="exceeds"):
            resolve_images(paths=ps)


# ─────────────────────────── roster ──────────────────────────────────────────
class TestRoster:
    def test_filters_non_vision_and_resolves_vision(self, monkeypatch):
        import startd8.utils.agent_resolution as ar

        def fake_resolve(spec, **kwargs):
            return object()  # stand-in agent

        monkeypatch.setattr(ar, "resolve_agent_spec", fake_resolve)
        roster, unavailable = build_roster(
            ["anthropic:claude-opus-4-8", "openai:gpt-3.5-turbo"],
            require_vision=True,
        )
        assert "anthropic:claude-opus-4-8" in roster
        assert ("openai:gpt-3.5-turbo", "not vision-capable") in unavailable

    def test_unresolvable_spec_is_recorded_not_raised(self, monkeypatch):
        import startd8.utils.agent_resolution as ar

        def boom(spec, **kwargs):
            raise RuntimeError("no api key")

        monkeypatch.setattr(ar, "resolve_agent_spec", boom)
        roster, unavailable = build_roster(["openai:gpt-5.5"], require_vision=True)
        assert roster == {}
        assert unavailable and "no api key" in unavailable[0][1]

    def test_default_council_used_when_specs_none(self, monkeypatch):
        import startd8.utils.agent_resolution as ar

        seen = []
        monkeypatch.setattr(ar, "resolve_agent_spec", lambda spec, **k: seen.append(spec) or object())
        build_roster(None, require_vision=True)
        assert len(seen) == 3  # the cross-vendor council


# ─────────────────────────── view ────────────────────────────────────────────
class TestComparisonView:
    def test_comparison_text_covers_all_statuses(self):
        from startd8.consultation import ConsultationSession, Turn, TurnError, TurnRole, TurnStatus

        s = ConsultationSession(id="x", prompt="p", roster=["ok_m", "fail_m", "skip_m"])
        s.turns_by_model = {
            "ok_m": [Turn(role=TurnRole.user, text="q"),
                     Turn(role=TurnRole.assistant, text="the answer", status=TurnStatus.ok,
                          input_tokens=10, output_tokens=5, time_ms=42)],
            "fail_m": [Turn(role=TurnRole.assistant, status=TurnStatus.failed,
                            error=TurnError(type="RateLimit", code="429"))],
            "skip_m": [Turn(role=TurnRole.assistant, status=TurnStatus.skipped_non_vision)],
        }
        text = comparison_text(s)
        assert "ok_m" in text and "the answer" in text and "in=10" in text
        assert "fail_m" in text and "RateLimit" in text
        assert "skip_m" in text and "not vision-capable" in text


# ─────────────────────────── TUI wiring ──────────────────────────────────────
class TestTuiWiring:
    def test_mixin_exposes_menu(self):
        from startd8.tui.mixin_consultation import ConsultationMixin

        assert hasattr(ConsultationMixin, "consultation_menu")

    def test_improved_tui_registers_consultation(self):
        pytest.importorskip("questionary")
        from startd8.tui_improved import ImprovedTUI
        from startd8.tui.mixin_consultation import ConsultationMixin

        assert issubclass(ImprovedTUI, ConsultationMixin)
        assert hasattr(ImprovedTUI, "consultation_menu")
