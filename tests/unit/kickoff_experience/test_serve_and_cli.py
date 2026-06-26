"""M7 — serve plumbing, preflight, scratch GC, inspect mode, CLI."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.serve import (
    INSPECT_SCHEMA_VERSION,
    Mode,
    find_free_port,
    gc_stale_scratch,
    inspect_payload,
    preflight,
    scratch_dir_for,
)

CONVENTIONS = "domain: conventions\nprovenance_default: authored\nlanguage: python\n"
REQ_DOC = textwrap.dedent(
    """\
    ## Entities

    ### Profile
    | Field | Type | Notes |
    |---|---|---|
    | name | text | |
    """
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(CONVENTIONS, encoding="utf-8")
    (tmp_path / "docs" / "kickoff" / "REQUIREMENTS.md").write_text(REQ_DOC, encoding="utf-8")
    return tmp_path


# --- ports + preflight -------------------------------------------------------------------------


def test_find_free_port_is_bindable() -> None:
    port = find_free_port()
    assert 1024 < port < 65536


def test_preflight_ok_on_real_project(project: Path) -> None:
    pf = preflight(project, mode=Mode.WRITE)
    assert pf.ok
    names = {c.name for c in pf.checks}
    assert {"inputs_dir", "inputs_writable", "port_bindable"} <= names


def test_preflight_flags_missing_inputs(tmp_path: Path) -> None:
    pf = preflight(tmp_path, mode=Mode.WRITE)
    assert not pf.ok
    inputs_check = next(c for c in pf.checks if c.name == "inputs_dir")
    assert not inputs_check.ok
    assert "missing" in inputs_check.detail


def test_inspect_mode_does_not_require_writable(tmp_path: Path) -> None:
    # In inspect mode the writable check is not even run (read-only).
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    pf = preflight(tmp_path, mode=Mode.INSPECT)
    assert "inputs_writable" not in {c.name for c in pf.checks}


# --- scratch GC (R5-S8) ------------------------------------------------------------------------


def test_gc_stale_scratch_keeps_current_removes_old(project: Path) -> None:
    root = project / ".startd8" / "kickoff-scratch"
    root.mkdir(parents=True)
    current = scratch_dir_for(project, "f" * 64)
    current.mkdir()
    # Three stale dirs.
    for name in ("aaaa", "bbbb", "cccc"):
        (root / name).mkdir()
    removed = gc_stale_scratch(project, "f" * 64, keep_n=2)
    # Keeps current + the newest 1 stale (keep_n - 1); removes the other 2.
    assert len(removed) == 2
    assert current.is_dir()  # the current fingerprint is never removed


def test_gc_stale_scratch_noop_when_absent(tmp_path: Path) -> None:
    assert gc_stale_scratch(tmp_path, "abc") == []


# --- inspect payload (R4-F3 / R4-F8) -----------------------------------------------------------


def test_inspect_payload_is_versioned_and_read_only(project: Path) -> None:
    before = (project / "docs/kickoff/inputs/conventions.yaml").read_text()
    payload = inspect_payload(project)
    assert payload["schema_version"] == INSPECT_SCHEMA_VERSION
    assert payload["mode"] == Mode.INSPECT
    assert "state" in payload and "next_action" in payload and "preflight" in payload
    assert "fingerprint" in payload
    # No write happened, no scratch dir was created.
    assert (project / "docs/kickoff/inputs/conventions.yaml").read_text() == before
    assert not (project / ".startd8" / "kickoff-scratch").exists()


def test_inspect_payload_matches_canonical_state(project: Path) -> None:
    from startd8.kickoff_experience.web import load_state

    payload = inspect_payload(project)
    assert payload["state"] == load_state(project).to_dict()


# --- feature-mode gate on the web app (R4-F5) --------------------------------------------------


def test_preview_mode_refuses_apply(project: Path) -> None:
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    client = TestClient(build_kickoff_app(project, mode=Mode.PREVIEW))
    # Even with a (would-be) valid token, preview mode refuses to apply.
    import re

    html = client.get("/step/conventions").text
    csrf = re.search(r"name='csrf' value='([^']+)'", html).group(1)
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.yaml#/language", "value": "python", "csrf": csrf},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "preview_only"
    # Preview still works in preview mode.
    pv = client.post(
        "/capture/preview", data={"value_path": "conventions.yaml#/language", "value": "go"}
    )
    assert pv.status_code == 200


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_lint_config_clean() -> None:
    from typer.testing import CliRunner

    from startd8.cli_kickoff import kickoff_app

    res = CliRunner().invoke(kickoff_app, ["lint-config"])
    assert res.exit_code == 0
    assert "clean" in res.stdout


def test_cli_inspect_emits_json(project: Path) -> None:
    import json

    from typer.testing import CliRunner

    from startd8.cli_kickoff import kickoff_app

    res = CliRunner().invoke(kickoff_app, ["inspect", str(project)])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["schema_version"] == INSPECT_SCHEMA_VERSION
    assert "state" in payload
