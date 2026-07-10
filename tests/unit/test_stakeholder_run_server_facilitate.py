# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""F1 M3 — the facilitate HTTP routes: dry-run, confirm (run_key/budget/nonce), status, cancel."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import startd8.kickoff_experience.stakeholder_run_server as srv

TOKEN = "tok"


class _Budget:
    block_on_exceed = True
    scope_project = "stakeholder-panel"


class _Manager:
    def __init__(self, budgets):
        self._b = budgets

    def list_budgets(self, active_only=True):
        return self._b


class _Pricing:
    def estimate_cost(self, model, prompt_chars, expected_output_chars=0):
        return 0.01

    def calculate_total_cost(self, model, input_tokens, output_tokens):
        return 0.002


def _project(tmp_path):
    d = tmp_path / "docs" / "kickoff" / "inputs"
    d.mkdir(parents=True)
    (d / "stakeholders.yaml").write_text(
        "domain: stakeholders\nprovenance_default: authored\n"
        "personas:\n  - role_id: po\n    display_name: PO\n    goals: [\"ship the mvp\"]\n"
        "  - role_id: eu\n    display_name: EU\n    goals: [\"use it fast\"]\n",
        encoding="utf-8")
    return tmp_path


def _client(tmp_path, *, manager=None):
    cfg = srv.RunServerConfig(
        project_root=_project(tmp_path), token=TOKEN, model="anthropic:claude-haiku-4-5-20251001",
        budget_manager=manager if manager is not None else _Manager([_Budget()]),
        pricing=_Pricing(),
    )
    return TestClient(srv.build_stakeholder_run_app(cfg))


_H = {"authorization": f"Bearer {TOKEN}"}


def test_auth_required(tmp_path):
    r = _client(tmp_path).post("/stakeholders/facilitate", json={"dry_run": True})
    assert r.status_code == 401


def test_dry_run_estimate(tmp_path):
    r = _client(tmp_path).post("/stakeholders/facilitate",
                               json={"dry_run": True, "posture": "prototype", "tier": "cheap"}, headers=_H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_key"] and body["posture"] == "prototype" and body["tier"] == "cheap"
    assert body["estimated_cost"] >= 0 and body["projected_calls"] > 0


def test_dry_run_fails_closed_without_budget(tmp_path):
    # H-13 — a green preview must not precede a 412 confirm; no blocking budget → 412 on the dry_run too
    r = _client(tmp_path, manager=_Manager([])).post(
        "/stakeholders/facilitate", json={"dry_run": True}, headers=_H)
    assert r.status_code == 412


def test_confirm_requires_run_key(tmp_path):
    r = _client(tmp_path).post("/stakeholders/facilitate", json={"posture": "scrutiny"}, headers=_H)
    assert r.status_code == 400


def test_confirm_run_key_mismatch_409(tmp_path):
    # a cheap dry-run's run_key can't authorize a premium confirm (H-10)
    c = _client(tmp_path)
    dry = c.post("/stakeholders/facilitate", json={"dry_run": True, "tier": "cheap"}, headers=_H).json()
    r = c.post("/stakeholders/facilitate",
               json={"tier": "premium", "run_key": dry["run_key"]}, headers=_H)  # premium ≠ cheap key
    assert r.status_code == 409


def test_confirm_happy_path_spawns(tmp_path, monkeypatch):
    spawned = {}

    def fake_start(cfg, roster, *, cost_tracker=None):
        spawned["sid"] = "kp-fake"
        return {"session_id": "kp-fake", "run_key": "rk", "status": "in_progress", "deduped": False}

    monkeypatch.setattr(srv, "start_facilitation", fake_start)
    c = _client(tmp_path)
    dry = c.post("/stakeholders/facilitate", json={"dry_run": True, "tier": "cheap"}, headers=_H).json()
    r = c.post("/stakeholders/facilitate", json={"tier": "cheap", "run_key": dry["run_key"]}, headers=_H)
    assert r.status_code == 200, r.text
    assert r.json()["session_id"] == "kp-fake" and spawned["sid"] == "kp-fake"


def test_status_and_cancel(tmp_path):
    c = _client(tmp_path)
    s = c.get("/stakeholders/facilitate/kp-unknown", headers=_H)
    assert s.status_code == 200 and s.json()["status"] == "unknown"
    x = c.post("/stakeholders/facilitate/kp-unknown/cancel", headers=_H)
    assert x.status_code == 404 and x.json()["cancelled"] is False
