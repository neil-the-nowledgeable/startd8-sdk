"""RUN-036 under-generation guard (#3).

A manifest-fillable module that generates only `router = None` (a $0 stub) must NOT
score disk-quality 1.0 — that false-pass makes a feature look fixed when it was avoided
by generating nothing. The guard mirrors the existing non-Python empty-stem detector and
is gated on the manifest prescribing fillable elements (so legitimate re-export modules
and manifest-free validation are unaffected).
"""

import ast

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.forward_manifest_validator import (
    _is_functionally_empty_python_module,
    compute_disk_quality_score,
    validate_disk_compliance,
)
from startd8.utils.code_manifest import ElementKind

STUB = (
    "from __future__ import annotations\n"
    "job_export_router = None\n"
    '__all__ = ["job_export_router"]\n'
)
REAL = (
    "from fastapi import APIRouter\n"
    "job_export_router = APIRouter()\n"
    "\n"
    "@job_export_router.get('/export')\n"
    "def export():\n"
    "    return {'ok': True}\n"
)


def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return rel


def _fillable_manifest(rel):
    # A CONSTANT element is fillable (is_fillable_spec) and needs no signature — it also
    # mirrors the RUN-036 case where the manifest prescribed a module-level `*_router`.
    spec = ForwardFileSpec(
        file=rel,
        elements=[ForwardElementSpec(kind=ElementKind.CONSTANT, name="job_export_router")],
    )
    return ForwardManifest(file_specs={rel: spec})


class TestUnderGenerationGuard:
    def test_stub_with_fillable_manifest_is_flagged(self, tmp_path):
        rel = _write(tmp_path, "app/job_export.py", STUB)
        res = validate_disk_compliance(rel, str(tmp_path), manifest=_fillable_manifest(rel))
        assert res.ast_valid is False
        assert res.error == "under_generation: functionally_empty_module"
        assert any(i.get("category") == "under_generated_module" for i in res.semantic_issues)
        # The whole point: a $0 stub must NOT score 1.0.
        assert compute_disk_quality_score(res) == 0.0

    def test_real_module_not_flagged(self, tmp_path):
        rel = _write(tmp_path, "app/job_export.py", REAL)
        res = validate_disk_compliance(rel, str(tmp_path), manifest=_fillable_manifest(rel))
        assert res.ast_valid is True
        assert res.error is None

    def test_stub_without_manifest_not_flagged(self, tmp_path):
        # The guard requires the manifest to prescribe fillable elements; no manifest → no guard
        # (unchanged behaviour — the guard never lowers a score it has no contract basis to lower).
        rel = _write(tmp_path, "app/job_export.py", STUB)
        res = validate_disk_compliance(rel, str(tmp_path))
        assert res.ast_valid is True

    def test_reexport_module_not_flagged(self, tmp_path):
        # A legitimate re-export module is functionally empty but has NO fillable manifest spec.
        rel = _write(
            tmp_path, "app/__init__.py",
            "from .job_export import job_export_router\n__all__ = ['job_export_router']\n",
        )
        res = validate_disk_compliance(rel, str(tmp_path), manifest=ForwardManifest(file_specs={}))
        assert res.ast_valid is True


class TestFunctionallyEmptyHelper:
    def test_none_assign_is_empty(self):
        assert _is_functionally_empty_python_module(ast.parse(STUB)) is True

    def test_function_is_not_empty(self):
        assert _is_functionally_empty_python_module(ast.parse(REAL)) is False

    def test_nonnull_assign_is_not_empty(self):
        assert _is_functionally_empty_python_module(ast.parse("X = 5\n")) is False

    def test_annassign_none_is_empty(self):
        assert _is_functionally_empty_python_module(
            ast.parse("from fastapi import APIRouter\nrouter: APIRouter = None\n")
        ) is True

    def test_toplevel_logic_is_not_empty(self):
        assert _is_functionally_empty_python_module(
            ast.parse("import sys\nif __name__ == '__main__':\n    sys.exit(0)\n")
        ) is False
