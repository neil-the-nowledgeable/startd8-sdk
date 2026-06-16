"""Phase 3 (static) — render_import determinism, header, drift recognition, identity baking.

No app-runtime deps (the behavioral validation lives in test_import_runtime.py). This pins the
deterministic generation + the two-hash drift wiring (schema + imports.yaml).
"""

from __future__ import annotations

import py_compile
import tempfile
import os

import pytest

from startd8.backend_codegen.assembler import render_backend
from startd8.backend_codegen.drift import check_drift, owned_file_in_sync
from startd8.backend_codegen.import_codegen import render_import

SCHEMA = """\
model Capability {
  id        String  @id @default(cuid())
  source    String  @default("user")
  confirmed Boolean @default(false)
  name      String?
  weight    Int?
}

model Outcome {
  id           String  @id @default(cuid())
  source       String  @default("user")
  confirmed    Boolean @default(false)
  label        String?
  capabilityId String?
  capability   Capability? @relation(fields: [capabilityId], references: [id])
}
"""

IMPORTS = "imports:\n  Capability:\n    format: json\n    identity: name\n  Outcome:\n    format: json\n"


def test_render_is_deterministic():
    a = render_import(SCHEMA, IMPORTS)
    b = render_import(SCHEMA, IMPORTS)
    assert a == b


def test_header_is_two_hash():
    out = render_import(SCHEMA, IMPORTS)
    assert "# startd8-artifact: python-import" in out
    assert "# schema-sha256:" in out
    assert "# imports-sha256:" in out


def test_generated_compiles():
    out = render_import(SCHEMA, IMPORTS)
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, out.encode())
    os.close(fd)
    try:
        py_compile.compile(path, doraise=True)
    finally:
        os.unlink(path)


def test_identity_from_manifest_is_baked():
    out = render_import(SCHEMA, IMPORTS)
    # Capability declared identity: name → baked; Outcome defaults to id
    assert "'Capability': {'fields': ['name'], 'kind': 'name'}" in out
    assert "'Outcome': {'fields': ['id'], 'kind': 'id'}" in out


def test_import_order_is_fk_topological():
    out = render_import(SCHEMA, IMPORTS)
    # Capability (parent) must precede Outcome (FK holder) in IMPORT_ORDER
    line = next(l for l in out.splitlines() if l.startswith("IMPORT_ORDER"))
    assert line.index("Capability") < line.index("Outcome")


def test_conditional_emission():
    assert "app/importer.py" in dict(render_backend(SCHEMA, imports_text=IMPORTS))
    assert "app/importer.py" not in dict(render_backend(SCHEMA))  # opt-in


def test_drift_in_sync_round_trip():
    files = dict(render_backend(SCHEMA, imports_text=IMPORTS))
    imp = files["app/importer.py"]
    assert check_drift(SCHEMA, imp, imports_text=IMPORTS).status == "in_sync"
    assert owned_file_in_sync(SCHEMA, imp, imports_text=IMPORTS) is True


def test_drift_stale_when_imports_change():
    files = dict(render_backend(SCHEMA, imports_text=IMPORTS))
    imp = files["app/importer.py"]
    changed = IMPORTS.replace("identity: name", "identity: id")
    assert check_drift(SCHEMA, imp, imports_text=changed).status == "stale"


def test_skip_hook_errors_without_manifest():
    # the regression Phase 2.5 fixes: without imports_text the two-hash check can't verify → not $0
    files = dict(render_backend(SCHEMA, imports_text=IMPORTS))
    imp = files["app/importer.py"]
    assert owned_file_in_sync(SCHEMA, imp) is False
