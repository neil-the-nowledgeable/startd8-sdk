"""M-E — the post-mortem mypy filter must stop swallowing first-party import errors (C-3).

run-021/023/024/025 all shipped wrong first-party imports (`from app.models import AiCall` when it
lives in app.tables; `from ai.x` with the wrong package root) that produce mypy `import-not-found` —
which the old blanket filter discarded as "provisioning noise", manufacturing a green PASS. The fix:
third-party absence stays noise; first-party (`app.*`) absence is a real fault.
"""

from dataclasses import dataclass

from startd8.contractors.prime_postmortem import (
    _first_party_roots,
    _is_import_provisioning_noise,
)


@dataclass
class _Diag:
    code: str
    message: str


ROOTS = {"app", "ai"}


def test_third_party_import_is_noise():
    d = _Diag(
        "import-not-found",
        'Cannot find implementation or library stub for module named "fastapi"',
    )
    assert _is_import_provisioning_noise(d, ROOTS) is True


def test_first_party_import_is_real_fault_not_noise():
    # the run-023 bug: `from ai.artifacts import ...` (wrong root) — must NOT be filtered
    d = _Diag(
        "import-not-found",
        'Cannot find implementation or library stub for module named "ai.artifacts"',
    )
    assert _is_import_provisioning_noise(d, ROOTS) is False


def test_first_party_app_module_is_real_fault():
    d = _Diag("import-not-found", 'Cannot find module named "app.models"')
    assert _is_import_provisioning_noise(d, ROOTS) is False


def test_non_import_diagnostic_is_never_noise():
    d = _Diag("name-defined", 'Name "AiCall" is not defined')
    assert _is_import_provisioning_noise(d, ROOTS) is False


def test_import_diag_without_parseable_module_defaults_to_noise():
    # no `module named "X"` to inspect → conservative: treat as third-party noise
    d = _Diag("import-untyped", "Skipping analyzing something: module is installed but untyped")
    assert _is_import_provisioning_noise(d, ROOTS) is True


def test_first_party_roots_includes_app_and_disk_packages(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "notapkg").mkdir()  # no __init__.py → not importable, not first-party

    roots = _first_party_roots(str(tmp_path))

    assert {"app", "svc", "helper"} <= roots
    assert "notapkg" not in roots


def test_app_is_always_first_party_even_if_dir_absent(tmp_path):
    # the codegen convention: `app` counts even before it's written
    assert "app" in _first_party_roots(str(tmp_path))
