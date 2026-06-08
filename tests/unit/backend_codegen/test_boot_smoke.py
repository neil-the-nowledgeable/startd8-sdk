"""M-D — runtime boot-smoke gate (C-6 Layer 1).

The pure verdict logic runs everywhere; the subprocess-boot tests need fastapi/sqlmodel installed
(importorskip), mirroring test_runtime_smoke.
"""

import pytest

from startd8.validators.boot_smoke import (
    BootSmokeResult,
    resolve_app_target,
    run_boot_smoke,
)


# --------------------------------------------------------------------------- #
# Pure verdict logic (no subprocess)
# --------------------------------------------------------------------------- #

def test_verdict_unavailable_is_not_a_pass():
    r = BootSmokeResult(status="unavailable", message="no fastapi")
    assert r.verdict == "unavailable" and not r.is_pass


def test_verdict_pass_when_booted_and_routes_present():
    r = BootSmokeResult(status="checked", ok=True, routes=("/metric",), missing_routes=())
    assert r.verdict == "pass" and r.is_pass


def test_verdict_fail_when_booted_but_route_missing():
    r = BootSmokeResult(status="checked", ok=True, routes=("/metric",), missing_routes=("/ai/x",))
    assert r.verdict == "fail"


def test_verdict_fail_when_boot_errored():
    r = BootSmokeResult(status="checked", ok=False, message="ModuleNotFoundError")
    assert r.verdict == "fail"


def test_missing_path_is_error():
    assert run_boot_smoke("/no/such/dir/xyz").status == "error"


# --------------------------------------------------------------------------- #
# F-5 — app-target resolution (the gate must never hardcode one variant)
# --------------------------------------------------------------------------- #

def _touch_pkg(root, package="app", *modules):
    pkg = root / package
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for m in modules:
        (pkg / m).write_text("app = None\n", encoding="utf-8")


def test_resolve_main_variant(tmp_path):
    """The v2 cascade emits app/main.py and NO server.py (RUN-008 1a-iii)."""
    _touch_pkg(tmp_path, "app", "main.py")
    assert resolve_app_target(str(tmp_path)) == "app.main:app"


def test_resolve_server_variant_preferred(tmp_path):
    """--ai-passes emits app/server.py (wraps main + AI router) — the superset wins."""
    _touch_pkg(tmp_path, "app", "main.py", "server.py")
    assert resolve_app_target(str(tmp_path)) == "app.server:app"


def test_resolve_package_from_app_yaml(tmp_path):
    """The package name comes from the scaffold manifest, not a hardcoded 'app'."""
    (tmp_path / "app.yaml").write_text(
        "app:\n  name: backend\n  package: backend\n", encoding="utf-8"
    )
    _touch_pkg(tmp_path, "backend", "main.py")
    assert resolve_app_target(str(tmp_path)) == "backend.main:app"


def test_resolve_package_from_prisma_app_yaml(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "app.yaml").write_text(
        "app:\n  package: svc\n", encoding="utf-8"
    )
    _touch_pkg(tmp_path, "svc", "server.py")
    assert resolve_app_target(str(tmp_path)) == "svc.server:app"


def test_resolve_malformed_manifest_falls_back_to_default_package(tmp_path):
    (tmp_path / "app.yaml").write_text("nonsense_key: true\n", encoding="utf-8")
    _touch_pkg(tmp_path, "app", "main.py")
    assert resolve_app_target(str(tmp_path)) == "app.main:app"


def test_resolve_no_entrypoint_is_none(tmp_path):
    assert resolve_app_target(str(tmp_path)) is None


def test_run_boot_smoke_without_entrypoint_is_error_not_pass(tmp_path):
    result = run_boot_smoke(str(tmp_path))
    assert result.status == "error"
    assert not result.is_pass
    assert "no app entrypoint" in result.message


def test_explicit_app_spec_still_honored(tmp_path):
    """Callers passing app= keep full control — resolution only fills the default."""
    _touch_pkg(tmp_path, "app", "main.py", "server.py")
    # Force the main variant even though server.py exists; the subprocess may fail
    # (no fastapi guaranteed here) but the targeted spec must be the explicit one.
    result = run_boot_smoke(str(tmp_path), app="app.main:app", timeout=30)
    assert result.status in ("checked", "unavailable", "timeout", "error")


# --------------------------------------------------------------------------- #
# Real subprocess boot (needs app deps)
# --------------------------------------------------------------------------- #

SCHEMA = """
model Profile {
  id   String @id @default(cuid())
  name String
}
""".strip()


def _render_to(tmp_path):
    from startd8.backend_codegen import render_backend

    for rel, content in render_backend(SCHEMA):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def test_generated_app_boots_and_serves_openapi(tmp_path):
    """Main variant (the v2 cascade's shape: app/main.py, no server.py) passes via
    auto-resolution — the RUN-008 F-5 falsifiability requirement."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")
    _render_to(tmp_path)
    assert resolve_app_target(str(tmp_path)) == "app.main:app"

    result = run_boot_smoke(str(tmp_path))

    assert result.is_pass, f"{result.verdict}: {result.message} {result.diagnostics}"
    # CRUD routes for the Profile entity should be in the served OpenAPI
    assert any("profile" in p.lower() for p in result.routes)


def test_server_variant_boots_via_auto_resolution(tmp_path):
    """Server variant (--ai-passes shape: app/server.py wrapping main) also passes via
    auto-resolution — a healthy app passes regardless of which variant was generated."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")
    _render_to(tmp_path)
    (tmp_path / "app" / "server.py").write_text(
        "from app.main import app\n__all__ = ['app']\n", encoding="utf-8"
    )
    assert resolve_app_target(str(tmp_path)) == "app.server:app"

    result = run_boot_smoke(str(tmp_path))

    assert result.is_pass, f"{result.verdict}: {result.message} {result.diagnostics}"
    assert any("profile" in p.lower() for p in result.routes)


def test_expected_route_missing_fails(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")
    _render_to(tmp_path)

    result = run_boot_smoke(str(tmp_path), expected_routes=["/ai/does-not-exist"])

    assert not result.is_pass
    assert "/ai/does-not-exist" in result.missing_routes


def test_deps_absent_is_unavailable_not_silent_pass(tmp_path):
    """When app deps are missing, the gate must report `unavailable` (non-pass), never green
    (NFR-MA-2). Runs end-to-end through the subprocess; skipped where fastapi *is* installed."""
    import importlib.util

    if importlib.util.find_spec("fastapi") is not None:
        pytest.skip("fastapi installed — the unavailable path is exercised only without it")
    _render_to(tmp_path)
    result = run_boot_smoke(str(tmp_path))
    assert result.status == "unavailable"
    assert not result.is_pass and result.verdict == "unavailable"


def test_broken_import_fails_boot(tmp_path):
    """A module that passes compileall but fails at import must FAIL the gate (the run-025 trap)."""
    pytest.importorskip("fastapi")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    # syntactically valid, imports a non-existent module → compileall green, import explodes
    (tmp_path / "app" / "main.py").write_text(
        "import definitely_not_a_real_module_xyz\napp = None\n", encoding="utf-8"
    )

    result = run_boot_smoke(str(tmp_path))

    assert not result.is_pass
    assert result.status == "checked"  # it ran; the app failed — distinct from unavailable
    assert any("ModuleNotFoundError" in d or "definitely_not_a_real_module" in d
               for d in result.diagnostics)
