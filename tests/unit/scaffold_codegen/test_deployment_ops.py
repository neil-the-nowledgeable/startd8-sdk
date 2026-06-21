"""Deployment-mode M1 ops — A4 (run.sh / container bind by mode) + A7 (coherence guard).

A4 (FR-NET-1/2): the local run.sh binds loopback (installed) / all-interfaces (deployed); the
Dockerfile always binds 0.0.0.0 but its body + hash vary by mode (R1-S5). A7 (FR-CFG-5): the
normative ERROR/WARN/OK coherence matrix, enforced by `generate backend` when an app.yaml is given.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app
from startd8.scaffold_codegen import (
    parse_app_manifest,
    render_dockerfile,
    render_env_example,
    render_run_script,
    render_scaffold,
    scaffold_in_sync,
)
from startd8.scaffold_codegen.coherence import (
    ERROR,
    WARN,
    evaluate_coherence,
    has_errors,
)
from startd8.scaffold_codegen.drift import embedded_manifest_sha

pytestmark = pytest.mark.unit

runner = CliRunner()

INSTALLED_YAML = "app:\n  name: demo\n  package: app\n"  # no deployment block -> installed default
DEPLOYED_PG = (
    "app:\n  name: demo\n  package: app\n"
    "deployment:\n  mode: deployed\n"
    "persistence:\n  path: postgresql://db/app\n"
)
# DEPLOYED_PG + a gateway acknowledgement → clears the FR-CND-6 fail-closed identity ERROR, so a
# real deployed build (which emits the decode-only auth seam) succeeds.
DEPLOYED_PG_TRUSTED = DEPLOYED_PG + "deploy:\n  trust_gateway: true\n"
DEPLOYED_DEFAULT = "deployment:\n  mode: deployed\n"  # db_path defaults to ./data/app.db (sqlite)

SCHEMA = "model Profile {\n  id   String @id\n  name String\n}\n"


# --- A4: run.sh bind is mode-derived; Dockerfile stays 0.0.0.0 but varies by mode ----------------

def test_run_script_bind_is_mode_derived():
    installed = render_run_script(INSTALLED_YAML)
    deployed = render_run_script(DEPLOYED_PG)
    assert installed.startswith("#!/usr/bin/env bash\n")  # shebang line 1 (executable)
    assert "--host 127.0.0.1" in installed
    assert "--host 0.0.0.0" in deployed
    assert "# startd8-artifact: scaffold-run-script" in installed  # owned/drift-tracked


def test_dockerfile_always_binds_all_interfaces_but_body_varies_by_mode():
    installed = render_dockerfile(INSTALLED_YAML)
    deployed = render_dockerfile(DEPLOYED_PG)
    assert '"--host", "0.0.0.0"' in installed and '"--host", "0.0.0.0"' in deployed  # container reach
    assert installed != deployed  # the mode comment differs
    assert "deployment mode: installed" in installed and "deployment mode: deployed" in deployed


def test_run_sh_is_in_scaffold_set_and_drift_checks():
    files = dict(render_scaffold(INSTALLED_YAML))
    assert "run.sh" in files
    run = files["run.sh"]
    assert scaffold_in_sync(INSTALLED_YAML, run) is True
    tampered = run.replace("127.0.0.1", "0.0.0.0")  # hand-edit the bind
    assert scaffold_in_sync(INSTALLED_YAML, tampered) is False


def test_r1_s5_mode_is_in_the_scaffold_hash_and_artifacts_differ():
    # Mode flip changes app.yaml text -> different manifest-sha256 in EVERY scaffold artifact header
    # (so --check sees the flip, FR-DET-1), and the mode-varying bodies differ too.
    i_files, d_files = dict(render_scaffold(INSTALLED_YAML)), dict(render_scaffold(DEPLOYED_PG))
    assert embedded_manifest_sha(i_files["Dockerfile"]) != embedded_manifest_sha(d_files["Dockerfile"])
    assert i_files["run.sh"] != d_files["run.sh"]


# --- A5: .env.example secrets/observability defaults are mode-derived (FR-SEC-1/FR-OBS-1) ----------

def test_env_installed_defaults():
    env = render_env_example(INSTALLED_YAML)
    assert "ENV=development" in env  # OTel deployment.environment aligned with mode
    assert "DATABASE_URL=sqlite:///" in env  # local-first default
    assert "STARTD8_SECRETS_BACKEND" not in env  # local backend is the default; no entry needed


def test_env_deployed_defaults():
    env = render_env_example(DEPLOYED_PG)
    assert "ENV=production" in env
    assert "DATABASE_URL=postgresql://db/app" in env  # full DSN honored, not sqlite:///-prefixed
    assert "STARTD8_SECRETS_BACKEND=doppler" in env  # external secrets manager expected
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=" in env  # centralized OTel export expected


def test_env_is_owned_and_drift_checks():
    env = render_env_example(DEPLOYED_PG)
    assert scaffold_in_sync(DEPLOYED_PG, env) is True
    assert scaffold_in_sync(DEPLOYED_PG, env.replace("doppler", "vault")) is False


# --- A7: the FR-CFG-5 coherence matrix -----------------------------------------------------------

@pytest.mark.parametrize(
    "yaml_text, kwargs, expect_codes",
    [
        (INSTALLED_YAML, {}, []),                                   # installed + sqlite default -> OK
        (DEPLOYED_PG, {}, []),                                      # deployed + postgres + migrations -> OK
        (DEPLOYED_DEFAULT, {}, ["deployed-sqlite-file"]),          # deployed + sqlite file -> ERROR
        ("deployment:\n  mode: deployed\npersistence:\n  path: 'sqlite:///:memory:'\n",
         {}, ["deployed-sqlite-memory"]),                          # deployed + :memory: -> WARN
        ("deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
         "migrations:\n  enabled: false\n", {}, ["deployed-no-migrations"]),  # ERROR
        ("app:\n  name: d\npersistence:\n  path: postgresql://db/app\n", {},
         ["installed-shared-dsn"]),                                # installed + shared DSN -> ERROR
        (DEPLOYED_PG, {"has_auth_seam": True, "has_tenant": False},
         ["deployed-auth-no-tenant", "deployed-decode-only-no-gateway-ack"]),  # WARN + fail-closed ERROR
        (DEPLOYED_PG_TRUSTED, {"has_auth_seam": True, "has_tenant": False},
         ["deployed-auth-no-tenant"]),                             # trust_gateway clears the security ERROR
        (INSTALLED_YAML, {"has_auth_seam": True}, ["installed-auth-requested"]),  # ERROR
    ],
)
def test_coherence_matrix(yaml_text, kwargs, expect_codes):
    findings = evaluate_coherence(parse_app_manifest(yaml_text), **kwargs)
    assert sorted(f.code for f in findings) == sorted(expect_codes)


def test_has_errors_distinguishes_severity():
    err = evaluate_coherence(parse_app_manifest(DEPLOYED_DEFAULT))
    assert has_errors(err) and err[0].severity == ERROR
    memory = "deployment:\n  mode: deployed\npersistence:\n  path: 'sqlite:///:memory:'\n"
    warn = evaluate_coherence(parse_app_manifest(memory))
    assert not has_errors(warn) and warn[0].severity == WARN


# --- M0: the cloud-native `deploy:` block (strict-keyed) -----------------------------------------

def test_deploy_block_parses_fields():
    m = parse_app_manifest(
        "deployment:\n  mode: deployed\n"
        "deploy:\n  trust_gateway: true\n  target_cloud: gke\n  secrets:\n    backend: eso-doppler\n"
    )
    assert m.deploy_trust_gateway is True
    assert m.deploy_target_cloud == "gke"
    assert m.deploy_secrets_backend == "eso-doppler"


def test_deploy_block_defaults_fail_closed():
    m = parse_app_manifest("deployment:\n  mode: deployed\n")  # no deploy block
    assert m.deploy_trust_gateway is False  # default = fail-closed


def test_deploy_block_unknown_key_errors():
    with pytest.raises(ValueError, match="deploy.*unknown keys"):
        parse_app_manifest("deploy:\n  trust_gatewy: true\n")  # typo


def test_deploy_secrets_backend_validated():
    with pytest.raises(ValueError, match="secrets.backend"):
        parse_app_manifest("deploy:\n  secrets:\n    backend: vault\n")  # not an allowed backend


# --- DEPLOY_ENVIRONMENTS M0: the deploy.environments grammar (FR-ENV-1/2) ------------------------

_ENVS_YAML = (
    "deployment:\n  mode: deployed\n"
    "deploy:\n  trust_gateway: true\n  environments:\n"
    "    prod:\n      replicas: 3\n    dev:\n      log_level: debug\n    test: {}\n"
)


def test_environments_parse_sorted_for_byte_stability():
    m = parse_app_manifest(_ENVS_YAML)
    assert m.deploy_environments == ("dev", "prod", "test")  # sorted, not insertion order
    assert m.has_environments is True


def test_no_environments_is_empty_sotto():
    m = parse_app_manifest("deployment:\n  mode: deployed\ndeploy:\n  trust_gateway: true\n")
    assert m.deploy_environments == () and m.has_environments is False  # absent → none (no overlays)


def test_environment_unknown_override_key_errors():
    with pytest.raises(ValueError, match="environments.prod.*unknown keys"):
        parse_app_manifest("deploy:\n  environments:\n    prod:\n      replcas: 3\n")  # typo


def test_environments_must_be_mapping():
    with pytest.raises(ValueError, match="environments` must be a mapping"):
        parse_app_manifest("deploy:\n  environments:\n    - dev\n    - prod\n")  # list, not mapping


def test_installed_with_environments_is_coherence_error():
    m = parse_app_manifest(
        "deployment:\n  mode: installed\ndeploy:\n  environments:\n    dev: {}\n"
    )
    codes = {f.code: f.severity for f in evaluate_coherence(m)}
    assert codes.get("installed-with-environments") == ERROR  # FR-ENV-2 guard


def test_environment_specs_carry_overrides():
    m = parse_app_manifest(_ENVS_YAML)
    specs = {s.name: s for s in m.deploy_environment_specs}
    assert specs["prod"].has_replicas is True and specs["prod"].secrets_config is None
    assert specs["dev"].log_level == "debug"


def test_m3_inconsistent_secrets_scope_warns():
    """M3: some envs pin secrets_config, others don't → cross-env secret-bleed WARN (FR-ENV-7)."""
    yaml_text = (
        "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
        "deploy:\n  trust_gateway: true\n  environments:\n"
        "    prod:\n      secrets_config: prd\n    dev: {}\n"
    )
    m = parse_app_manifest(yaml_text)
    codes = {f.code: f for f in evaluate_coherence(m, has_auth_seam=True)}
    f = codes.get("env-inconsistent-secrets-scope")
    assert f is not None and f.severity == WARN and "dev" in f.message


