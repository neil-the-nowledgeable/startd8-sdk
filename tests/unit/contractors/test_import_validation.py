"""AR-823: Import validation against module inventory.

Verifies IntegrationEngine._validate_imports() correctly identifies
unresolved first-party imports while allowing stdlib and third-party.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def module_inventory():
    """Standard module inventory for testing."""
    return [
        "startd8",
        "startd8.agents",
        "startd8.agents.base",
        "startd8.providers",
        "startd8.costs",
        "startd8.contractors",
    ]


@pytest.fixture
def py_file_with_valid_imports(tmp_path):
    """Python file with valid imports."""
    f = tmp_path / "valid.py"
    f.write_text(
        "import os\n"
        "import json\n"
        "from startd8.agents import base\n"
        "from startd8.providers import registry\n"
        "import requests\n"
    )
    return f


@pytest.fixture
def py_file_with_hallucinated_import(tmp_path):
    """Python file importing a nonexistent first-party sub-package.

    The hallucinated import is ``startd8.nonexistent_pkg.thing`` where
    ``startd8.nonexistent_pkg`` is not in the module inventory.
    """
    f = tmp_path / "hallucinated.py"
    f.write_text(
        "import os\n"
        "from startd8.nonexistent_pkg.thing import something\n"
        "from startd8.agents import base\n"
    )
    return f


@pytest.fixture
def py_file_stdlib_only(tmp_path):
    """Python file with only stdlib imports."""
    f = tmp_path / "stdlib_only.py"
    f.write_text(
        "import os\n"
        "import sys\n"
        "import json\n"
        "from pathlib import Path\n"
    )
    return f


@pytest.fixture
def yaml_file(tmp_path):
    """Non-Python file."""
    f = tmp_path / "config.yaml"
    f.write_text("key: value\n")
    return f


@pytest.mark.unit
class TestValidateImports:
    """Test IntegrationEngine._validate_imports()."""

    def test_allows_stdlib_imports(self, py_file_stdlib_only, module_inventory):
        """stdlib imports (os, sys, json) should not be flagged."""
        from startd8.contractors.integration_engine import IntegrationEngine

        result = IntegrationEngine._validate_imports(
            py_file_stdlib_only, module_inventory,
        )
        assert result == []

    def test_allows_known_project_imports(
        self, py_file_with_valid_imports, module_inventory,
    ):
        """Imports from module_inventory should be allowed."""
        from startd8.contractors.integration_engine import IntegrationEngine

        result = IntegrationEngine._validate_imports(
            py_file_with_valid_imports, module_inventory,
        )
        assert result == []

    def test_rejects_hallucinated_import(
        self, py_file_with_hallucinated_import, module_inventory,
    ):
        """Imports from nonexistent first-party modules should be flagged."""
        from startd8.contractors.integration_engine import IntegrationEngine

        result = IntegrationEngine._validate_imports(
            py_file_with_hallucinated_import, module_inventory,
        )
        # startd8.nonexistent_pkg.thing should be flagged
        assert len(result) >= 1
        assert any("nonexistent_pkg" in r for r in result)

    def test_skips_non_python_files(self, yaml_file, module_inventory):
        """Non-.py files should return empty list."""
        from startd8.contractors.integration_engine import IntegrationEngine

        result = IntegrationEngine._validate_imports(yaml_file, module_inventory)
        assert result == []

    def test_empty_inventory_skips_validation(self, py_file_with_hallucinated_import):
        """Empty module inventory means skip all validation."""
        from startd8.contractors.integration_engine import IntegrationEngine

        result = IntegrationEngine._validate_imports(
            py_file_with_hallucinated_import, [],
        )
        assert result == []

    def test_syntax_error_file_returns_empty(self, tmp_path, module_inventory):
        """Files with syntax errors should return empty (caught elsewhere)."""
        from startd8.contractors.integration_engine import IntegrationEngine

        bad_file = tmp_path / "bad_syntax.py"
        bad_file.write_text("def foo(\n")  # Syntax error

        result = IntegrationEngine._validate_imports(bad_file, module_inventory)
        assert result == []

    def test_third_party_imports_not_flagged(self, tmp_path, module_inventory):
        """Third-party packages not in inventory should NOT be flagged."""
        from startd8.contractors.integration_engine import IntegrationEngine

        f = tmp_path / "third_party.py"
        f.write_text(
            "import requests\n"
            "import pydantic\n"
            "from httpx import AsyncClient\n"
        )

        result = IntegrationEngine._validate_imports(f, module_inventory)
        assert result == []
