# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-routes
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("sqlmodel")
pytest.importorskip("httpx")

from fastapi.routing import APIRoute  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import Session, SQLModel, delete, select  # noqa: E402

from app import tables  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

# F-12: this suite's _reset() DELETEs every table. It MUST run against a
# dedicated, isolated database — NEVER the app's real engine. The old
# conditional isolation no-op'd whenever another test module imported app.db
# first, so _reset ran against the operator's production `app.db` and emptied
# it (a regen's pytest run wiped a real 116-row value model + 4 artifacts).
# Fix: own temp engine, UNCONDITIONALLY, plus a get_session dependency override
# so the seed/reset writes AND the routes under test both use the temp DB. The
# real app.db engine is never written to here (the app import only create_all's
# it via the lifespan, which is harmless/idempotent).
_smoke_db = Path(tempfile.mkdtemp(prefix="route-smoke-")) / "smoke.db"
_engine = create_engine(f"sqlite:///{_smoke_db}")
SQLModel.metadata.create_all(_engine)


def _override_get_session():
    with Session(_engine) as s:
        yield s


app.dependency_overrides[get_session] = _override_get_session


def _engine_is_temp() -> bool:
    """F-12 fail-loud tripwire. _reset() DELETEs every table, so it MUST run against the
    dedicated throwaway engine above — never a real DB. Structurally _engine is always a
    mkdtemp sqlite file, so this can only fail if a future change re-points it at the real
    ./app.db; then _reset REFUSES (skips loud) rather than wipe it. Opt out with
    STARTD8_ALLOW_NONTEMP_RESET=1 for a deliberately disposable real-path DB."""
    if os.environ.get("STARTD8_ALLOW_NONTEMP_RESET") == "1":
        return True
    url = str(_engine.url)
    if not url.startswith("sqlite:///"):
        return False  # remote / non-sqlite / engine default -> never reset
    try:
        db_path = Path(url[len("sqlite:///"):]).resolve()
        tmp = Path(tempfile.gettempdir()).resolve()
        return tmp in db_path.parents or db_path == tmp
    except (OSError, ValueError):
        return False

# Baked from the contract: every entity table (reset/seed surface) and the
# single-column-PK entities (route param filling + PK synthesis on seed rows).
_TABLES = ["OrderConfirmation"]
_PK = {"OrderConfirmation": ("id", "str")}
_FILL = {name.lower(): name for name in _PK}
# Entities (lowercased) carrying the confirm toggle — baked from the contract's `confirmed` field.
_CONFIRM = []

_OK_STATUSES = frozenset({200, 303, 307, 308})
_SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"
_PARAM_RE = re.compile(r"{([^}:]+)[^}]*}")


def _seed_cases():
    """(case_id, seed_path|None) per discovered fixture; always includes unseeded."""
    cases = [("unseeded", None)]
    try:
        import yaml  # noqa: F401
    except ImportError:
        return cases  # no yaml -> still smoke every no-param route, unseeded
    if _SEEDS_DIR.is_dir():
        for p in sorted(_SEEDS_DIR.glob("test-user-*.yaml")):
            cases.append((p.stem, p))
    return cases


_CASES = _seed_cases()


def _reset(session):
    if not _engine_is_temp():  # F-12 belt-and-suspenders: never DELETE against a real DB
        pytest.skip(
            "route-smoke refuses to DELETE: its engine is not a temp database ("
            + str(_engine.url) + ") — running this reset could WIPE a real DB (F-12). "
            "Set STARTD8_ALLOW_NONTEMP_RESET=1 if it is disposable."
        )
    for name in _TABLES:
        session.exec(delete(getattr(tables, name)))
    session.commit()


def _load_rows(session, seed_path):
    import yaml

    data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
    for entity, rows in (data.get("rows") or {}).items():
        cls = getattr(tables, entity, None)
        if cls is None:
            continue
        pk = _PK.get(entity)
        for n, row in enumerate(rows or (), start=1):
            row = dict(row)
            if pk is not None and pk[0] not in row:
                row[pk[0]] = n if pk[1] == "int" else f"{entity.lower()}-{n}"
            session.add(cls(**row))
    session.commit()


def _get_paths():
    return sorted({
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "GET" in (r.methods or ())
    })


