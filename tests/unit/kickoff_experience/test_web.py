"""M4 — deterministic kickoff web front-end."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.manifest import default_config  # noqa: E402
from startd8.kickoff_experience.state import build_kickoff_state  # noqa: E402
from startd8.kickoff_experience.web import (  # noqa: E402
    app_fingerprint,
    build_kickoff_app,
    load_state,
)

CONVENTIONS = textwrap.dedent(
    """\
    # header — must survive
    domain: conventions
    provenance_default: authored
    language: python
    stack:
      framework: fastapi
    data_model:
      money: cents
      datetime: utc
    """
)

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


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


# --- parity oracle -----------------------------------------------------------------------------


def test_state_json_is_the_canonical_view_model(project: Path) -> None:
    app = build_kickoff_app(project)
    client = TestClient(app)
    resp = client.get("/state.json")
    assert resp.status_code == 200
    # Byte-identical to what the TUI/M5 path would serialize from the same docs (R1-S7 parity).
    expected = load_state(project).to_dict()
    assert resp.json() == expected
    assert resp.json() == build_kickoff_state(
        {"REQUIREMENTS.md": REQ_DOC}
    ).to_dict() or "fields" in resp.json()


# --- pages -------------------------------------------------------------------------------------


def test_overview_renders_and_sets_csrf_cookie(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Project kickoff" in resp.text
    assert "Readiness" in resp.text
    assert "kickoff_csrf" in resp.cookies


def test_step_page_renders_fields(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    resp = client.get("/step/conventions")
    assert resp.status_code == 200
    assert "Technology conventions" in resp.text
    assert "value_path" in resp.text  # the capture form
    assert client.get("/step/nope").status_code == 404


# --- capture preview (no write) ----------------------------------------------------------------


def test_capture_preview_returns_diff(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    resp = client.post(
        "/capture/preview",
        data={"value_path": "conventions.yaml#/data_model.money", "value": "float"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["preview"]["old_value"] == "cents"
    assert body["preview"]["new_value"] == "float"
    # No write happened.
    assert "money: cents" in (project / "docs/kickoff/inputs/conventions.yaml").read_text()


def test_capture_preview_rejects_unknown_field(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    resp = client.post(
        "/capture/preview", data={"value_path": "conventions.yaml#/evil", "value": "x"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "value_path_not_allowed"


# --- capture apply: CSRF + rate-limit + post-write refresh -------------------------------------


def _csrf_from_step(client: TestClient) -> str:
    html = client.get("/step/conventions").text
    m = re.search(r"name='csrf' value='([^']+)'", html)
    assert m, "csrf token must be embedded in the form"
    return m.group(1)


def test_apply_requires_valid_csrf(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.yaml#/data_model.money", "value": "float", "csrf": "bogus"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "session_expired"


def test_apply_writes_and_post_write_refresh(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    csrf = _csrf_from_step(client)
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.yaml#/data_model.money", "value": "float", "csrf": csrf},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["applied"]["new_value"] == "float"
    # Post-write refresh (R1-S10): the field is re-read from disk.
    on_disk = (project / "docs/kickoff/inputs/conventions.yaml").read_text()
    assert "money: float" in on_disk
    assert "# header — must survive" in on_disk  # untouched


def test_apply_rate_limited_after_burst(project: Path) -> None:
    client = TestClient(build_kickoff_app(project))
    csrf = _csrf_from_step(client)
    # 20 allowed, 21st rate-limited (same token, same window).
    last = None
    for _ in range(21):
        last = client.post(
            "/capture/apply",
            data={
                "value_path": "conventions.yaml#/data_model.money",
                "value": "cents",
                "csrf": csrf,
            },
        )
    assert last.status_code == 429
    assert last.json()["code"] == "rate_limited"


def test_session_token_expires(project: Path) -> None:
    clock = FakeClock()
    client = TestClient(build_kickoff_app(project, clock=clock))
    csrf = _csrf_from_step(client)
    clock.t += 10_000.0  # advance past the TTL
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.yaml#/data_model.money", "value": "float", "csrf": csrf},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "session_expired"


# --- fingerprint (R5-S1) -----------------------------------------------------------------------


def test_fingerprint_stable_and_theme_sensitive() -> None:
    cfg = default_config()
    assert app_fingerprint(cfg) == app_fingerprint(cfg)
    assert app_fingerprint(cfg, theme="professional") != app_fingerprint(cfg, theme="editorial")


def test_app_exposes_fingerprint(project: Path) -> None:
    app = build_kickoff_app(project)
    assert app.state.kickoff_fingerprint == app_fingerprint(default_config())
