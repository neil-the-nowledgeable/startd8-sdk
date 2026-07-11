# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""GE-M5 — cloud scoping (read/preview-only) over the served guided surface (FR-GE-8).

Cloud has no per-tenant trust substrate (only the static ``server/auth.py`` X-API-Key), so a
``cloud=True`` served app is **read/preview-only**:

  * Reads (``/``, ``/guided`` + ``/guided.json``, ``/concierge`` GET, ``/state.json``) stay open.
  * Every WRITE + LLM-invoking (facilitation/chat) endpoint is refused with a typed **501**
    (``cloud_write_deferred``) — the explicit OQ-GE-7 marker (cloud-write is intentionally not built).
  * Deepen is **static-transcript-only**: ``/guided`` reads only persisted
    ``.startd8/kickoff-panel/*`` sessions (no LLM), so it is safe on cloud.
  * ``--api-key`` reuses the static X-API-Key middleware as the coarse cloud POST gate.

The human downloads produced inputs and writes locally (FR-GE-13/14: human/CLI is the sole writer).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.concierge_view import format_cost  # noqa: E402
from startd8.kickoff_experience.web import (  # noqa: E402
    CLOUD_WRITE_DEFERRED_CODE,
    build_kickoff_app,
)


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\n", encoding="utf-8"
    )
    return root


def _halted_cost_session() -> dict:
    return {
        "session_id": "kp-20260704T000000-abc123",
        "status": "halted",
        "halt": {"reason": "assumptions_gate", "message": "Validate the premise first."},
        "budget_usd": 2.0,
        "cost_total_usd": 0.1234,
        "rounds": [{"round_id": "R1", "entries": [{"cost_usd": 0.1234}]}],
        "synthesis": None,
    }


def _persist_session(root: Path, session: dict) -> None:
    d = root / ".startd8" / "kickoff-panel"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session['session_id']}.json").write_text(json.dumps(session), encoding="utf-8")


# ── the cloud toggle sets a read-only posture ────────────────────────────────────────────────────


def test_cloud_app_state_is_read_only_and_agentic_disabled(tmp_path):
    root = _make_project(tmp_path)
    app = build_kickoff_app(root, cloud=True, chat_factory=lambda: object())
    assert app.state.kickoff_cloud is True
    # cloud force-disables the LLM-invoking agentic panel even if a factory was passed
    assert app.state.kickoff_agentic_enabled is False


# ── reads stay open; Deepen is static-transcript-only on cloud ───────────────────────────────────


def test_cloud_guided_read_surfaces_static_transcript(tmp_path):
    root = _make_project(tmp_path)
    _persist_session(root, _halted_cost_session())
    client = TestClient(build_kickoff_app(root, cloud=True))

    j = client.get("/guided.json")
    assert j.status_code == 200
    payload = j.json()
    assert payload["schema"] == "kickoff.guided.v1"
    # the persisted Deepen transcript is surfaced read-only (no LLM invoked)
    assert payload["deepen"]["halted"] is True
    assert payload["deepen"]["cost_total_usd"] == 0.1234

    h = client.get("/guided")
    assert h.status_code == 200
    body = h.text
    assert "Orient" in body and "Guide" in body and "Deepen" in body
    assert format_cost(0.1234) in body


def test_cloud_overview_and_state_read_ok(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True))
    assert client.get("/").status_code == 200
    assert client.get("/state.json").status_code == 200
    assert client.get("/concierge.json").status_code == 200


# ── every write endpoint is refused with the typed 501 (OQ-GE-7 marker) ──────────────────────────


def _assert_cloud_deferred(resp) -> None:
    assert resp.status_code == 501, resp.text
    assert resp.json()["code"] == CLOUD_WRITE_DEFERRED_CODE


def test_cloud_capture_apply_refused(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True))
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.language", "value": "python", "csrf": "x"},
    )
    _assert_cloud_deferred(resp)


def test_cloud_concierge_instantiate_refused(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True))
    resp = client.post(
        "/concierge/instantiate",
        data={"posture": "prototype", "csrf": "x", "intent": "y"},
    )
    _assert_cloud_deferred(resp)


def test_cloud_concierge_friction_refused(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True))
    resp = client.post(
        "/concierge/friction",
        data={"friction": "f", "what_happened": "w", "implication": "i",
              "csrf": "x", "intent": "y"},
    )
    _assert_cloud_deferred(resp)


# ── the paid facilitation/chat is disabled on cloud (no LLM spend) ────────────────────────────────


def test_cloud_chat_page_is_unavailable(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True, chat_factory=lambda: object()))
    r = client.get("/concierge/chat")
    assert r.status_code == 200
    assert "unavailable on cloud" in r.text.lower()


def test_cloud_chat_message_refused(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True, chat_factory=lambda: object()))
    resp = client.post("/concierge/chat/message", data={"message": "hi"})
    _assert_cloud_deferred(resp)


# ── the static X-API-Key gates POSTs when serving cloud with a key ────────────────────────────────


def test_cloud_api_key_gates_post(tmp_path):
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, cloud=True, api_key="s3cret"))
    # a POST without the key is rejected by the middleware (before the route)
    unauth = client.post("/capture/preview", data={"value_path": "x", "value": "y"})
    assert unauth.status_code == 401
    # with the key the request reaches the route (a read-only preview POST → 200/400, not 401)
    authed = client.post(
        "/capture/preview",
        data={"value_path": "conventions.language", "value": "python"},
        headers={"X-API-Key": "s3cret"},
    )
    assert authed.status_code != 401
    # reads never require the key (middleware only gates POST)
    assert client.get("/guided.json").status_code == 200


# ── regression: a LOCAL (non-cloud) preview serve keeps its existing behaviour ────────────────────


def test_local_preview_refusal_is_unchanged(tmp_path):
    """Non-cloud preview mode still returns `preview_only` (not the cloud code) — behaviour preserved."""
    root = _make_project(tmp_path)
    client = TestClient(build_kickoff_app(root, mode="preview"))
    resp = client.post(
        "/capture/apply",
        data={"value_path": "conventions.language", "value": "python", "csrf": "x"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "preview_only"
