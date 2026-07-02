"""Welcome Mat 2.0 — template download pillar (FR-WM2-1..4, 16).

Covers the manifest accessor (one-inventory/no-drift + dest safety), individual download
(key-closure, posture validation, content type), the bundle (with_authoring split, zip-slip-safe
members, size ceiling), and triple-byte parity (single == bundle == instantiate) across postures.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from startd8.concierge.writes import (  # noqa: E402
    _AUTHORING_FILES,
    _KICKOFF_FILES,
    build_instantiate_plan,
    get_template_entry,
    is_safe_template_dest,
    kickoff_template_manifest,
    render_template_content,
)
from startd8.kickoff_experience import web as web_mod  # noqa: E402
from startd8.kickoff_experience.telemetry import (  # noqa: E402
    EV_TEMPLATE_BUNDLE_DOWNLOADED,
    EV_TEMPLATE_DOWNLOADED,
    FUNNEL_EVENTS,
    record_events,
)
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(build_kickoff_app(tmp_path), headers={"host": "127.0.0.1:8000"})


# --- S1: manifest accessor — one inventory, no drift (FR-WM2-4/16) ------------------------------


def test_manifest_bijects_with_instantiate_lists() -> None:
    entries = kickoff_template_manifest()
    # Exactly the instantiate inventory, no more, no fewer.
    # 12 = 7 kickoff-package files (incl. the stakeholder-panel roster, M0) + 5 authoring files.
    assert len(entries) == len(_KICKOFF_FILES) + len(_AUTHORING_FILES) == 12
    manifest_rels = {e.template_rel for e in entries}
    list_rels = {rel for rel, _ in _KICKOFF_FILES} | {
        rel for rel, _ in _AUTHORING_FILES
    }
    assert manifest_rels == list_rels


def test_manifest_keys_unique_and_dests_safe() -> None:
    entries = kickoff_template_manifest()
    keys = [e.key for e in entries]
    assert len(keys) == len(set(keys))  # closed, unique key space
    for e in entries:
        assert is_safe_template_dest(e.dest)
        assert "/" not in e.key and ".." not in e.key  # single-segment slug


def test_manifest_dests_equal_full_instantiate_plan_paths() -> None:
    # The download set (with authoring) == what instantiate writes with --with-authoring (FR-WM2-16).
    entries = kickoff_template_manifest()
    plan = build_instantiate_plan("/tmp/whatever", "prototype", with_authoring=True)
    assert {e.dest for e in entries} == {w["path"] for w in plan["writes"]}


def test_is_safe_template_dest_rejects_traversal() -> None:
    assert is_safe_template_dest("docs/kickoff/x.md")
    for bad in ("/etc/passwd", "../x", "docs/../../x", "a//b", "a\\b", ""):
        assert not is_safe_template_dest(bad)


# --- S2: individual download (FR-WM2-2) ---------------------------------------------------------


def test_download_individual_file_attachment(client: TestClient) -> None:
    with record_events() as events:
        r = client.get("/templates/file/conventions")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="conventions.yaml"'
    assert r.headers["content-type"].startswith("text/yaml")
    assert r.text == render_template_content(
        get_template_entry("conventions"), "prototype"
    )
    assert [e.name for e in events] == [EV_TEMPLATE_DOWNLOADED]
    assert events[0].attributes == {
        "key": "conventions",
        "group": "package",
        "posture": "prototype",
    }


def test_download_markdown_content_type(client: TestClient) -> None:
    r = client.get("/templates/file/requirements-template")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")


def test_unknown_key_404(client: TestClient) -> None:
    r = client.get("/templates/file/does-not-exist")
    assert r.status_code == 404
    assert r.json()["code"] == "unknown_template"


@pytest.mark.parametrize("evil", ["..", "%2e%2e", "..%2f..%2fetc%2fpasswd"])
def test_key_closure_blocks_traversal(client: TestClient, evil: str) -> None:
    # The invariant is "no traversal input ever serves a file from outside the closed manifest set."
    # A single path segment can't carry a real path; an encoded/garbage key misses the manifest → 404;
    # a bare ".." is client-normalized to the index (HTML, no attachment). None serve a foreign file.
    r = client.get(f"/templates/file/{evil}")
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_invalid_posture_400(client: TestClient) -> None:
    r = client.get("/templates/file/conventions?posture=evil")
    assert r.status_code == 400
    assert r.json()["code"] == "posture_invalid"


def test_posture_substitution_matches_instantiate(client: TestClient) -> None:
    # The download must equal instantiate output at the same posture (R3-F1 / FR-WM2-4).
    for posture in ("prototype", "production"):
        r = client.get(f"/templates/file/conventions?posture={posture}")
        assert r.status_code == 200
        plan = build_instantiate_plan("/tmp/x", posture, with_authoring=True)
        want = next(
            w["content"]
            for w in plan["writes"]
            if w["path"] == "docs/kickoff/inputs/conventions.yaml"
        )
        assert r.text == want
    # prototype vs production actually differ for conventions.yaml (provenance substitution).
    proto = client.get("/templates/file/conventions?posture=prototype").text
    prod = client.get("/templates/file/conventions?posture=production").text
    assert proto != prod


# --- S2: bundle (FR-WM2-3) ----------------------------------------------------------------------


def _zip_names(data: bytes) -> set:
    return set(zipfile.ZipFile(io.BytesIO(data)).namelist())


def test_bundle_with_authoring_split(client: TestClient) -> None:
    full = client.get("/templates/bundle.zip?with_authoring=true")
    pkg = client.get("/templates/bundle.zip?with_authoring=false")
    assert full.status_code == pkg.status_code == 200
    assert full.headers["content-type"] == "application/zip"
    full_names = _zip_names(full.content)
    pkg_names = _zip_names(pkg.content)
    assert pkg_names == {dest for _, dest in _KICKOFF_FILES}
    assert full_names == {dest for _, dest in _KICKOFF_FILES} | {
        dest for _, dest in _AUTHORING_FILES
    }


def test_bundle_emits_event(client: TestClient) -> None:
    with record_events() as events:
        client.get("/templates/bundle.zip?with_authoring=false")
    assert [e.name for e in events] == [EV_TEMPLATE_BUNDLE_DOWNLOADED]
    assert events[0].attributes["count"] == len(_KICKOFF_FILES)


def test_bundle_invalid_posture_400(client: TestClient) -> None:
    assert client.get("/templates/bundle.zip?posture=evil").status_code == 400


def test_bundle_size_ceiling_413(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(web_mod, "_BUNDLE_MAX_UNCOMPRESSED_BYTES", 10)  # absurdly low
    r = client.get("/templates/bundle.zip")
    assert r.status_code == 413
    assert r.json()["code"] == "bundle_too_large"


# --- triple-byte parity: single == bundle == instantiate, every key × posture (R2-S6) ----------


@pytest.mark.parametrize("posture", ["prototype", "production"])
def test_triple_byte_parity(client: TestClient, posture: str) -> None:
    bundle = client.get(f"/templates/bundle.zip?posture={posture}&with_authoring=true")
    zf = zipfile.ZipFile(io.BytesIO(bundle.content))
    plan = build_instantiate_plan("/tmp/x", posture, with_authoring=True)
    plan_by_dest = {w["path"]: w["content"] for w in plan["writes"]}
    for e in kickoff_template_manifest():
        single = client.get(f"/templates/file/{e.key}?posture={posture}").content
        zipped = zf.read(e.dest)
        instantiated = plan_by_dest[e.dest].encode("utf-8")
        assert single == zipped == instantiated, f"drift on {e.key} @ {posture}"


# --- index + discoverability --------------------------------------------------------------------


def test_templates_index_renders_and_overview_links(client: TestClient) -> None:
    idx = client.get("/templates")
    assert idx.status_code == 200
    assert "Kickoff templates" in idx.text
    assert "posture" in idx.text.lower()
    # every key is linkable from the index
    for e in kickoff_template_manifest():
        assert f"/templates/file/{e.key}" in idx.text
    # the home page surfaces the download entry point
    assert "/templates" in client.get("/").text


def test_download_events_registered_in_funnel() -> None:
    assert EV_TEMPLATE_DOWNLOADED in FUNNEL_EVENTS
    assert EV_TEMPLATE_BUNDLE_DOWNLOADED in FUNNEL_EVENTS


# --- home-page Concierge CTA (R2-S7 / FR-WM2-1) ------------------------------------------------


def test_home_page_shows_concierge_cta_when_package_missing(client: TestClient) -> None:
    # The fixture serves a package-less tmp_path → instantiate_offer.needed → a prominent CTA card
    # (driven by build_concierge_view.next_action), not just the generic link.
    html = client.get("/").text
    assert "Create the kickoff package" in html
    assert "/concierge" in html


def test_concierge_cta_helper_modes() -> None:
    from startd8.kickoff_experience.web import _concierge_cta

    # No view-model → degrade to the generic link (no CTA card).
    assert "/concierge" in _concierge_cta(None) and "card" not in _concierge_cta(None)
    # Package complete → generic link.
    complete = _concierge_cta(
        {"instantiate_offer": {"needed": False}, "next_action": {}}
    )
    assert "card" not in complete and "/concierge" in complete
    # Package needed → CTA card carrying the view-model's next_action.
    needed = _concierge_cta(
        {
            "instantiate_offer": {"needed": True},
            "next_action": {
                "title": "Create the kickoff package",
                "detail": "no inputs yet",
            },
        }
    )
    assert "card" in needed and "Create the kickoff package" in needed
