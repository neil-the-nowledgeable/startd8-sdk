"""Tests for Node.js P0 module system + async constraints — REQ-NODE-MP-200/201."""

import pytest

from startd8.languages.registry import LanguageRegistry


@pytest.fixture(autouse=True, scope="module")
def discover_profiles():
    LanguageRegistry.discover()


def _node_profile():
    return LanguageRegistry.get("nodejs")


class TestCodingStandardsCriticalPrefix:
    def test_critical_block_present(self):
        standards = _node_profile().coding_standards
        assert standards.startswith("CRITICAL NODE.JS CONSTRAINTS")

    def test_module_system_constraint(self):
        standards = _node_profile().coding_standards
        assert "NEVER mix" in standards
        assert "crashes at runtime" in standards

    def test_async_constraint(self):
        standards = _node_profile().coding_standards
        assert "async/await" in standards
        assert "unhandled rejections crash" in standards

    def test_general_standards_follow_critical(self):
        standards = _node_profile().coding_standards
        critical_idx = standards.index("CRITICAL")
        general_idx = standards.index("Node.js coding standards:")
        assert general_idx > critical_idx


class TestProjectContextCritical:
    def test_esm_has_critical_preamble(self):
        section = _node_profile().build_project_context_section(
            {"module_system": "esm"}
        )
        assert "CRITICAL" in section
        assert "ONLY `import`/`export`" in section
        assert "NEVER use `require()`" in section
        assert "File extensions REQUIRED" in section

    def test_cjs_has_critical_preamble(self):
        section = _node_profile().build_project_context_section(
            {"module_system": "commonjs"}
        )
        assert "CRITICAL" in section
        assert "ONLY `require()`/`module.exports`" in section
        assert "NEVER use `import`/`export`" in section

    def test_esm_rules_present(self):
        section = _node_profile().build_project_context_section(
            {"module_system": "esm"}
        )
        assert "import X from 'pkg'" in section
        assert "No `require()`" in section

    def test_cjs_rules_present(self):
        section = _node_profile().build_project_context_section(
            {"module_system": "commonjs"}
        )
        assert "const X = require('pkg')" in section
        assert "No `import`/`export`" in section
