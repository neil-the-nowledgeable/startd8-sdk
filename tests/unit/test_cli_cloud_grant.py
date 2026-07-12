"""M4b — the `startd8 cloud-grant issue|revoke|list` operator CLI (OQ-4 control-plane surface).

The CLI is the human/operator side (issuance); the served app is the consume-only side. These tests
prove the round-trip: what the CLI issues into the store, a FileGrantStore (the served app) can consume.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from startd8.cli_cloud_grant import cloud_grant_app  # noqa: E402
from startd8.kickoff_experience.cloud_grant import FileGrantStore, GrantTarget  # noqa: E402

runner = CliRunner()
TGT = GrantTarget("dep-1", "proj", "chat-write")


def _paths(tmp_path):
    return str(tmp_path / "grants.json"), str(tmp_path / "audit.jsonl")


def _issue(tmp_path, *extra):
    store, audit = _paths(tmp_path)
    args = ["issue", "--deployment", "dep-1", "--project", "proj", "--issued-by", "ops:alice",
            "--store", store, "--audit", audit, *extra]
    return runner.invoke(cloud_grant_app, args), store, audit


def test_issue_writes_grant_and_audit(tmp_path):
    r, store, audit = _issue(tmp_path)
    assert r.exit_code == 0 and "grant issued" in r.output
    grants = json.loads(Path(store).read_text())
    assert len(grants) == 1
    g = next(iter(grants.values()))
    assert g["deployment_id"] == "dep-1" and g["capability"] == "chat-write" and g["uses_remaining"] == 1
    assert g["issued_by"] == "ops:alice"
    assert Path(audit).read_text().count('"event": "issue"') == 1


def test_issued_grant_is_consumable_by_the_served_app(tmp_path):
    # The whole point: the CLI's out-of-band write is visible to + consumable by the served-app store.
    r, store, _ = _issue(tmp_path, "--uses", "1", "--ttl", "600")
    assert r.exit_code == 0
    import time
    d = FileGrantStore(store).resolve_and_consume(TGT, now=time.time())
    assert d.allowed is True and d.uses_remaining_after == 0


def test_issue_is_fail_closed_when_store_is_unwritable(tmp_path):
    # Point --store at a path whose parent is a FILE → mkdir/persist fails → exit 1, no grant.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    store = str(blocker / "grants.json")   # parent 'blocker' is a file, not a dir
    r = runner.invoke(cloud_grant_app, ["issue", "--deployment", "d", "--project", "p",
                                        "--issued-by", "op", "--store", store,
                                        "--audit", str(tmp_path / "a.jsonl")])
    assert r.exit_code == 1 and "fail-closed" in r.output


def test_list_empty_and_populated(tmp_path):
    store, _ = _paths(tmp_path)
    empty = runner.invoke(cloud_grant_app, ["list", "--store", store])
    assert empty.exit_code == 0 and "no grants" in empty.output
    _issue(tmp_path)
    r = runner.invoke(cloud_grant_app, ["list", "--store", store])
    assert r.exit_code == 0 and "live" in r.output and "dep-1/proj/chat-write" in r.output


def test_revoke_marks_revoked_and_unknown_id_exits_2(tmp_path):
    r, store, audit = _issue(tmp_path)
    gid = next(iter(json.loads(Path(store).read_text())))
    ok = runner.invoke(cloud_grant_app, ["revoke", gid, "--store", store, "--audit", audit])
    assert ok.exit_code == 0 and "revoked" in ok.output
    assert json.loads(Path(store).read_text())[gid]["revoked"] is True
    missing = runner.invoke(cloud_grant_app, ["revoke", "nope", "--store", store, "--audit", audit])
    assert missing.exit_code == 2


def test_for_serve_derives_project_from_dir_name(tmp_path):
    proj = tmp_path / "my-deployment"
    proj.mkdir()
    store, audit = _paths(tmp_path)
    r = runner.invoke(cloud_grant_app, ["issue", "--deployment", "d", "--for-serve", str(proj),
                                        "--issued-by", "op", "--store", store, "--audit", audit])
    assert r.exit_code == 0
    g = next(iter(json.loads(Path(store).read_text()).values()))
    assert g["project_id"] == "my-deployment"   # derived from the dir name (matches serve default)


def test_human_ttl_and_env_deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("STARTD8_DEPLOYMENT_ID", "dep-from-env")
    store, audit = _paths(tmp_path)
    r = runner.invoke(cloud_grant_app, ["issue", "--project", "p", "--ttl", "30m",
                                        "--issued-by", "op", "--store", store, "--audit", audit])
    assert r.exit_code == 0
    g = next(iter(json.loads(Path(store).read_text()).values()))
    assert g["deployment_id"] == "dep-from-env"                 # env default used
    assert abs((g["expires_at"] - g["issued_at"]) - 1800.0) < 1.0   # 30m == 1800s


def test_issue_requires_project_or_for_serve(tmp_path):
    store, audit = _paths(tmp_path)
    r = runner.invoke(cloud_grant_app, ["issue", "--deployment", "d", "--issued-by", "op",
                                        "--store", store, "--audit", audit])
    assert r.exit_code == 2 and "--project or --for-serve" in r.output


def test_status_summarizes_audit(tmp_path):
    r, store, audit = _issue(tmp_path)
    from startd8.kickoff_experience.cloud_grant import FileGrantStore as _FS, AuditLog as _AL
    import time as _t
    _FS(store, audit=_AL(audit)).resolve_and_consume(TGT, now=_t.time())   # a consume event
    out = runner.invoke(cloud_grant_app, ["status", "--audit", audit])
    assert out.exit_code == 0 and "issue=1" in out.output and "consume=1" in out.output


def test_gc_prunes_revoked(tmp_path):
    r, store, audit = _issue(tmp_path)
    gid = next(iter(json.loads(Path(store).read_text())))
    runner.invoke(cloud_grant_app, ["revoke", gid, "--store", store, "--audit", audit])
    out = runner.invoke(cloud_grant_app, ["gc", "--store", store])
    assert out.exit_code == 0 and "pruned 1" in out.output
    assert json.loads(Path(store).read_text()) == {}


def test_list_live_only(tmp_path):
    r, store, audit = _issue(tmp_path)
    gid = next(iter(json.loads(Path(store).read_text())))
    runner.invoke(cloud_grant_app, ["revoke", gid, "--store", store, "--audit", audit])
    out = runner.invoke(cloud_grant_app, ["list", "--store", store, "--live-only"])
    assert out.exit_code == 0 and "no grants" in out.output   # the only grant is revoked → filtered out
