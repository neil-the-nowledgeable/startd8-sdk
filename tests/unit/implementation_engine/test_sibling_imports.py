"""Tests for L5+: sibling-file import derivation in spec builder."""

from startd8.implementation_engine.spec_builder import _build_sibling_imports_section


class TestSiblingImportsExtracted:
    def test_sibling_imports_included(self):
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {
                "src/svc/logger.py": "import logging\nfrom opentelemetry import trace\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert "import logging" in result
        assert "Sibling Files" in result

    def test_multiple_siblings(self):
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {
                "src/svc/logger.py": "import logging\n",
                "src/svc/config.py": "import os\nimport json\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert "import logging" in result
        assert "import os" in result
        assert "import json" in result


class TestSiblingImportsDifferentDirExcluded:
    def test_different_dir_ignored(self):
        context = {
            "target_files": ["src/svc_a/server.py"],
            "existing_files_content": {
                "src/svc_b/logger.py": "import logging\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert result == ""


class TestSiblingImportsSyntaxError:
    def test_syntax_error_skipped(self):
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {
                "src/svc/broken.py": "def foo(\n",
                "src/svc/good.py": "import os\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert "import os" in result


class TestSiblingImportsEmpty:
    def test_no_existing_files(self):
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {},
        }
        result = _build_sibling_imports_section(context)
        assert result == ""

    def test_no_existing_files_key(self):
        context = {"target_files": ["src/svc/server.py"]}
        result = _build_sibling_imports_section(context)
        assert result == ""

    def test_no_target_files(self):
        context = {
            "existing_files_content": {"src/svc/logger.py": "import os\n"},
        }
        result = _build_sibling_imports_section(context)
        assert result == ""


class TestNonPythonExcluded:
    def test_dockerfile_not_parsed(self):
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {
                "src/svc/Dockerfile": "FROM python:3.11\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert result == ""


class TestFallbackToFrameworkDefaults:
    def test_no_siblings_allows_framework_fallback(self):
        """When sibling imports return empty, framework defaults should be used."""
        # This tests the integration logic in build_spec_prompt, but we can
        # verify the section returns empty so the caller falls through.
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {},
        }
        result = _build_sibling_imports_section(context)
        assert result == ""

    def test_deduplication(self):
        """Same import from multiple siblings should appear once."""
        context = {
            "target_files": ["src/svc/server.py"],
            "existing_files_content": {
                "src/svc/a.py": "import os\n",
                "src/svc/b.py": "import os\n",
            },
        }
        result = _build_sibling_imports_section(context)
        assert result.count("import os") == 1
