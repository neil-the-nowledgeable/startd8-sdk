"""Tests for REQ-SV2-1300 (import conventions) and REQ-SV2-1400 (anti-patterns)."""

import pytest

from startd8.implementation_engine.spec_builder import (
    _build_import_conventions_section,
    _build_anti_pattern_section,
)


# ── REQ-SV2-1300: Import Conventions ─────────────────────────────────


class TestBuildImportConventionsSection:
    """Flat-layout detection and import convention injection."""

    def _flat_context(self, **overrides):
        """Context with sibling .py files but no __init__.py."""
        ctx = {
            "target_files": ["emailservice/email_server.py"],
            "existing_files": {
                "emailservice/logger.py": "import logging",
                "emailservice/demo_pb2.py": "# generated proto stub",
            },
        }
        ctx.update(overrides)
        return ctx

    def test_flat_layout_detected(self):
        result = _build_import_conventions_section(self._flat_context())
        assert "flat module layout" in result
        assert "import demo_pb2" in result
        assert "import logger" in result

    def test_bad_example_included(self):
        result = _build_import_conventions_section(self._flat_context())
        assert "from emailservice import" in result
        assert "WRONG" in result

    def test_package_layout_returns_empty(self):
        """When __init__.py exists, no convention guidance is needed."""
        ctx = self._flat_context(existing_files={
            "emailservice/__init__.py": "",
            "emailservice/logger.py": "import logging",
        })
        result = _build_import_conventions_section(ctx)
        assert result == ""

    def test_no_existing_files_returns_empty(self):
        ctx = {"target_files": ["emailservice/email_server.py"]}
        result = _build_import_conventions_section(ctx)
        assert result == ""

    def test_no_target_files_returns_empty(self):
        ctx = {"existing_files": {"emailservice/logger.py": "pass"}}
        result = _build_import_conventions_section(ctx)
        assert result == ""

    def test_no_sibling_py_files_returns_empty(self):
        """Sibling files in a different directory don't count."""
        ctx = {
            "target_files": ["emailservice/email_server.py"],
            "existing_files": {
                "otherservice/logger.py": "pass",
            },
        }
        result = _build_import_conventions_section(ctx)
        assert result == ""

    def test_existing_files_content_key(self):
        """Also reads from existing_files_content (alternate key)."""
        ctx = {
            "target_files": ["svc/server.py"],
            "existing_files_content": {
                "svc/helper.py": "pass",
                "svc/models.py": "pass",
            },
        }
        result = _build_import_conventions_section(ctx)
        assert "import helper" in result
        assert "import models" in result

    def test_limits_examples_to_four(self):
        """Only first 4 sibling modules shown as examples."""
        ctx = {
            "target_files": ["svc/server.py"],
            "existing_files": {
                f"svc/mod{i}.py": "pass" for i in range(6)
            },
        }
        result = _build_import_conventions_section(ctx)
        # Sorted: mod0, mod1, mod2, mod3 shown; mod4, mod5 not
        assert "import mod0" in result
        assert "import mod3" in result
        assert "import mod4" not in result


# ── REQ-SV2-1400: Anti-Pattern Section ───────────────────────────────


class TestBuildAntiPatternSection:
    """Env-var anti-pattern detection and guidance injection."""

    def test_triggered_by_task_description(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Configure environment variables for GCP")
        assert "os.getenv" in result
        assert "WRONG" in result
        assert "Anti-Patterns" in result

    def test_triggered_by_env_keyword(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Set up .env file for the service")
        assert "Anti-Patterns" in result

    def test_triggered_by_config_keyword(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Add configuration loading for database")
        assert "Anti-Patterns" in result

    def test_triggered_by_existing_file_content(self):
        ctx = {
            "existing_files": {
                "svc/config.py": 'port = os.getenv("PORT", "8080")',
            },
        }
        result = _build_anti_pattern_section(ctx, "Implement the health check endpoint")
        assert "Anti-Patterns" in result

    def test_triggered_by_existing_files_content_key(self):
        ctx = {
            "existing_files_content": {
                "svc/main.py": 'val = os.environ.get("KEY")',
            },
        }
        result = _build_anti_pattern_section(ctx, "Add logging to main")
        assert "Anti-Patterns" in result

    def test_not_triggered_for_unrelated_task(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Implement the sorting algorithm")
        assert result == ""

    def test_not_triggered_empty_context(self):
        result = _build_anti_pattern_section({}, "Add unit tests for the parser")
        assert result == ""

    def test_os_path_guidance_included(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Configure environment variables")
        assert "os.path" in result

    def test_correct_example_included(self):
        ctx = {}
        result = _build_anti_pattern_section(ctx, "Load environment variables")
        assert 'project_id = os.getenv("GCP_PROJECT_ID", "")' in result