def _fill_path(path, session):
    """Resolve {param} placeholders from seeded rows; None when unfillable."""
    params = _PARAM_RE.findall(path)
    if not params:
        return path
    if len(params) > 1:
        return None  # multi-param routes are out of v1 smoke scope
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    prefix = segments[1] if len(segments) > 1 and segments[0] == "ui" else (
        segments[0] if segments else ""
    )
    entity = _FILL.get(prefix)
    if entity is None:
        return None
    row = session.exec(select(getattr(tables, entity))).first()
    if row is None:
        return None  # empty fixture -> by-id routes have nothing to point at
    return _PARAM_RE.sub(str(getattr(row, _PK[entity][0])), path, count=1)


@pytest.mark.parametrize(
    ("case_id", "seed_path"), _CASES, ids=[c[0] for c in _CASES],
)
def test_every_get_route_smokes(case_id, seed_path):
    """GET every mounted route (incl. user_routers/views) against this fixture.

    A route answering outside {200, 3xx-redirect} — 404, 422, 500 — fails the
    suite: the empty fixture proves empty states render; populated fixtures
    prove rows render. Unfillable parameterized routes are skipped, not failed.
    """
    with Session(_engine) as session:
        _reset(session)
        if seed_path is not None:
            _load_rows(session, seed_path)

    failures, checked = [], 0
    try:
        with _testclient.TestClient(app) as client, Session(_engine) as session:
            for path in _get_paths():
                target = _fill_path(path, session)
                if target is None:
                    continue
                resp = client.get(target, follow_redirects=False)
                checked += 1
                if resp.status_code not in _OK_STATUSES:
                    failures.append(f"GET {target} -> {resp.status_code}")
                elif resp.status_code == 200:
                    body = resp.text
                    if not body.strip():
                        failures.append(f"GET {target} -> 200 with empty body")
                    elif "Traceback (most recent call last)" in body:
                        failures.append(f"GET {target} -> 200 with a traceback body")
    finally:
        with Session(_engine) as session:
            _reset(session)

    assert checked > 0, "route walk found no smokable GET routes"
    assert not failures, (
        f"[{case_id}] {len(failures)} route(s) failed smoke:\n  "
        + "\n  ".join(failures)
    )


def test_confirm_routes_registered():
    """Each `confirmed`-bearing entity exposes POST /ui/<e>/{id}/confirm (AR-5 / FR-CA-8).

    GET-smoke proves a page renders, not that an action exists — exactly how AR-5 slipped
    through. This asserts the suggest->confirm verb's route is *registered*, so a regression
    that drops the toggle is caught at the generated-app level, not only in the SDK.
    """
    post_paths = {
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "POST" in (r.methods or ())
    }
    missing = [e for e in _CONFIRM
               if ("/ui/" + e + "/{id}/confirm") not in post_paths]
    assert not missing, "confirm route missing for: " + repr(missing)


def test_ai_routes_mounted_if_ai_layer_present():
    """F-9: if this app generated an AI layer, its /ai/* POST routes MUST be mounted.

    GET-smoke can't catch an unmounted POST layer — that's exactly how the AI router shipped
    generated-but-unmounted (every /ai/* pass 404'd). Guarded: an app with no AI layer simply
    skips. A non-404 (200/422/400/503) proves the route is MOUNTED — we never exercise the pass.
    """
    # Detect the AI layer on DISK — importing `app.ai.routes` would rebind the name `app`
    # (the package) over the FastAPI `app` object imported above, breaking `app.routes`.
    if not (Path(__file__).resolve().parents[1] / "app" / "ai" / "routes.py").is_file():
        pytest.skip("no AI layer in this app")
    ai_posts = sorted(
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "POST" in (r.methods or ()) and r.path.startswith("/ai/")
    )
    assert ai_posts, "AI layer present but zero /ai/* POST routes mounted (F-9 regression)"
    # raise_server_exceptions=False: an empty-body POST may 500 inside the pass handler
    # (no key / unparseable input) — that still proves the route is MOUNTED. We only reject 404.
    with _testclient.TestClient(app, raise_server_exceptions=False) as client:
        for path in ai_posts:
            resp = client.post(path, json={})
            assert resp.status_code != 404, f"POST {path} -> 404 (route not mounted)"
