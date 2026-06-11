"""resolve_skill_md: the real skill-loading mechanism that replaced the phantom-tool stub."""

from pathlib import Path

from startd8.skills.agent import resolve_skill_md


def _make_skill(home: Path, name: str, body: str) -> None:
    d = home / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")


def test_reads_skill_md(tmp_path, monkeypatch):
    _make_skill(tmp_path, "frontend-design", "# Frontend Design\nBe bold.\n")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_skill_md("frontend-design") == "# Frontend Design\nBe bold.\n"


def test_strips_skill_prefix(tmp_path, monkeypatch):
    # on-disk dir is un-prefixed; the skill_id may carry a `skill-` prefix
    _make_skill(tmp_path, "code-reviewer", "review well")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_skill_md("skill-code-reviewer") == "review well"


def test_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_skill_md("nonexistent-skill") is None
