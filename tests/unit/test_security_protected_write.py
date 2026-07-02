"""FR-A6a: generation must not write operator control files (protected-path write guard).

An injected instruction could steer generation to emit a project-root ``security_allowlist.yaml``
that suppresses Anzen-gate findings. The guard refuses that write (canonicalizing the path first to
defeat ``..``/symlink/case-fold bypass). See prompt-injection-prevention REQUIREMENTS FR-A6a (R1-S4).
"""

import pytest

from startd8.exceptions import ValidationError
from startd8.security import (
    PROTECTED_CONTROL_FILES,
    assert_writable_generated_target,
    is_protected_control_file,
)

_BASE = "/tmp/proj"


@pytest.mark.parametrize("path", [
    "security_allowlist.yaml",
    "sub/dir/security_allowlist.yaml",
    "SECURITY_ALLOWLIST.YAML",          # case-fold (case-insensitive FS bypass)
    "x/../security_allowlist.yaml",      # traversal canonicalized
    ".contextcore.yaml",
])
def test_protected_control_files_are_caught(path):
    assert is_protected_control_file(path, _BASE)
    with pytest.raises(ValidationError):
        assert_writable_generated_target(path, _BASE)


@pytest.mark.parametrize("path", [
    "app/models.py",
    "src/main.py",
    "allowlist_helper.py",       # substring, not the control file
    "docs/security_notes.md",
])
def test_normal_generated_targets_pass(path):
    assert not is_protected_control_file(path, _BASE)
    assert assert_writable_generated_target(path, _BASE)  # returns the Path, no raise


def test_protected_set_includes_the_security_allowlist():
    assert "security_allowlist.yaml" in PROTECTED_CONTROL_FILES


def test_guarded_write_skips_protected_and_logs(tmp_path, caplog):
    """The integration-engine helper refuses a protected write (skip + log), not crash."""
    import logging
    from startd8.contractors.integration_engine import _guarded_write

    evil = tmp_path / "security_allowlist.yaml"
    with caplog.at_level(logging.WARNING):
        wrote = _guarded_write(evil, "entries: [...]", tmp_path)
    assert wrote is False
    assert not evil.exists()            # the malicious control file never landed
    assert any(getattr(r, "event", None) == "protected_control_file_write_refused"
               for r in caplog.records)


def test_guarded_write_allows_normal_target(tmp_path):
    from startd8.contractors.integration_engine import _guarded_write

    good = tmp_path / "app" / "models.py"
    good.parent.mkdir(parents=True)
    assert _guarded_write(good, "print('ok')", tmp_path) is True
    assert good.read_text() == "print('ok')"
