"""Deterministic contract-test emitter (Python contract-codegen, rung 4 — semantic tests).

The schema-derived half of "tests that verify the semantic validation of the code". Projects the
``.prisma`` contract into an owned, ``$0``-LLM, drift-checked ``tests/test_contract.py`` whose
assertions are **executable semantic guarantees**, not just "it compiles":

- **round-trip** — ``Schema.model_validate(inst.model_dump()) == inst`` per entity (data fidelity).
- **field presence + optionality** — every contract scalar (incl. FK scalars) is a model field with
  the right required/optional shape (no dropped or silently-retyped field).
- **enum domain** — an out-of-domain enum value raises ``ValidationError`` (literal-set integrity).

These are exactly the invariants derivable from the contract alone, so they are deterministic and
byte-identical on regen. The genuinely *behavioral* assertions (AI-pass output quality) stay
LLM-authored (rung 5) — they need real model output and cannot be projected from the schema.

Mirrors the other backend_codegen emitters: a ``#`` GENERATED header (pytest ignores comments), the
``python-tests-contract`` artifact kind, recognized/verified by the shared provider + drift path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header
from .crud_generator import _pk_field
from .htmx_generator import _confirm_field

CONTRACT_TESTS_PATH = "tests/test_contract.py"
COMPLETENESS_TESTS_PATH = "tests/test_completeness.py"
ROUTE_SMOKE_TESTS_PATH = "tests/test_route_smoke.py"
_KIND = "python-tests-contract"
_COMPLETENESS_KIND = "python-tests-completeness"
_ROUTE_SMOKE_KIND = "python-tests-routes"

_SHIM = (
    "import sys\n"
    "from pathlib import Path\n\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
)

# Prisma scalar -> a valid sample value as Python source. Values are chosen to validate under the
# generated Pydantic models with no constraints (the renderer emits plain types), and to round-trip
# byte-stably. Decimal/DateTime go through Pydantic's lax coercion (str -> Decimal/datetime).
_SCALAR_SAMPLE: Dict[str, str] = {
    "String": '"sample"',
    "Boolean": "False",
    "Int": "0",
    "BigInt": "0",
    "Float": "0.0",
    "Decimal": '"0"',
    "DateTime": '"2020-01-01T00:00:00"',
    "Json": "None",
    "Bytes": 'b"x"',
}


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _sample_literal(field: PrismaField, schema: PrismaSchema) -> str:
    """A valid value for *field* as Python source. ``[]`` for lists; first member for enums."""
    if field.is_list:
        return "[]"  # empty list validates for any list[...] and round-trips
    if field.type in schema.enums:
        vals = schema.enums[field.type]
        return f'"{vals[0]}"' if vals else '""'
    return _SCALAR_SAMPLE.get(field.type, "None")  # default None covers Any/unmappable scalars


def _required_kwargs(schema: PrismaSchema, name: str) -> str:
    """A ``{"f": value, ...}`` dict literal of an entity's required scalars (source order)."""
    required = [f for f in schema.scalar_fields(name) if not f.is_optional]
    return "{" + ", ".join(f'"{f.name}": {_sample_literal(f, schema)}' for f in required) + "}"


def _entity_block(schema: PrismaSchema, name: str) -> str:
    """The three semantic test functions for one entity (no trailing newline)."""
    cls = f"{name}Schema"
    low = name.lower()
    scalars = schema.scalar_fields(name)
    kw = _required_kwargs(schema, name)
    lines: List[str] = []

    # 1. round-trip fidelity
    lines += [
        f"def test_{low}_roundtrip():",
        f"    inst = {cls}(**{kw})",
        f"    assert {cls}.model_validate(inst.model_dump()) == inst",
        "",
        "",
    ]

    # 2. field presence + optionality (FK scalars included — they are scalars)
    lines.append(f"def test_{low}_fields():")
    lines.append(f"    f = {cls}.model_fields")
    if scalars:
        for fld in scalars:
            pred = (
                f"not f[{fld.name!r}].is_required()"
                if fld.is_optional
                else f"f[{fld.name!r}].is_required()"
            )
            lines.append(f"    assert {fld.name!r} in f and {pred}")
    else:
        lines.append("    assert set(f) == set()")

    # 3. enum-domain integrity (first non-list enum field, if any)
    enum_fields = [f for f in scalars if f.type in schema.enums and not f.is_list]
    if enum_fields:
        ef = enum_fields[0]
        lines += [
            "",
            "",
            f"def test_{low}_{ef.name}_enum_domain():",
            f"    bad = dict({kw})",
            f'    bad[{ef.name!r}] = "__not_a_valid_enum_member__"',
            "    with pytest.raises(ValidationError):",
            f"        {cls}(**bad)",
        ]
    return "\n".join(lines)


