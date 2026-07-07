# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff-audience M5 — FR-19 web audience selector.

The riskiest surface, so it is fully gated: it persists via the SAME canonical
``set_audience_preference`` as the CLI (not a second write path), behind the shared write gate
(loopback Host / CSRF / rate-limit), writes ONLY the preference (A-OQ10 — no pre-pass), and validates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from startd8.kickoff_experience.web import build_kickoff_app

_LOOPBACK = {"host": "127.0.0.1:8000"}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(build_kickoff_app(tmp_path), headers=_LOOPBACK)


def _csrf(client: TestClient) -> str:
    html = client.get("/concierge").text
    return re.search(r"name='csrf' value='([^']+)'", html).group(1)


def test_audience_json_reports_resolved_default(client: TestClient) -> None:
    r = client.get("/audience.json")
    assert r.status_code == 200
    body = r.json()
    assert body["audience"] == "intermediate"     # unset default (FR-2)
    assert body["tier"] == "light"
    assert set(body["choices"]) == {"beginner", "intermediate", "advanced"}


def test_audience_set_persists_via_canonical_setter(client: TestClient, tmp_path: Path) -> None:
    csrf = _csrf(client)
    r = client.post("/audience/set", data={"audience": "beginner", "csrf": csrf})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["audience"] == "beginner" and r.json()["scope"] == "project"
    # persisted to the project build-preferences.yaml (the canonical setter, not a second path)
    prefs = (tmp_path / "docs" / "kickoff" / "inputs" / "build-preferences.yaml").read_text()
    assert "audience: beginner" in prefs
    # and re-resolves through /audience.json
    assert client.get("/audience.json").json()["audience"] == "beginner"


def test_audience_set_writes_only_preference_no_prepass(client: TestClient, tmp_path: Path) -> None:
    """A-OQ10: the selector writes ONLY the preference — it never runs the pre-pass (no ledger)."""
    csrf = _csrf(client)
    client.post("/audience/set", data={"audience": "beginner", "csrf": csrf})
    assert not (tmp_path / "docs" / "kickoff" / "confirmed.yaml").exists()


def test_audience_set_rejects_bad_value(client: TestClient) -> None:
    csrf = _csrf(client)
    r = client.post("/audience/set", data={"audience": "expert", "csrf": csrf})
    assert r.status_code == 400 and r.json()["code"] == "bad_audience"


def test_audience_set_requires_valid_csrf(client: TestClient) -> None:
    r = client.post("/audience/set", data={"audience": "beginner", "csrf": "forged-token"})
    assert r.status_code == 403 and r.json()["code"] == "session_expired"


def test_audience_set_forbidden_from_non_loopback_host(tmp_path: Path) -> None:
    evil = TestClient(build_kickoff_app(tmp_path), headers={"host": "evil.example.com"})
    csrf = _csrf(evil)   # GET still works
    r = evil.post("/audience/set", data={"audience": "beginner", "csrf": csrf})
    assert r.status_code == 403 and r.json()["code"] == "forbidden_host"
