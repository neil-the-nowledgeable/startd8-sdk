"""M-CM3 — web Concierge surface + hardening."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.kickoff_experience.telemetry import (  # noqa: E402
    EV_FRICTION_LOGGED,
    EV_KICKOFF_INSTANTIATED,
    EV_SURVEY_VIEWED,
    record_events,
)
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # A package-less project (no docs/kickoff/inputs/) — the Concierge instantiate target.
    return TestClient(build_kickoff_app(tmp_path), headers={"host": "127.0.0.1:8000"})


def _csrf_and_intents(client: TestClient):
    html = client.get("/concierge").text
    csrf = re.search(r"name='csrf' value='([^']+)'", html).group(1)
    # Two forms (instantiate, friction) → two intent tokens, in document order.
    tokens = re.findall(r"name='intent' value='([^']+)'", html)
    return csrf, tokens


# --- the page + parity payload -----------------------------------------------------------------

def test_concierge_page_renders_with_frame_deny(client: TestClient) -> None:
    r = client.get("/concierge")
    assert r.status_code == 200
    assert "Concierge" in r.text and "Survey" in r.text
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_concierge_json_is_the_shared_view_model(client: TestClient) -> None:
    r = client.get("/concierge.json")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == 1
    assert body["instantiate_offer"]["package_state"] == "missing"
    assert "friction_form" in body and "next_action" in body


def test_overview_links_to_concierge(client: TestClient) -> None:
    assert "/concierge" in client.get("/").text


# --- preview writes nothing (R2-S1) ------------------------------------------------------------

def test_instantiate_preview_writes_nothing(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/concierge/instantiate/preview", data={"posture": "prototype"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["writes"]
    assert not (tmp_path / "docs" / "kickoff" / "inputs").exists()  # no write


# --- instantiate apply + post-apply reconciliation (R3-S2) -------------------------------------

def test_instantiate_apply_creates_package_and_reconciles(client: TestClient, tmp_path: Path) -> None:
    csrf, tokens = _csrf_and_intents(client)
    with record_events() as events:
        r = client.post("/concierge/instantiate",
                        data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["code"] == "ok" and body["written_count"] > 0
    # Post-apply reconciliation: package_state is now complete.
    assert body["package_state"] == "complete"
    assert (tmp_path / "docs" / "kickoff" / "inputs" / "conventions.yaml").exists()
    assert EV_KICKOFF_INSTANTIATED in [e.name for e in events]


def test_concierge_get_emits_survey_viewed(client: TestClient) -> None:
    with record_events() as events:
        client.get("/concierge")
    assert EV_SURVEY_VIEWED in [e.name for e in events]


# --- hardening: host allowlist (R1-S8), replay (R3-S1) -----------------------------------------

def test_instantiate_rejects_non_loopback_host(tmp_path: Path) -> None:
    client = TestClient(build_kickoff_app(tmp_path), headers={"host": "evil.example.com"})
    csrf, tokens = _csrf_and_intents(client)  # GET still works
    r = client.post("/concierge/instantiate",
                    data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden_host"


def test_replayed_intent_is_refused(client: TestClient) -> None:
    csrf, tokens = _csrf_and_intents(client)
    first = client.post("/concierge/instantiate",
                        data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert first.status_code == 200
    # Reusing the same intent token must not write twice.
    replay = client.post("/concierge/instantiate",
                         data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert replay.status_code == 409
    assert replay.json()["code"] == "replay"


# --- friction (validation, timestamp, telemetry privacy) --------------------------------------

def test_friction_apply_logs_with_timestamp(client: TestClient, tmp_path: Path) -> None:
    csrf, tokens = _csrf_and_intents(client)
    with record_events() as events:
        r = client.post("/concierge/friction", data={
            "friction": "grammar rejected my PRD", "what_happened": "needs reformat",
            "implication": "F-4 path", "csrf": csrf, "intent": tokens[1],
        })
    assert r.status_code == 200, r.text
    log = (tmp_path / "concierge-friction.jsonl").read_text()
    assert "grammar rejected my PRD" in log and '"ts":' in log
    # Telemetry privacy (R2-F4): the friction event carries NO free-text.
    fl = next(e for e in events if e.name == EV_FRICTION_LOGGED)
    assert "grammar rejected my PRD" not in str(fl.attributes)


def test_friction_blank_field_rejected_typed(client: TestClient) -> None:
    csrf, tokens = _csrf_and_intents(client)
    r = client.post("/concierge/friction", data={
        "friction": "", "what_happened": "x", "implication": "y",
        "csrf": csrf, "intent": tokens[1],
    })
    assert r.status_code == 400
    assert r.json()["code"] == "missing_required_field"


def test_preview_mode_refuses_concierge_write(tmp_path: Path) -> None:
    client = TestClient(build_kickoff_app(tmp_path, mode="preview"), headers={"host": "127.0.0.1"})
    csrf, tokens = _csrf_and_intents(client)
    r = client.post("/concierge/instantiate",
                    data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert r.status_code == 403
    assert r.json()["code"] == "preview_only"


def test_intent_store_is_bounded() -> None:
    # Code-review fix: abandoned intents (viewed, never applied) must not grow without limit.
    from startd8.kickoff_experience.web import _IntentStore

    store = _IntentStore()
    for _ in range(_IntentStore._MAX + 50):
        store.issue("instantiate", "d")
    assert len(store._intents) <= _IntentStore._MAX
