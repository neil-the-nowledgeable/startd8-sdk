"""P1 secure provisioning (provision.py) — pure-logic guards (no live installs; injected runner)."""
from __future__ import annotations

import startd8.benchmark_matrix.behavioral.provision as prov
from startd8.benchmark_matrix.behavioral.provision import (
    install_plan,
    provision_workdir,
    secure_env,
)


def test_install_plan_is_scripts_disabled_and_unsupported_degrades(tmp_path):
    go = install_plan("go", tmp_path, ["src/shippingservice/main.go"])
    assert go[0] == ["go", "mod", "tidy"] and go[1].name == "shippingservice"
    argv, _ = install_plan("python", tmp_path, ["src/emailservice/email_server.py"])
    assert "--only-binary=:all:" in argv and "grpcio" in argv and "--target" in argv  # SEC-1 + common set
    assert install_plan("java", tmp_path, ["X.java"]) is None  # secure path not built → degrade


def test_secure_env_scrubs_secrets_and_isolates_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.tok")
    env = secure_env(tmp_path)
    assert "ANTHROPIC_API_KEY" not in env and "DOPPLER_TOKEN" not in env  # FR-P1-SEC-2 / FR-45
    assert env["GOMODCACHE"].startswith(str(tmp_path)) and env["PIP_CACHE_DIR"].startswith(str(tmp_path))  # SEC-5


def test_secure_env_cache_paths_are_absolute(tmp_path, monkeypatch):
    # Go requires GOMODCACHE absolute; a relative workdir (e.g. the rescore's batch-relative path)
    # must still produce absolute cache paths.
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    env = secure_env(Path("relcell"))
    assert Path(env["GOMODCACHE"]).is_absolute() and Path(env["GOCACHE"]).is_absolute()


def test_provision_ok_and_failure(tmp_path):
    seen = {}

    def ok(argv, cwd, env, timeout):
        seen["env"] = env
        return 0, ""

    r = provision_workdir(tmp_path, "go", ["src/shippingservice/main.go"], runner=ok)
    assert r.ok and "scripts-disabled" in r.controls and "scrubbed-env" in r.controls
    assert "ANTHROPIC_API_KEY" not in seen["env"]  # the installer never sees secrets

    r2 = provision_workdir(tmp_path, "go", ["src/shippingservice/main.go"], runner=lambda *a: (1, "boom"))
    assert not r2.ok and "provision failed" in r2.degraded_reason


def test_provision_offline_fails_closed(tmp_path):
    r = provision_workdir(tmp_path, "python", ["src/emailservice/x.py"], offline=True, runner=lambda *a: (0, ""))
    assert not r.ok and "offline" in r.degraded_reason  # FR-P1-SEC-3


def test_provision_unsupported_skips_and_toolchain_absent_degrades(tmp_path, monkeypatch):
    # No secure strategy yet (java) → SKIP + proceed (don't fail the cell; never run untrusted gradle).
    r = provision_workdir(tmp_path, "java", ["X.java"], runner=lambda *a: (0, ""))
    assert r.ok and r.controls == "skipped"
    # But a SUPPORTED language whose toolchain is missing → degrade (FR-P1-5).
    monkeypatch.setattr(prov.shutil, "which", lambda t: None)
    r2 = provision_workdir(tmp_path, "go", ["src/x/main.go"], runner=lambda *a: (0, ""))
    assert not r2.ok and "toolchain absent" in r2.degraded_reason
