"""FR-E15 — `cloud-grant invite`: packages the remote-onboarding flow (issue grant+link, generate the
key, print the operator playbook). It must issue a real, redeemable, link-bearing grant and print the
exact serve command + link + review/apply steps."""
from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.cli_cloud_grant import cloud_grant_app  # noqa: E402
from startd8.kickoff_experience.cloud_grant import GrantTarget, open_grant_store  # noqa: E402

runner = CliRunner()


def _invite(tmp_path, *extra):
    proj = tmp_path / "benchmark-portal"
    proj.mkdir()
    store = tmp_path / "g.json"
    args = ["invite", "--for-serve", str(proj), "--serve-url", "https://app.example/",
            "--cloud-origin", "https://app.example", "--issued-by", "ops", "--deployment", "prod-1",
            "--store", str(store), "--audit", str(tmp_path / "a.jsonl"), *extra]
    # COLUMNS wide so Rich doesn't wrap the long serve command / link mid-token in the test terminal.
    return runner.invoke(cloud_grant_app, args, env={"COLUMNS": "400"}), proj, store


def test_invite_prints_the_full_playbook(tmp_path):
    r, proj, store = _invite(tmp_path)
    assert r.exit_code == 0, r.output
    out = r.output
    # the 4 steps + the serve command flags + the link + the revoke escape hatch
    assert "1. Start the server" in out and "2. Send this ONE-TIME link" in out
    assert "3. Review what they proposed" in out and "4. Apply the ones you accept" in out
    assert "startd8 kickoff start" in out and "--cloud" in out and "--grant-store" in out
    assert "--deployment-id prod-1" in out and "--cloud-origin https://app.example" in out
    assert "https://app.example/kickoff/enter?t=" in out
    assert "vipp negotiate" in out and "vipp apply" in out
    assert "cloud-grant revoke" in out


def test_invite_generates_a_consumer_key_when_omitted(tmp_path):
    r, _, _ = _invite(tmp_path)
    assert "--api-key sk-kickoff-" in r.output          # a random key baked into the serve command


def test_invite_honors_an_explicit_key(tmp_path):
    r, _, _ = _invite(tmp_path, "--api-key", "sk-mine-123")
    assert "--api-key sk-mine-123" in r.output


def test_invite_issues_a_redeemable_link_grant(tmp_path):
    # The printed link must actually work: extract its token, and redeem it against the written store.
    r, proj, store = _invite(tmp_path)
    token = r.output.split("kickoff/enter?t=", 1)[1].split()[0].strip()
    target = GrantTarget("prod-1", "benchmark-portal", "chat-write")
    s = open_grant_store(store)
    dec = s.redeem_link(token, target, now=0.0)
    assert dec.allowed                                  # a real, live, target-bound grant
    # one-time: a second redemption is denied (burned)
    assert not s.redeem_link(token, target, now=0.0).allowed


def test_invite_requires_deployment(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    r = runner.invoke(cloud_grant_app, [
        "invite", "--for-serve", str(proj), "--serve-url", "https://x", "--cloud-origin", "https://x",
        "--issued-by", "ops", "--store", str(tmp_path / "g.json"), "--audit", str(tmp_path / "a.jsonl"),
    ])
    assert r.exit_code == 2 and "--deployment" in r.output
