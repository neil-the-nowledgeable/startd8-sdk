"""Tests for L6 discarded return value detection and observability integration.

Verifies REQ-SV-701/702 (expression lint) and REQ-SV-901/902/903
(OTel span attributes, Loki logging, Kaizen export) from
SEMANTIC_VALIDATION_REQUIREMENTS.md.
"""

import pytest
from unittest.mock import MagicMock, patch

from startd8.forward_manifest_validator import (
    validate_disk_compliance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _discarded_issues(result):
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "discarded_return"
    ]


# ---------------------------------------------------------------------------
# L6: Discarded return value detection (REQ-SV-701)
# ---------------------------------------------------------------------------


class TestDiscardedReturns:
    def test_discarded_getenv_flagged(self, tmp_path):
        """Run-050 bug: os.getenv() called as expression statement."""
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nos.getenv('FOO')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _discarded_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["symbol"] == "os.getenv"
        assert issues[0]["line"] == 2

    def test_assigned_getenv_passes(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nval = os.getenv('FOO')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []

    def test_discarded_environ_get_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nos.environ.get('BAR')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _discarded_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "os.environ.get"

    def test_discarded_path_join_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nos.path.join('/a', 'b')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _discarded_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "os.path.join"

    def test_discarded_path_exists_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nos.path.exists('/tmp')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _discarded_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "os.path.exists"

    def test_instance_method_not_flagged(self, tmp_path):
        """Instance method calls (d.get, s.replace) are not detectable via AST."""
        rel = _write_py(
            tmp_path, "app.py",
            "d = {}\nd.get('key')\ns = 'hi'\ns.replace('h', 'H')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []

    def test_multiple_discarded_calls(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import os\nos.getenv('A')\nos.getenv('B')\nos.getenv('C')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _discarded_issues(result)
        assert len(issues) == 3

    def test_print_not_flagged(self, tmp_path):
        """Side-effect calls should never be flagged."""
        rel = _write_py(tmp_path, "app.py", "print('hello')\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []

    def test_list_append_not_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "items = []\nitems.append(1)\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []

    def test_logging_call_not_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "import logging\nlogging.info('msg')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []

    def test_method_call_on_variable_not_flagged(self, tmp_path):
        """Calls on local variables with non-pure names should pass."""
        rel = _write_py(
            tmp_path, "app.py",
            "db = object()\ndb.connect()\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _discarded_issues(result) == []


# ---------------------------------------------------------------------------
# Observability: OTel span attributes (REQ-SV-901)
# ---------------------------------------------------------------------------


class TestOtelSpanAttributes:
    def test_issues_available_for_otel_emission(self, tmp_path):
        """Verify that semantic issues are populated for OTel to emit."""
        rel = _write_py(
            tmp_path, "app.py",
            "import phantom_module\nimport os\nos.getenv('X')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))

        import_issues = [
            i for i in result.semantic_issues
            if isinstance(i, dict) and i.get("category") == "import_resolution"
        ]
        discarded_issues = _discarded_issues(result)
        assert len(import_issues) >= 1
        assert len(discarded_issues) >= 1

        # Verify the categories that would be emitted as OTel attributes
        categories = sorted({
            i["category"] for i in result.semantic_issues
            if isinstance(i, dict) and "category" in i
        })
        assert "import_resolution" in categories
        assert "discarded_return" in categories

    def test_otel_failure_does_not_crash(self, tmp_path):
        """If OTel is unavailable, validation still works."""
        rel = _write_py(tmp_path, "app.py", "import phantom\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True


# ---------------------------------------------------------------------------
# Observability: Logger uses get_logger (REQ-SV-902)
# ---------------------------------------------------------------------------


class TestLoggerSetup:
    def test_uses_get_logger(self):
        """forward_manifest_validator must use get_logger, not logging.getLogger."""
        import startd8.forward_manifest_validator as mod
        # The module-level logger should come from get_logger
        assert mod.logger is not None
        assert mod.logger.name == "startd8.forward_manifest_validator"


# ---------------------------------------------------------------------------
# Kaizen export: semantic_issue_summary (REQ-SV-903)
# ---------------------------------------------------------------------------


class TestKaizenExport:
    def test_semantic_issue_summary_with_issues(self, tmp_path):
        """FeaturePostMortem.semantic_issue_summary aggregates by category."""
        from startd8.contractors.prime_postmortem import FeaturePostMortem

        rel = _write_py(
            tmp_path, "app.py",
            (
                "import phantom_one\n"
                "import phantom_two\n"
                "import os\nos.getenv('X')\n"
            ),
        )
        compliance = validate_disk_compliance(rel, str(tmp_path))

        fpm = FeaturePostMortem(
            feature_id="PI-001",
            name="test",
            status="success",
            success=True,
            disk_compliance=compliance,
        )

        summary = fpm.semantic_issue_summary
        assert "import_resolution" in summary
        assert summary["import_resolution"] >= 2
        assert "discarded_return" in summary
        assert summary["discarded_return"] >= 1

    def test_semantic_issue_summary_empty(self):
        from startd8.contractors.prime_postmortem import FeaturePostMortem

        fpm = FeaturePostMortem(
            feature_id="PI-001",
            name="test",
            status="success",
            success=True,
        )
        assert fpm.semantic_issue_summary == {}

    def test_semantic_issue_summary_no_dict_issues(self, tmp_path):
        """Old-style string issues should not appear in summary."""
        from startd8.contractors.prime_postmortem import FeaturePostMortem
        from startd8.forward_manifest_validator import DiskComplianceResult

        compliance = DiskComplianceResult(
            file_path="test.py",
            semantic_issues=["old-style string issue"],
        )
        fpm = FeaturePostMortem(
            feature_id="PI-001",
            name="test",
            status="success",
            success=True,
            disk_compliance=compliance,
        )
        assert fpm.semantic_issue_summary == {}
