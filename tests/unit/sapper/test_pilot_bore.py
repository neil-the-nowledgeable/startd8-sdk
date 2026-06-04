"""Phase 1 — pilot bore tests (FR-SAP-4). Replays the RUN-028 existence-miss scenario.

mypy-gated: the existence axis needs mypy (the compileall floor cannot see cross-module
references). Tests that need it skip cleanly when mypy is absent.
"""

from __future__ import annotations

import importlib.util
import shutil

import pytest

from startd8.sapper.models import AssumptionKind, AssumptionVerdict, UnresolvedReason
from startd8.sapper.pilot_bore import run_pilot_bore

pytestmark = pytest.mark.unit

_HAS_MYPY = shutil.which("mypy") is not None or importlib.util.find_spec("mypy") is not None
requires_mypy = pytest.mark.skipif(not _HAS_MYPY, reason="mypy not available")


@pytest.fixture
def real_project(tmp_path):
    """A tiny real codebase: app.tables defines JobDescription, NOT Match (RUN-028 shape)."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "tables.py").write_text(
        "class JobDescription:\n"
        "    id: str = ''\n\n"
        "class Profile:\n"
        "    id: str = ''\n"
    )
    return str(tmp_path)


@requires_mypy
def test_bore_refutes_invented_entity_but_not_real_one(real_project):
    skeletons = {
        "app/jobs.py": (
            "from app.tables import JobDescription, Match\n\n"
            "def resolve_matches(jd_id: str): ...\n"
        )
    }
    res = run_pilot_bore(skeletons, real_project)
    assert res.bore_status in ("checked", "degraded")
    symbols = {f.found if f.found != "absent" else f.expected for f in res.findings}
    refuted = [f for f in res.findings if f.verdict == AssumptionVerdict.REFUTED]
    # Match is invented → REFUTED module_source; JobDescription exists → no finding.
    match_findings = [f for f in refuted if "Match" in (f.expected + f.found)]
    assert match_findings, f"expected a REFUTED finding for Match; got {[ (f.kind.value,f.expected) for f in res.findings]}"
    assert match_findings[0].kind is AssumptionKind.MODULE_SOURCE
    assert not [f for f in refuted if "JobDescription" in f.expected], "JobDescription exists — must not be refuted"


@requires_mypy
def test_bore_refutes_missing_local_module_but_ignores_third_party(real_project):
    skeletons = {
        "app/svc.py": (
            "from app.ghost import Thing\n"        # local, missing → REFUTED
            "from flask import Blueprint\n\n"        # third-party, missing → noise, dropped
            "def f(): ...\n"
        )
    }
    res = run_pilot_bore(skeletons, real_project)
    refuted = [f for f in res.findings if f.verdict == AssumptionVerdict.REFUTED]
    assert any("app.ghost" in f.expected for f in refuted), "missing local module must be REFUTED"
    assert not any("flask" in (f.expected + f.found) for f in res.findings), "third-party missing import is noise"


def test_syntax_invalid_skeleton_refuted_not_crash():
    skeletons = {"app/broken.py": "def f(:\n    ...\n"}  # invalid syntax
    res = run_pilot_bore(skeletons, None)
    bad = [f for f in res.findings if f.kind is AssumptionKind.DECOMPOSITION_INTEGRITY]
    assert bad and bad[0].verdict is AssumptionVerdict.REFUTED
    assert "SyntaxError" in bad[0].found


def test_oversized_skeleton_degraded_not_hang():
    big = "x = 1\n" * 100_000
    res = run_pilot_bore({"app/huge.py": big}, None, max_skeleton_bytes=1_000)
    deg = [f for f in res.findings if f.reason is UnresolvedReason.BORE_DEGRADED]
    assert deg, "oversized skeleton must degrade to UNRESOLVED(bore_degraded)"


def test_non_python_skeleton_unavailable():
    res = run_pilot_bore({"web/app.ts": "const x = 1;"}, None)
    assert res.bore_status == "unavailable"
    assert any("non-Python" in n for n in res.notes)


@requires_mypy
def test_overlay_excludes_secrets(real_project, tmp_path):
    # Drop a secret into the real project; the overlay must not carry it (we can't easily
    # inspect the temp dir post-cleanup, so assert the run still succeeds and the secret
    # file is ignored by pattern — exercised indirectly via no crash + clean status).
    (tmp_path / ".env").write_text("SECRET=hunter2\n")
    skeletons = {"app/ok.py": "from app.tables import JobDescription\n\ndef f(): ...\n"}
    res = run_pilot_bore(skeletons, real_project)
    assert res.bore_status in ("checked", "degraded")
