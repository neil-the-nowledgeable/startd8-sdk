"""Tests for the Workbook cockpit generation (post-M4 convergence).

The Workbook is the pure-Python v2 cockpit + a v2 dashlist index (no jsonnet). Covers: the default
`kickoff portal` → cockpit, the M3.1 auto-refresh reroute (instantiate/confirm build the cockpit),
the M5 AgenticView fold, the portfolio index (v2 dashlist + NR-6 guard), and non-fatal isolation.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience import portal_build
from startd8.kickoff_experience.portal_build import build_index
from startd8.kickoff_experience.portal_spec import INDEX_UID, WORKBOOK_TAG, slugify_project

pytestmark = pytest.mark.unit
runner = CliRunner()


def _proj() -> Path:
    # resolve_confined_root rejects a symlinked root (macOS /var → /private/var).
    return Path(os.path.realpath(tempfile.mkdtemp()))


def _instantiate(proj: Path, *args: str):
    return runner.invoke(kickoff_kernel_app, ["instantiate", str(proj), "--apply", *args])


def _confirmable_field(proj) -> str:
    a = runner.invoke(
        kickoff_kernel_app,
        ["confirm", "--all", "--as-is", "--dry-run", "--project", str(proj)],
    )
    m = re.findall(r"([a-z-]+\.yaml#/[^\s]+) =", a.stdout)
    return m[0] if m else "observability.yaml#/provenance_default"


# --------------------------------------------------------------------------- default = cockpit (M3)


def test_portal_default_builds_the_cockpit():
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold docs/kickoff
    out = runner.invoke(kickoff_kernel_app, ["portal", str(proj)])
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))  # the -v2 cockpit board
    assert "cockpit" in out.output.lower()


def test_instantiate_autorefresh_builds_the_cockpit_no_jsonnet():
    # M3.1: `instantiate` (default --portal) refreshes the -v2 cockpit — no jsonnet toolchain.
    proj = _proj()
    out = _instantiate(proj)
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))


def test_confirm_autorefresh_builds_the_cockpit_no_jsonnet():
    # M3.1: a confirm refreshes the -v2 cockpit, no jsonnet needed.
    proj = _proj()
    _instantiate(proj, "--no-portal")
    out = runner.invoke(
        kickoff_kernel_app,
        ["confirm", _confirmable_field(proj), "--as-is", "--project", str(proj)],
    )
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))


def test_no_kickoff_package_skips():
    res = portal_build.build_workbook_v2_and_maybe_provision(_proj(), "demo")
    assert res.skipped_reason and "no kickoff package" in res.skipped_reason


# --------------------------------------------------------------------------- agentic cockpit fold (M5)


def test_dynamic_cockpit_folds_snapshot_and_inbox():
    from startd8.kickoff_experience import session_snapshot as ss
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    proj = _proj()
    _instantiate(proj, "--no-portal")
    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "how ready?"},
            {"role": "assistant", "content": [{"type": "text", "text": "two inputs remain"}]},
        ],
        model="m", input_tokens=1, output_tokens=1, total_tokens=2, cost_usd=0.0,
        posture="concierge · propose-only", project=str(proj), session_id="sid-m5",
        generated_at="2026-07-09T00:00:00+00:00",
    )
    ss.write_snapshot(proj, snap)
    env = ProposalEnvelope(
        project_id="p", envelope_seq=1,
        proposals=[EnvelopedProposal(kind="capture", params={"value_path": "conventions.tz", "value": "UTC"}, id="MP-1")],
    )
    ip = proj / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env.to_dict()), encoding="utf-8")

    res = portal_build.build_workbook_v2_and_maybe_provision(proj, out_dir=proj / "out")
    assert res.ok, res.skipped_reason
    assert res.summary["snapshot"] == "present" and res.summary["proposals"] == 1
    board = json.loads(Path(res.json_path).read_text(encoding="utf-8"))
    titles = [t["spec"]["title"] for t in board["spec"]["layout"]["spec"]["tabs"]]
    assert titles == ["Status", "Assistant", "Proposals", "Stakeholders", "Pipeline"]
    blob = json.dumps(board)
    assert "two inputs remain" in blob and "MP-1" in blob


# --------------------------------------------------------------------------- slug (FR-5)


def test_slug_is_deterministic():
    assert slugify_project("My App") == "my-app"
    assert slugify_project("my_app") == "my-app"


# --------------------------------------------------------------------------- instantiate wiring


def test_instantiate_generates_workbook_by_default():
    proj = _proj()
    out = _instantiate(proj)
    assert out.exit_code == 0
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*.json"))
    assert any("Workbook:" in ln for ln in out.stdout.splitlines())


def test_no_portal_skips_generation():
    proj = _proj()
    out = _instantiate(proj, "--no-portal")
    assert out.exit_code == 0
    assert not (proj / ".startd8" / "dashboards").exists()
    assert any("skipped (--no-portal)" in ln for ln in out.stdout.splitlines())


def test_preview_is_side_effect_free():
    proj = _proj()
    out = runner.invoke(kickoff_kernel_app, ["instantiate", str(proj)])  # no --apply
    assert not (proj / ".startd8" / "dashboards").exists()
    assert not any("Workbook" in ln for ln in out.stdout.splitlines())


def test_generation_failure_never_changes_instantiate_exit(monkeypatch):
    # FR-7: a Workbook (cockpit) failure never fails the source-of-record write.
    proj = _proj()
    monkeypatch.setattr(
        portal_build,
        "build_workbook_v2_and_maybe_provision",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("catastrophic")),
    )
    out = _instantiate(proj)
    assert out.exit_code == 0
    assert (proj / "docs" / "kickoff" / "inputs" / "conventions.yaml").is_file()  # scaffold intact


# --------------------------------------------------------------------------- portfolio index (FR-11, v2)


def test_index_is_a_v2_dashlist_by_workbook_tag():
    from startd8.kickoff_experience.portal_spec_v2 import build_index_v2

    board = build_index_v2()
    assert board["metadata"]["name"] == INDEX_UID
    panel = list(board["spec"]["elements"].values())[0]
    assert panel["spec"]["vizConfig"]["kind"] == "dashlist"
    assert panel["spec"]["vizConfig"]["spec"]["options"]["tags"] == [WORKBOOK_TAG]


def test_index_compiles_empty_portfolio():
    # M4: the portfolio index is a pure-Python v2 dashlist (no jsonnet toolchain).
    res = build_index(_proj())  # zero Workbooks anywhere — must still render
    assert res.ok, res.skipped_reason
    d = json.loads(Path(res.json_path).read_text())
    assert d["metadata"]["name"] == INDEX_UID
    panel = list(d["spec"]["elements"].values())[0]
    assert panel["spec"]["vizConfig"]["kind"] == "dashlist"
    assert panel["spec"]["vizConfig"]["spec"]["options"]["tags"] == ["workbook"]


def test_index_provision_to_shared_url_needs_confirmation():
    # NR-6: a non-loopback provision URL for the global index requires confirm_shared.
    blocked = build_index(_proj(), provision_url="http://grafana.example.com:3000")
    assert blocked.skipped_reason and "confirmation" in blocked.skipped_reason
    assert portal_build._is_loopback("http://localhost:3000")
    assert not portal_build._is_loopback("http://grafana.example.com:3000")


# --------------------------------------------------------------------------- refresh on confirm (FR-9)


def test_confirm_refreshes_workbook_fr9():
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold, no board yet
    out = runner.invoke(
        kickoff_kernel_app,
        ["confirm", _confirmable_field(proj), "--as-is", "--project", str(proj)],
    )
    assert out.exit_code == 0
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*.json"))  # board regenerated
    assert any("Workbook:" in ln for ln in out.stdout.splitlines())


def test_confirm_no_portal_skips_refresh_fr9():
    proj = _proj()
    _instantiate(proj, "--no-portal")
    out = runner.invoke(
        kickoff_kernel_app,
        ["confirm", _confirmable_field(proj), "--as-is", "--no-portal", "--project", str(proj)],
    )
    assert out.exit_code == 0
    assert not (proj / ".startd8" / "dashboards").exists()
