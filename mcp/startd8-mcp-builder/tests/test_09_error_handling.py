"""Phase 5.1: Error Handling / Graceful Degradation Tests.

These tests focus on shared error utilities and file/SDK error paths
that aren't already fully covered by tool-specific tests.

Covers:
- T5.1.1 Missing dependencies handled (Anthropic SDK covered in test_05)
- T5.1.2 File system errors handled
- T5.1.3 API errors handled (partially covered in test_05)
- T5.1.4 Invalid YAML handled (covered in discovery tests)
- T5.1.5 Permission errors handled
- T5.1.7 All errors return helpful messages (general `_handle_error`)
"""

from __future__ import annotations

from pathlib import Path

import pytest

import startd8_mcp


def test_handle_error_includes_type_name() -> None:
    """T5.1.7 - `_handle_error` prefixes messages with the exception type."""

    class CustomError(RuntimeError):
        pass

    e = CustomError("something went wrong")
    msg = startd8_mcp._handle_error(e)

    assert msg.startswith("Error: CustomError:"), msg
    assert "something went wrong" in msg


def test_load_skill_instructions_permission_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T5.1.2/T5.1.5 - Permission or IO errors produce a clear error message.

    We simulate a permission error by monkeypatching Path.read_text to
    raise a PermissionError for the specific path used in the fake
    skill, without affecting other paths.
    """

    fake_file = tmp_path / "skills" / "blocked" / "SKILL.md"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_text("# blocked", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):  # type: ignore[override]
        if self == fake_file:
            raise PermissionError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    skill = {"file_path": str(fake_file)}
    msg = startd8_mcp._load_skill_instructions(skill)

    assert msg.startswith("Error loading skill instructions:"), msg
    assert "permission denied" in msg

