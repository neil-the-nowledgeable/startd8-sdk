"""Phase 2 — convention route tests (FR-SAP-10 + OQ-6 SQLAlchemy import rule)."""

from __future__ import annotations

import pytest

from startd8.sapper.convention_route import run_convention_route
from startd8.sapper.models import AssumptionKind, AssumptionVerdict

pytestmark = pytest.mark.unit


def test_flask_and_module_source_refuted_on_skeleton():
    skeletons = {
        "app/jobs.py": (
            "from flask import Blueprint\n"
            "from app.models import JobDescription\n\n"
            "def f(): ...\n"
        )
    }
    findings = run_convention_route(skeletons)
    kinds = {(f.kind, f.found) for f in findings}
    assert all(f.verdict is AssumptionVerdict.REFUTED for f in findings)
    assert any(f.kind is AssumptionKind.FRAMEWORK_IDIOM and "flask" in f.found for f in findings)
    assert any(f.kind is AssumptionKind.MODULE_SOURCE for f in findings)


def test_oq6_sqlalchemy_import_caught_at_declaration_surface():
    # The body-stripped skeleton has no `.query(` call — only the import. OQ-6 rule must fire.
    skeletons = {"app/svc.py": "from sqlalchemy.orm import Session\n\ndef f(): ...\n"}
    findings = run_convention_route(skeletons)
    assert any(
        f.kind is AssumptionKind.ORM_IDIOM and "sqlalchemy" in f.found for f in findings
    ), "OQ-6: SQLAlchemy import must be caught at plan time on the skeleton"


def test_clean_fastapi_skeleton_no_findings():
    skeletons = {
        "app/jobs.py": (
            "from fastapi import APIRouter\n"
            "from sqlmodel import Session, select\n"
            "from app.tables import JobDescription\n\n"
            "def f(): ...\n"
        )
    }
    findings = run_convention_route(skeletons)
    assert findings == [], f"a conformant skeleton must yield no convention findings; got {findings}"


def test_non_python_skeleton_skipped():
    assert run_convention_route({"web/app.ts": "import x from 'y'"}) == []
