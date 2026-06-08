"""PresentationPolishFileProvider: owns polish files; in-sync iff they match the recorded theme."""

from pathlib import Path

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.presentation_polish import PolishConfig, apply_polish
from startd8.presentation_polish.engine import STYLESHEET_RELPATH
from startd8.presentation_polish.provider import PresentationPolishFileProvider

pytestmark = []


def _polished(tmp_path, theme="professional"):
    (tmp_path / "app").mkdir()
    apply_polish(PolishConfig(project_root=tmp_path, theme=theme))
    return tmp_path


def test_owns_only_marked_files():
    p = PresentationPolishFileProvider()
    assert p.owns(Path("app/static/css/app.css"), "/* STARTD8-POLISH v1 */\nbody{}")
    assert not p.owns(Path("app/models.py"), "# GENERATED from schema\n")


def test_in_sync_true_for_freshly_applied(tmp_path):
    root = _polished(tmp_path)
    p = PresentationPolishFileProvider()
    css_path = root / STYLESHEET_RELPATH
    content = css_path.read_text()
    ctx = ProviderContext(project_root=root)
    assert p.owns(css_path, content)
    assert p.is_in_sync(css_path, content, ctx)


def test_in_sync_false_when_tampered(tmp_path):
    root = _polished(tmp_path)
    p = PresentationPolishFileProvider()
    css_path = root / STYLESHEET_RELPATH
    tampered = css_path.read_text() + "\n/* STARTD8-POLISH but edited */\n"
    ctx = ProviderContext(project_root=root)
    assert p.owns(css_path, tampered)
    assert not p.is_in_sync(css_path, tampered, ctx)


def test_in_sync_false_without_manifest(tmp_path):
    root = _polished(tmp_path)
    (root / ".startd8" / "polish-manifest.json").unlink()
    p = PresentationPolishFileProvider()
    css_path = root / STYLESHEET_RELPATH
    ctx = ProviderContext(project_root=root)
    # cannot verify theme → safe "not in sync"
    assert not p.is_in_sync(css_path, css_path.read_text(), ctx)


def test_registered_at_entry_point():
    # the provider is discoverable via the deterministic-providers registry
    from startd8.contractors import deterministic_providers as dp

    dp.clear_providers()
    dp.discover(force=True)
    names = {getattr(prov, "name", None) for prov in dp._PROVIDERS}
    assert "presentation-polish" in names
