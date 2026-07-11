"""M1 — the `_cloud_capability` effective-posture seam (CLOUD_MIRROR_GRANT_PLAN.md §2.2 / FR-13).

Two kinds of test:

1. **Characterization (behavior-preserving).** These encode TODAY's cloud posture and must pass BOTH
   on the unrefactored code (run first, per R1-S4) AND after the seam refactor — proving the collapse to
   one seam is byte-behavior-preserving when no grant store is configured. Cloud is read/preview-only:
   the 7 write/chat gates deny with ``cloud_write_deferred``; the 4 read/preview POSTs are NOT cloud-denied.
2. **Structural default-deny guard (R1-S2).** A *new* cloud POST route wired to neither list must return
   501 — this passes ONLY after the refactor adds the guard (it would fail-open on the unrefactored code).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

_HOST = {"host": "cloud.example.com"}   # a non-loopback Host (a real cloud surface)

# TODAY's cloud posture, verified against web.py on origin/main:
CLOUD_DENIED_WRITES = {
    "/capture/apply": {"value_path": "conventions.tz", "value": "UTC", "csrf": "x"},
    "/audience/set": {"audience": "advanced", "csrf": "x"},
    "/concierge/instantiate": {"posture": "prototype", "csrf": "x", "intent": "x"},
    "/concierge/friction": {"friction": "f", "what_happened": "w", "implication": "i",
                            "csrf": "x", "intent": "x"},
    "/concierge/chat/message": {"message": "hi"},
    "/concierge/chat/confirm": {"proposal_id": "p", "csrf": "x"},
    "/concierge/chat/reset": {"csrf": "x"},
}
CLOUD_ALLOWED_POSTS = {
    "/capture/preview": {"value_path": "conventions.tz", "value": "UTC"},
    "/concierge/instantiate/preview": {"posture": "prototype"},
    "/concierge/chat/pending": {},
    "/concierge/chat/discard": {"proposal_id": "p", "csrf": "x"},
}


def _cloud_client(tmp_path):
    return TestClient(build_kickoff_app(tmp_path, cloud=True), headers=_HOST)


def _code(resp):
    try:
        return resp.json().get("code")
    except Exception:
        return None


# --------------------------------------------------------------------------- characterization (both)


def test_cloud_write_and_chat_routes_are_deferred(tmp_path):
    c = _cloud_client(tmp_path)
    for path, form in CLOUD_DENIED_WRITES.items():
        r = c.post(path, data=form)
        assert r.status_code == 501, f"{path} should be cloud-deferred, got {r.status_code}"
        assert _code(r) == "cloud_write_deferred", f"{path} code={_code(r)}"


def test_cloud_chat_page_is_unavailable(tmp_path):
    r = _cloud_client(tmp_path).get("/concierge/chat")
    assert r.status_code == 200
    assert "unavailable on cloud" in r.text.lower()


def test_cloud_read_and_preview_posts_are_not_deferred(tmp_path):
    c = _cloud_client(tmp_path)
    for path, form in CLOUD_ALLOWED_POSTS.items():
        r = c.post(path, data=form)
        assert _code(r) != "cloud_write_deferred", f"{path} must NOT be cloud-deferred (read/preview)"
        assert r.status_code != 501, f"{path} returned 501 but is a read/preview route"


def test_local_writes_are_not_cloud_deferred(tmp_path):
    # Non-cloud (local): the seam allows — the write gates fall through to CSRF/mode/etc., never cloud.
    c = TestClient(build_kickoff_app(tmp_path, cloud=False), headers={"host": "127.0.0.1:8000"})
    for path, form in CLOUD_DENIED_WRITES.items():
        r = c.post(path, data=form)
        assert _code(r) != "cloud_write_deferred", f"{path} local must not be cloud-deferred"


# --------------------------------------------------------------------------- structural guard (post-refactor)


def test_structural_default_deny_for_unregistered_cloud_write(tmp_path):
    # R1-S2: a NEW cloud POST route wired to neither the seam nor the read allowlist must fail CLOSED.
    # (On the unrefactored code this route would 404/200 — the guard makes it 501.)
    app = build_kickoff_app(tmp_path, cloud=True)

    @app.post("/synthetic/write")
    def _synthetic():   # a route that "forgot" the seam
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True}, status_code=200)

    c = TestClient(app, headers=_HOST)
    r = c.post("/synthetic/write", data={})
    assert r.status_code == 501, "an un-seamed cloud write route must default-deny (R1-S2)"
    assert _code(r) == "cloud_write_deferred"


def test_every_post_route_is_classified_in_exactly_one_set(tmp_path):
    # Lockstep guard: every real @app.post must be in exactly one cloud set, so a NEW route forces a
    # conscious read-vs-write classification at test time (not a silent runtime default-deny surprise).
    from startd8.kickoff_experience.web import _CLOUD_READONLY_POSTS, _CLOUD_SEAM_GATED_POSTS

    app = build_kickoff_app(tmp_path, cloud=True)
    post_paths = {
        r.path for r in app.routes
        if "POST" in (getattr(r, "methods", None) or set())
    }
    classified = _CLOUD_READONLY_POSTS | _CLOUD_SEAM_GATED_POSTS
    assert not (_CLOUD_READONLY_POSTS & _CLOUD_SEAM_GATED_POSTS), "a route is in BOTH sets"
    assert not (post_paths - classified), \
        f"unclassified POST route(s) — add to a cloud set: {post_paths - classified}"
    assert not (classified - post_paths), \
        f"cloud set references a non-existent route: {classified - post_paths}"
