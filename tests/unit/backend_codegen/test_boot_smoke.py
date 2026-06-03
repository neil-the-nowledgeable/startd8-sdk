"""M-D — runtime boot-smoke gate (C-6 Layer 1).

The pure verdict logic runs everywhere; the subprocess-boot tests need fastapi/sqlmodel installed
(importorskip), mirroring test_runtime_smoke.
"""

import pytest

from startd8.validators.boot_smoke import BootSmokeResult, run_boot_smoke


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
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")
    _render_to(tmp_path)

    result = run_boot_smoke(str(tmp_path))

    assert result.is_pass, f"{result.verdict}: {result.message} {result.diagnostics}"
    # CRUD routes for the Profile entity should be in the served OpenAPI
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