def render_contract_tests(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``tests/test_contract.py`` — deterministic semantic tests over the contract.

    Byte-stable: entities in schema source order, scalars in field order, fixed sample values. The
    ``sys.path`` shim makes ``import app`` work regardless of how pytest is invoked.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    header = _header(source_file, sha, _KIND)

    model_imports = (
        "from app.models import " + ", ".join(f"{n}Schema" for n in names)
        if names
        else "# (no models in the contract — nothing to test)"
    )
    preamble = (
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\n"
        "import pytest\n"
        "from pydantic import ValidationError\n\n"
        f"{model_imports}"
    )

    sections = [header + "\n\n" + preamble]
    sections.extend(_entity_block(schema, n) for n in names)
    return "\n\n\n".join(sections) + "\n"


def render_completeness_tests(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    manifest: Optional[Dict[str, Any]] = None,
) -> str:
    """Render ``tests/test_completeness.py`` — FR-9: the completeness *formula* as an executable check.

    Pins the generated ``compute_completeness`` at its endpoints, mode-agnostically: a fully-populated
    model scores ``1.0`` with no nudges; an empty model scores ``0.0`` with one nudge per *included*
    entity (the manifest ``exclude`` set drops join/system tables from the denominator). The expected
    values are baked literals computed here, so a bug in the generated function (wrong rounding,
    off-by-one denominator, miscounted nudges) flips the test red.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    excluded = {str(e) for e in (manifest.get("exclude") or [])} if manifest else set()
    included = [n for n in names if n not in excluded]

    header = _header(source_file, sha, _COMPLETENESS_KIND)
    preamble = _SHIM + "\nfrom app.completeness import compute_completeness"

    if not included:
        # Empty/all-excluded contract → the generated function returns 1.0 for any input.
        block = (
            "def test_completeness_trivial():\n"
            "    assert compute_completeness({}).score == 1.0\n"
            "    assert compute_completeness({}).nudges == []"
        )
        return header + "\n\n" + preamble + "\n\n\n" + block + "\n"

    full = "{" + ", ".join(f'"{n}": 99' for n in names) + "}"
    blocks = [
        (
            "def test_completeness_full():\n"
            f"    r = compute_completeness({full})\n"
            "    assert r.score == 1.0\n"
            "    assert r.nudges == []"
        ),
        (
            "def test_completeness_empty():\n"
            "    r = compute_completeness({})\n"
            "    assert r.score == 0.0\n"
            f"    assert len(r.nudges) == {len(included)}"
        ),
    ]
    return header + "\n\n" + preamble + "\n\n\n" + "\n\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Route-smoke suite (rung 5 floor — generated HTTP smoke over every GET route)
# ---------------------------------------------------------------------------

_INT_PK_TYPES = frozenset({"Int", "BigInt"})

# The suite body is a fixed template; only the baked schema maps vary. Kept as
# one literal so the emitted module reads as a coherent program, not codegen
# confetti. Placeholders: {tables} {pk_map}.
_ROUTE_SMOKE_BODY = '''\
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
_engine = create_engine(f"sqlite:///{{_smoke_db}}")
SQLModel.metadata.create_all(_engine)


def _override_get_session():
    with Session(_engine) as s:
        yield s


app.dependency_overrides[get_session] = _override_get_session

# Baked from the contract: every entity table (reset/seed surface) and the
# single-column-PK entities (route param filling + PK synthesis on seed rows).
_TABLES = {tables}
_PK = {pk_map}
_FILL = {{name.lower(): name for name in _PK}}
# Entities (lowercased) carrying the confirm toggle — baked from the contract's `confirmed` field.
_CONFIRM = {confirm}

_OK_STATUSES = frozenset({{200, 303, 307, 308}})
_SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"
_PARAM_RE = re.compile(r"{{([^}}:]+)[^}}]*}}")


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
    for name in _TABLES:
        session.exec(delete(getattr(tables, name)))
    session.commit()


def _load_rows(session, seed_path):
    import yaml

    data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {{}}
    for entity, rows in (data.get("rows") or {{}}).items():
        cls = getattr(tables, entity, None)
        if cls is None:
            continue
        pk = _PK.get(entity)
        for n, row in enumerate(rows or (), start=1):
            row = dict(row)
            if pk is not None and pk[0] not in row:
                row[pk[0]] = n if pk[1] == "int" else f"{{entity.lower()}}-{{n}}"
            session.add(cls(**row))
    session.commit()


def _get_paths():
    return sorted({{
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "GET" in (r.methods or ())
    }})


def _fill_path(path, session):
    """Resolve {{param}} placeholders from seeded rows; None when unfillable."""
    params = _PARAM_RE.findall(path)
    if not params:
        return path
    if len(params) > 1:
        return None  # multi-param routes are out of v1 smoke scope
    segments = [s for s in path.split("/") if s and not s.startswith("{{")]
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

    A route answering outside {{200, 3xx-redirect}} — 404, 422, 500 — fails the
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
                    failures.append(f"GET {{target}} -> {{resp.status_code}}")
                elif resp.status_code == 200:
                    body = resp.text
                    if not body.strip():
                        failures.append(f"GET {{target}} -> 200 with empty body")
                    elif "Traceback (most recent call last)" in body:
                        failures.append(f"GET {{target}} -> 200 with a traceback body")
    finally:
        with Session(_engine) as session:
            _reset(session)

    assert checked > 0, "route walk found no smokable GET routes"
    assert not failures, (
        f"[{{case_id}}] {{len(failures)}} route(s) failed smoke:\\n  "
        + "\\n  ".join(failures)
    )


def test_confirm_routes_registered():
    """Each `confirmed`-bearing entity exposes POST /ui/<e>/{{id}}/confirm (AR-5 / FR-CA-8).

    GET-smoke proves a page renders, not that an action exists — exactly how AR-5 slipped
    through. This asserts the suggest->confirm verb's route is *registered*, so a regression
    that drops the toggle is caught at the generated-app level, not only in the SDK.
    """
    post_paths = {{
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "POST" in (r.methods or ())
    }}
    missing = [e for e in _CONFIRM
               if ("/ui/" + e + "/{{id}}/confirm") not in post_paths]
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
            resp = client.post(path, json={{}})
            assert resp.status_code != 404, f"POST {{path}} -> 404 (route not mounted)"
'''


def render_route_smoke_tests(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``tests/test_route_smoke.py`` — generated HTTP smoke over every GET route.

    The rung-5 floor (strtd8 §8 F-8): the rung-4 tests are data/function-level only, so an
    app can ship hundreds of live routes with zero tests that make an HTTP request — which
    is exactly the layer where the campaign defects lived (bare ``/value-map`` 422,
    provenance rows invisible in every list view). This suite walks ``app.routes`` at run
    time — so view/user routers mounted through the ``user_routers`` seam are covered, not
    just the backend's own — and GETs each route per seed fixture (``seeds/test-user-*``:
    the empty user proves empty states render; populated users prove rows render). $0 LLM,
    in-process ``TestClient``, no browser. Deterministic: only the baked entity maps vary
    with the contract.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    header = _header(source_file, sha, _ROUTE_SMOKE_KIND)

    pk_entries: List[str] = []
    for name in names:
        pk = next((f for f in schema.scalar_fields(name) if f.is_id), None)
        if pk is not None:
            py_type = "int" if pk.type in _INT_PK_TYPES else "str"
            pk_entries.append(f'"{name}": ("{pk.name}", "{py_type}")')

    tables_literal = "[" + ", ".join(f'"{n}"' for n in names) + "]"
    pk_literal = "{" + ", ".join(pk_entries) + "}"
    # Confirmed-bearing entities get the confirm-route existence check (FR-CA-8). A single-column
    # PK is required for the by-id route — same gate the generator applies.
    confirm_names = [
        n.lower()
        for n in names
        if _confirm_field(schema, n) is not None
        and _pk_field(schema, n) is not None
    ]
    confirm_literal = "[" + ", ".join(f'"{n}"' for n in confirm_names) + "]"
    body = _ROUTE_SMOKE_BODY.format(
        tables=tables_literal, pk_map=pk_literal, confirm=confirm_literal
    )
    return header + "\n\n" + body
