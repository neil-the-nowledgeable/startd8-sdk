"""Detector fidelity — DET-MR-1 / DET-IR-1 (DETECTOR_FIDELITY_ANALYSIS_AND_REQUIREMENTS.md).

Guards the two semantic-detector fixes that let `run_semantic_repair` see the canonical
REQ-SR-100 (method_resolution) and REQ-SR-200 (import_resolution) bugs — plus the negative
cases that must NOT be flagged (dispatch is fine for non-calls; namespace-package siblings;
real package layouts).
"""
from __future__ import annotations

from pathlib import Path

from startd8.forward_manifest_validator import validate_disk_compliance


def _write(root: Path, rel: str, body: str) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return rel


def _cats(root: Path, rel: str, category: str) -> list:
    res = validate_disk_compliance(rel, str(root))
    return [i for i in (res.semantic_issues or []) if i.get("category") == category]


# ── DET-MR-1: method_resolution is dispatch-independent ──────────────────────

def test_mr_self_call_flagged_even_when_in_tasks_dict(tmp_path):
    """REQ-SR-100: self.index() is a bug even though index is in `tasks = {index: 1}`."""
    rel = _write(tmp_path, "svc/locustfile.py",
                 "from locust import TaskSet\n\n"
                 "def index(l):\n    l.client.get('/')\n\n"
                 "class UserBehavior(TaskSet):\n"
                 "    def on_start(self):\n        self.index()\n"
                 "    tasks = {index: 1}\n")
    issues = _cats(tmp_path, rel, "method_resolution")
    assert any(i.get("symbol") == "index" for i in issues), \
        "self.index() must be flagged despite tasks-dict membership (DET-MR-1)"


def test_mr_real_method_not_flagged(tmp_path):
    """Negative: self.<m>() where <m> is an actual class method is fine."""
    rel = _write(tmp_path, "svc/app.py",
                 "class C:\n    def helper(self):\n        return 1\n"
                 "    def run(self):\n        return self.helper()\n")
    assert _cats(tmp_path, rel, "method_resolution") == []


# ── DET-IR-1: self-referential parent import in flat layout ──────────────────

def test_ir_flat_layout_parent_import_flagged(tmp_path):
    """REQ-SR-200: `from emailservice.email_server import X` from inside flat emailservice/."""
    _write(tmp_path, "emailservice/email_server.py", "class EmailServiceStub:\n    pass\n")
    rel = _write(tmp_path, "emailservice/email_client.py",
                 "from emailservice.email_server import EmailServiceStub\n")
    issues = _cats(tmp_path, rel, "import_resolution")
    assert issues, "flat-layout self-referential parent import must be flagged (DET-IR-1)"


def test_ir_package_layout_parent_import_not_flagged(tmp_path):
    """Negative: same import resolves when emailservice/ is a real package (__init__.py)."""
    _write(tmp_path, "emailservice/__init__.py", "")
    _write(tmp_path, "emailservice/email_server.py", "class EmailServiceStub:\n    pass\n")
    rel = _write(tmp_path, "emailservice/email_client.py",
                 "from emailservice.email_server import EmailServiceStub\n")
    assert _cats(tmp_path, rel, "import_resolution") == []


def test_ir_namespace_sibling_import_not_flagged(tmp_path):
    """Negative: `import utils` of a sibling sub-dir is a valid Py3 namespace package."""
    (tmp_path / "svc" / "utils").mkdir(parents=True)
    rel = _write(tmp_path, "svc/server.py", "import utils\n")
    assert _cats(tmp_path, rel, "import_resolution") == []
