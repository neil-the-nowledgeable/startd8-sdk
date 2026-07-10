"""Tests for the Workbook project-start generation (WORKBOOK_PROJECT_START_REQUIREMENTS v0.4).

Covers the shared helper (FR-1/FR-10), toolchain degradation (FR-6 absent+broken), non-fatal isolation
(FR-7), the 1:1 slug + reserved `index` (FR-5), the portfolio index + NR-6 guard (FR-11), and the
instantiate wiring (FR-2 default-ON, `--no-portal`, preview side-effect-free, fault-injection isolation).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience import portal_build
from startd8.kickoff_experience.portal_build import (
    build_and_maybe_provision,
    build_index,
)
from startd8.kickoff_experience.portal_spec import (
    INDEX_UID,
    WORKBOOK_TAG,
    WorkbookSlugError,
    build_workbook_index_spec,
    slugify_project,
    workbook_uid,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def _proj() -> Path:
    # resolve_confined_root rejects a symlinked root (macOS /var → /private/var).
    return Path(os.path.realpath(tempfile.mkdtemp()))


def _instantiate(proj: Path, *args: str):
    return runner.invoke(
        kickoff_kernel_app, ["instantiate", str(proj), "--apply", *args]
    )


# --------------------------------------------------------------------------- convergence M3 (default flip)


def test_portal_default_builds_the_cockpit():
    # M3: a plain `kickoff portal` now builds the v2 cockpit (no jsonnet needed), not the classic board.
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold docs/kickoff
    out = runner.invoke(kickoff_kernel_app, ["portal", str(proj)])
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))  # the -v2 cockpit board
    assert "cockpit" in out.output.lower()


def test_instantiate_autorefresh_builds_the_cockpit_no_jsonnet():
    # M3.1: `instantiate` (default --portal) now refreshes the DEFAULT board — the -v2 cockpit — which
    # needs no jsonnet toolchain (proves the reroute off the classic path).
    proj = _proj()
    out = _instantiate(proj)  # default portal refresh
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))  # cockpit board written


def test_confirm_autorefresh_builds_the_cockpit_no_jsonnet():
    # M3.1: a confirm refreshes the -v2 cockpit (not the classic board), no jsonnet needed.
    proj = _proj()
    _instantiate(proj, "--no-portal")
    out = runner.invoke(
        kickoff_kernel_app,
        ["confirm", _confirmable_field(proj), "--as-is", "--project", str(proj)],
    )
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*-v2.json"))


def test_portal_classic_escape_hatch_does_not_build_v2():
    # M3: `--classic` routes to the legacy board (which may skip without the jsonnet toolchain) — it must
    # NOT emit the v2 cockpit board.
    proj = _proj()
    _instantiate(proj, "--no-portal")
    out = runner.invoke(kickoff_kernel_app, ["portal", str(proj), "--classic"])
    assert out.exit_code == 0, out.output
    dash = proj / ".startd8" / "dashboards"
    v2 = list(dash.glob("cc-portal-kickoff-*-v2.json")) if dash.is_dir() else []
    assert not v2  # classic path (built or skipped) never writes the -v2 board


# --------------------------------------------------------------------------- agentic cockpit (M5 wiring)


def test_dynamic_cockpit_folds_snapshot_and_inbox():
    # M5: build_workbook_v2_and_maybe_provision passes the M2 AgenticView so the Assistant/Proposals
    # tabs mirror the real session snapshot + VIPP inbox ($0, no provision).
    from startd8.kickoff_experience import session_snapshot as ss
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold the kickoff package (docs/kickoff)

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
    assert res.summary["snapshot"] == "present"
    assert res.summary["proposals"] == 1
    board = json.loads(Path(res.json_path).read_text(encoding="utf-8"))
    titles = [t["spec"]["title"] for t in board["spec"]["layout"]["spec"]["tabs"]]
    assert titles == ["Status", "Assistant", "Proposals", "Stakeholders", "Pipeline"]
    blob = json.dumps(board)
    assert "two inputs remain" in blob and "MP-1" in blob  # snapshot + proposal folded into the board


# --------------------------------------------------------------------------- FR-5 slug / UID


def test_slug_is_deterministic_and_1to1():
    assert slugify_project("My App") == "my-app"
    assert slugify_project("my_app") == "my-app"
    assert workbook_uid("My App") == "cc-portal-kickoff-my-app"


def test_reserved_index_slug_is_rejected():
    with pytest.raises(WorkbookSlugError):
        workbook_uid("Index")  # would collide with the portfolio-index UID
    with pytest.raises(WorkbookSlugError):
        workbook_uid("!!!")  # slugifies to empty


def test_helper_skips_on_reserved_slug():
    proj = _proj()
    (proj / "docs" / "kickoff").mkdir(parents=True)
    res = build_and_maybe_provision(proj, "index")
    assert res.skipped_reason and "reserved" in res.skipped_reason
    assert res.json_path is None


# --------------------------------------------------------------------------- FR-6 toolchain degrade


def test_absent_toolchain_degrades_not_raises(monkeypatch):
    proj = _proj()
    (proj / "docs" / "kickoff").mkdir(parents=True)

    def _raise():
        from startd8.dashboard_creator.discovery import ConfigurationError

        raise ConfigurationError("no toolchain")

    monkeypatch.setattr("startd8.dashboard_creator.discovery.detect_toolchain", _raise)
    res = build_and_maybe_provision(proj, "demo")
    assert res.skipped_reason and "jsonnet toolchain" in res.skipped_reason
    assert res.json_path is None  # nothing generated, no exception


def test_broken_toolchain_degrades(monkeypatch):
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold the package
    # Simulate a present-but-broken toolchain: the compile step raises mid-run.
    monkeypatch.setattr(
        portal_build,
        "_run_workflow",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    res = build_and_maybe_provision(proj, "demo")
    assert res.skipped_reason and "generation failed" in res.skipped_reason


def test_no_kickoff_package_skips():
    res = build_and_maybe_provision(_proj(), "demo")
    assert res.skipped_reason and "no kickoff package" in res.skipped_reason


# --------------------------------------------------------------------------- FR-2 / FR-4 happy path


def test_helper_generates_skeleton_on_fresh_project():
    proj = _proj()
    _instantiate(proj, "--no-portal")  # package exists, no authoring yet
    res = build_and_maybe_provision(proj, "demo")
    assert res.ok and res.skipped_reason is None
    assert res.uid == "cc-portal-kickoff-demo"
    d = json.loads(Path(res.json_path).read_text())
    assert d["uid"] == "cc-portal-kickoff-demo"
    assert WORKBOOK_TAG in d["tags"]  # FR-11 tag contract
    assert "templating" in d  # FR-4 empty-state renders as a valid dashboard


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


# --------------------------------------------------------------------------- FR-7 non-fatal isolation


def test_generation_failure_never_changes_instantiate_exit(monkeypatch):
    proj = _proj()
    # Force the helper to blow up entirely; instantiate must still exit 0 (the write succeeded).
    monkeypatch.setattr(
        portal_build,
        "build_and_maybe_provision",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("catastrophic")),
    )
    out = _instantiate(proj)
    assert (
        out.exit_code == 0
    )  # FR-7: dashboard failure never fails the source-of-record write
    assert (
        proj / "docs" / "kickoff" / "inputs" / "conventions.yaml"
    ).is_file()  # scaffold intact


# --------------------------------------------------------------------------- FR-11 portfolio index


def test_index_spec_is_a_dashlist_by_workbook_tag():
    spec = build_workbook_index_spec()
    assert spec["uid"] == INDEX_UID
    p = spec["panels"][0]
    assert p["type"] == "dashlist" and p["options"]["tags"] == [WORKBOOK_TAG]


def test_index_compiles_empty_portfolio():
    # M4: the portfolio index is now a pure-Python v2 dashlist (no jsonnet toolchain).
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
    # loopback is fine without confirmation (generation still $0; provisioning would need a live server)
    assert portal_build._is_loopback("http://localhost:3000")
    assert not portal_build._is_loopback("http://grafana.example.com:3000")


# --------------------------------------------------------------------------- FR-9 refresh on confirm


def _confirmable_field(proj) -> str:
    import re

    a = runner.invoke(
        kickoff_kernel_app,
        ["confirm", "--all", "--as-is", "--dry-run", "--project", str(proj)],
    )
    m = re.findall(r"([a-z-]+\.yaml#/[^\s]+) =", a.stdout)
    return m[0] if m else "observability.yaml#/provenance_default"


def test_confirm_refreshes_workbook_fr9():
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold, no board yet
    out = runner.invoke(
        kickoff_kernel_app,
        ["confirm", _confirmable_field(proj), "--as-is", "--project", str(proj)],
    )
    assert out.exit_code == 0
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(
        dash.glob("cc-portal-kickoff-*.json")
    )  # board regenerated
    assert any("Workbook:" in ln for ln in out.stdout.splitlines())


def test_confirm_no_portal_skips_refresh_fr9():
    proj = _proj()
    _instantiate(proj, "--no-portal")
    out = runner.invoke(
        kickoff_kernel_app,
        [
            "confirm",
            _confirmable_field(proj),
            "--as-is",
            "--no-portal",
            "--project",
            str(proj),
        ],
    )
    assert out.exit_code == 0
    assert not (proj / ".startd8" / "dashboards").exists()


# --------------------------------------------------------------------------- FR-5 collision guard


def _fake_grafana(monkeypatch, resp):
    import startd8.dashboard_creator.grafana_client as gc

    class _Client:
        def __init__(self, *a, **k):
            pass

        def get_dashboard(self, uid):
            return resp

    monkeypatch.setattr(gc, "GrafanaClient", _Client)


class _Resp:
    def __init__(self, success, title=""):
        self.success = success
        self.data = {"dashboard": {"title": title}} if success else {}


def test_provision_collision_reason(monkeypatch):
    url, uid, title = (
        "http://grafana.example:3000",
        "cc-portal-kickoff-x",
        "Mine — Digital Project Workbook",
    )
    # a DIFFERENT project already owns the UID → refuse
    _fake_grafana(monkeypatch, _Resp(True, "Other — Digital Project Workbook"))
    assert "already belongs" in (
        portal_build._provision_collision_reason(url, uid, title) or ""
    )
    # 404 (not found) → no collision
    _fake_grafana(monkeypatch, _Resp(False))
    assert portal_build._provision_collision_reason(url, uid, title) is None
    # same board (same title) → idempotent upsert, no collision
    _fake_grafana(monkeypatch, _Resp(True, title))
    assert portal_build._provision_collision_reason(url, uid, title) is None


def test_build_refuses_provision_on_collision(monkeypatch):
    proj = _proj()
    _instantiate(proj, "--no-portal")
    _fake_grafana(monkeypatch, _Resp(True, "Someone Else — Digital Project Workbook"))
    res = build_and_maybe_provision(
        proj, "demo", provision_url="http://grafana.example:3000"
    )
    assert res.skipped_reason and "already belongs" in res.skipped_reason
    assert res.json_path is None  # refused before provisioning — never clobbered


# ------------------------------------------- audience personalization fail-open (Era 1, R2-S4/R2-S7)


def _overview_content(json_path) -> str:
    d = json.loads(Path(json_path).read_text())
    return next(p for p in d["panels"] if p.get("type") == "text")["options"]["content"]


def test_audience_resolution_failure_degrades_not_skips(monkeypatch):
    """R2-S7: a raise in resolve_audience_preference must degrade to the default board, NOT be swallowed
    by the broad except into a misleading 'generation failed' skip."""
    proj = _proj()
    _instantiate(proj, "--no-portal")

    def _boom(*a, **k):
        raise RuntimeError("config blew up")

    monkeypatch.setattr("startd8.concierge.audience.resolve_audience_preference", _boom)
    res = build_and_maybe_provision(proj, "demo")
    assert res.ok and res.skipped_reason is None
    assert "Rendered for" not in _overview_content(res.json_path)  # degraded to Intermediate/light


def test_missing_build_preferences_defaults_to_intermediate():
    """R2-S4: no build-preferences.yaml → resolve falls to Intermediate; board still generates."""
    proj = _proj()
    _instantiate(proj, "--no-portal")
    (proj / "docs" / "kickoff" / "inputs" / "build-preferences.yaml").unlink(missing_ok=True)
    res = build_and_maybe_provision(proj, "demo")
    assert res.ok
    assert "Rendered for" not in _overview_content(res.json_path)


def test_malformed_ledger_yields_no_badges_no_crash():
    """R2-S4/FR-6: a corrupt confirmed.yaml → load_ledger returns {} tolerantly; no badge, no crash."""
    proj = _proj()
    _instantiate(proj, "--no-portal")
    (proj / "docs" / "kickoff" / "confirmed.yaml").write_text("::: not yaml :::", encoding="utf-8")
    res = build_and_maybe_provision(proj, "demo")
    assert res.ok
    assert "🛡️" not in _overview_content(res.json_path)
