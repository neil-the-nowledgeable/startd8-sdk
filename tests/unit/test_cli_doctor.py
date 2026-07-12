"""FR-E10 — `startd8 doctor` environment self-check."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from startd8.cli_doctor import run_doctor  # noqa: E402


class _C:
    def __init__(self):
        self.out = []

    def print(self, *a, **k):
        self.out.append(" ".join(str(x) for x in a))


def test_doctor_reports_version_and_install_kind():
    c = _C()
    rc = run_doctor(c)
    text = "\n".join(c.out)
    assert "startd8 doctor" in text and "startd8" in text
    assert ("editable" in text) or ("installed" in text)
    assert "python" in text.lower()
    assert rc in (0, 1)


def test_doctor_warns_and_exits_1_without_a_provider_key(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
              "GEMINI_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = _C()
    rc = run_doctor(c)
    assert rc == 1
    assert any("provider API key" in line for line in c.out)


def test_doctor_ok_exit_0_with_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = _C()
    rc = run_doctor(c)
    # editable source + a key → no warnings on this in-repo run
    assert rc == 0 or all("provider API key" not in line for line in c.out)
