"""Tier B / M3 — B2 tenant-scoped routers.py (FR-TEN-2/3).

Static isolation verification: when `deployment.tenant` is declared, entities that carry the owner FK
get principal-scoped CRUD (list filters by owner; get/update/delete 404 on a non-owned row; create
server-sets the owner), while entities WITHOUT the owner FK stay unscoped. The owner field is
self-described in the header so the schema-only skip-hook verifies the scoped file with no app.yaml.
(The runtime cross-principal HTTP-denial proof needs Postgres — deferred PG integration test.)
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.crud_generator import render_routers
from startd8.backend_codegen.drift import check_drift, embedded_tenant_field
from startd8.backend_codegen.htmx_generator import render_web

pytestmark = pytest.mark.unit

SCHEMA = """\
model User {
  id String @id
}

model Note {
  id      String @id
  text    String
  ownerId String
}

model Lookup {
  id    String @id
  label String
}
"""
OWNER = "ownerId"


def test_unscoped_when_no_tenant_is_byte_identical_to_today():
    assert render_routers(SCHEMA, tenant_owner_field=None) == render_routers(SCHEMA)
    assert "# startd8-tenant:" not in render_routers(SCHEMA)
    assert "require_principal" not in render_routers(SCHEMA)


def test_scoped_routers_scope_owner_entities_only():
    text = render_routers(SCHEMA, tenant_owner_field=OWNER)
    assert f"# startd8-tenant: {OWNER}" in text  # self-described for the skip-hook
    assert "from .auth import Principal, require_principal" in text
    compile(text, "app/routers.py", "exec")

    # Note (has ownerId) is scoped on every path.
    assert "select(Note).where(Note.ownerId == principal.id)" in text  # list
    assert "obj.ownerId = principal.id" in text  # create server-sets owner
    assert "if obj is None or obj.ownerId != principal.id:" in text  # get/update/delete 404 guard
    assert text.count("principal: Principal = Depends(require_principal)") == 5  # list/create/get/update/delete

    # Lookup + User have no owner FK → unscoped (no principal dep, no where on them).
    assert "select(Lookup).where" not in text
    assert "def list_lookup(session: Session = Depends(get_session)) -> list[LookupRead]:" in text


def test_scoped_routers_skip_hook_verifies_with_schema_only():
    text = render_routers(SCHEMA, tenant_owner_field=OWNER)
    assert embedded_tenant_field(text) == OWNER
    # owned_file_in_sync passes ONLY schema_text — no app.yaml — and must re-derive the owner FK.
    assert owned_file_in_sync(SCHEMA, text) is True


def test_scoped_routers_drift_stale_and_tamper():
    text = render_routers(SCHEMA, tenant_owner_field=OWNER)
    changed = SCHEMA + "\nmodel Extra {\n  id String @id\n}\n"
    assert check_drift(changed, text).status == "stale"
    tampered = text.replace("Note.ownerId == principal.id", "True")  # weaken the scope = tamper
    assert check_drift(SCHEMA, tampered).status == "tampered"


def test_render_backend_threads_tenant_to_routers_and_web():
    deployed_plain = dict(render_backend(SCHEMA, deployment_mode="deployed"))
    deployed_tenant = dict(render_backend(SCHEMA, deployment_mode="deployed", tenant_owner_field=OWNER))
    for f in ("app/routers.py", "app/web.py"):
        assert "require_principal" not in deployed_plain[f]
        assert "principal" in deployed_tenant[f]
    assert "select(Note).where(Note.ownerId == principal.id)" in deployed_tenant["app/routers.py"]
    assert "select(Note).where(Note.ownerId == principal.id)" in deployed_tenant["app/web.py"]


# --- web.py (HTMX UI) scoping --------------------------------------------------------------------

def _entity_block(web: str, name: str) -> str:
    start = web.index(f"# --- {name} ---")
    nxt = web.find("# --- ", start + 1)
    return web[start:nxt] if nxt != -1 else web[start:]


def test_unscoped_web_is_byte_identical_to_today():
    assert render_web(SCHEMA, tenant_owner_field=None) == render_web(SCHEMA)
    assert "# startd8-tenant:" not in render_web(SCHEMA)
    assert "require_principal" not in render_web(SCHEMA)


def test_web_scopes_owner_entity_every_handler():
    text = render_web(SCHEMA, tenant_owner_field=OWNER)
    assert f"# startd8-tenant: {OWNER}" in text
    assert "from .auth import Principal, require_principal" in text
    compile(text, "app/web.py", "exec")
    note = _entity_block(text, "Note")
    assert "select(Note).where(Note.ownerId == principal.id)" in note  # list
    assert "obj.ownerId = principal.id" in note  # create server-sets owner
    assert "if item is None or item.ownerId != principal.id:" in note  # detail/edit 404 guard
    assert "if obj is None or obj.ownerId != principal.id:" in note  # update 404 guard
    assert "if obj is not None and obj.ownerId == principal.id:" in note  # delete ownership gate


def test_web_safety_net_no_unguarded_query_for_scoped_entity():
    # The keystone leak-guard: in the SCOPED entity's block, NO bare ownership-free guard or
    # unscoped select may survive (a single miss would expose another principal's rows via the UI).
    note = _entity_block(render_web(SCHEMA, tenant_owner_field=OWNER), "Note")
    assert "    if item is None:\n" not in note
    assert "    if obj is None:\n" not in note
    assert "    if obj is not None:\n" not in note
    assert "select(Note))" not in note  # the unscoped list query must be gone
    # ...while an UNSCOPED entity keeps the plain guards and is untouched.
    lookup = _entity_block(render_web(SCHEMA, tenant_owner_field=OWNER), "Lookup")
    assert "    if item is None:\n" in lookup
    assert "require_principal" not in lookup


def test_web_scoped_skip_hook_and_drift():
    text = render_web(SCHEMA, tenant_owner_field=OWNER)
    assert owned_file_in_sync(SCHEMA, text) is True  # fastapi-web: schema-only skip-hook re-derives tenant
    tampered = text.replace("Note.ownerId == principal.id", "True")
    assert check_drift(SCHEMA, tampered).status == "tampered"
