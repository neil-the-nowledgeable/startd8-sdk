"""Phase 4 (static) — FR-IMP-6 surface render determinism, conditional emission, drift.

Behavioral validation (served GET/POST) lives in test_import_runtime.py.
"""

from __future__ import annotations

import os
import py_compile
import tempfile

from startd8.backend_codegen.assembler import render_backend
from startd8.backend_codegen.drift import check_drift, owned_file_in_sync
from startd8.backend_codegen.import_surface import (
    render_import_surface,
    surface_enabled,
)

SCHEMA = "model Capability {\n  id String @id @default(cuid())\n  name String?\n}\n"
WITH_SURFACE = "imports:\n  Capability:\n    format: json\n    surface: yes\n"
NO_SURFACE = "imports:\n  Capability:\n    format: json\n"


def test_surface_enabled_gate():
    assert surface_enabled(WITH_SURFACE) is True
    assert surface_enabled(NO_SURFACE) is False
    assert surface_enabled(None) is False


def test_render_deterministic_and_compiles():
    a = render_import_surface(SCHEMA, WITH_SURFACE)
    b = render_import_surface(SCHEMA, WITH_SURFACE)
    assert a == b
    assert "# startd8-artifact: python-import-surface" in a
    fd, p = tempfile.mkstemp(suffix=".py")
    os.write(fd, a.encode())
    os.close(fd)
    try:
        py_compile.compile(p, doraise=True)
    finally:
        os.unlink(p)


def test_conditional_emission_requires_surface_flag():
    with_surface = dict(render_backend(SCHEMA, imports_text=WITH_SURFACE))
    no_surface = dict(render_backend(SCHEMA, imports_text=NO_SURFACE))
    assert "app/import_surface.py" in with_surface
    assert "app/importer.py" in with_surface          # importer always when imports present
    assert "app/import_surface.py" not in no_surface   # surface is opt-in on the flag
    assert "app/importer.py" in no_surface


def test_main_mounts_surface_tolerantly():
    files = dict(render_backend(SCHEMA, imports_text=WITH_SURFACE))
    assert "from .import_surface import import_surface_router" in files["app/main.py"]


def test_surface_drift_in_sync_and_stale():
    files = dict(render_backend(SCHEMA, imports_text=WITH_SURFACE))
    surf = files["app/import_surface.py"]
    assert check_drift(SCHEMA, surf, imports_text=WITH_SURFACE).status == "in_sync"
    assert owned_file_in_sync(SCHEMA, surf, imports_text=WITH_SURFACE) is True
    # changing the manifest restamps it
    changed = WITH_SURFACE.replace("surface: yes", "surface: yes\n    identity: name")
    assert check_drift(SCHEMA, surf, imports_text=changed).status == "stale"