def test_m3_consistent_secrets_scope_no_warn():
    yaml_text = (
        "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
        "deploy:\n  trust_gateway: true\n  environments:\n"
        "    prod:\n      secrets_config: prd\n    dev:\n      secrets_config: dev\n"
    )
    m = parse_app_manifest(yaml_text)
    codes = {f.code for f in evaluate_coherence(m, has_auth_seam=True)}
    assert "env-inconsistent-secrets-scope" not in codes  # all pinned → no warn


# --- A7 wired into `generate backend` ------------------------------------------------------------

def _schema(tmp_path):
    p = tmp_path / "schema.prisma"
    p.write_text(SCHEMA, encoding="utf-8")
    return p


def test_cli_coherence_error_blocks_the_build(tmp_path):
    schema = _schema(tmp_path)
    manifest = tmp_path / "app.yaml"
    manifest.write_text(DEPLOYED_DEFAULT, encoding="utf-8")  # deployed + sqlite -> ERROR
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--app-manifest", str(manifest)],
    )
    assert res.exit_code != 0
    assert "deployed-sqlite-file" in res.output
    assert not (tmp_path / "app" / "settings.py").exists()  # build refused before writing


def test_cli_coherent_deployed_builds(tmp_path):
    schema = _schema(tmp_path)
    manifest = tmp_path / "app.yaml"
    manifest.write_text(DEPLOYED_PG_TRUSTED, encoding="utf-8")  # deployed + postgres + gateway ack -> OK
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--app-manifest", str(manifest)],
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / "app" / "settings.py").exists()
