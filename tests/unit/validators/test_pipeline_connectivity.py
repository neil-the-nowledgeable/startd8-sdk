"""Pipeline connectivity tests — verify semantic checks flow end-to-end.

Each test creates a sample file with a known defect and verifies the defect
appears in DiskComplianceResult.semantic_issues after validate_disk_compliance().

These tests verify the wiring between detection and collection (REQ-KZ-001/002).
"""

import pytest

from startd8.forward_manifest_validator import validate_disk_compliance


class TestPythonPipelineConnectivity:
    """Python L11 semantic checks are wired into validate_disk_compliance."""

    def test_duplicate_main_guard_detected(self, tmp_path):
        """L11: duplicate main guards produce semantic_issues entry."""
        py_file = tmp_path / "test.py"
        py_file.write_text(
            'x = 1\n'
            'if __name__ == "__main__":\n'
            '    pass\n'
            'if __name__ == "__main__":\n'
            '    pass\n'
        )
        result = validate_disk_compliance(str(py_file), str(tmp_path))
        categories = [
            i["category"] for i in result.semantic_issues
            if isinstance(i, dict)
        ]
        assert "duplicate_main_guard" in categories

    def test_bare_except_pass_detected(self, tmp_path):
        """L11: bare except:pass produces semantic_issues entry."""
        py_file = tmp_path / "test.py"
        py_file.write_text(
            "def foo():\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"
            "        pass\n"
        )
        result = validate_disk_compliance(str(py_file), str(tmp_path))
        categories = [
            i["category"] for i in result.semantic_issues
            if isinstance(i, dict)
        ]
        assert "bare_except_pass" in categories

    def test_clean_python_file_no_l11_issues(self, tmp_path):
        """Clean Python file should not trigger L11 checks."""
        py_file = tmp_path / "clean.py"
        py_file.write_text(
            "def hello():\n"
            "    return 'world'\n"
        )
        result = validate_disk_compliance(str(py_file), str(tmp_path))
        l11_categories = {
            i["category"] for i in result.semantic_issues
            if isinstance(i, dict) and i["category"] in (
                "duplicate_main_guard", "bare_except_pass",
            )
        }
        assert not l11_categories


class TestTypescriptPipelineConnectivity:
    """TypeScript files route through JS semantic validation (REQ-KZ-002)."""

    def test_typescript_var_usage_detected(self, tmp_path):
        """.ts files get var_usage semantic check."""
        ts_file = tmp_path / "test.ts"
        ts_file.write_text("var x = 1;\nexport default x;\n")
        result = validate_disk_compliance(str(ts_file), str(tmp_path))
        categories = [
            i.get("category") for i in result.semantic_issues
            if isinstance(i, dict)
        ]
        assert "var_usage" in categories

    def test_tsx_file_routes_to_js_validator(self, tmp_path):
        """.tsx files are validated (not silently skipped)."""
        tsx_file = tmp_path / "App.tsx"
        tsx_file.write_text("var x = 1;\nexport default x;\n")
        result = validate_disk_compliance(str(tsx_file), str(tmp_path))
        categories = [
            i.get("category") for i in result.semantic_issues
            if isinstance(i, dict)
        ]
        assert "var_usage" in categories


class TestPackageJsonPipelineConnectivity:
    """Package.json semantic checks collected in DiskComplianceResult (REQ-KZ-002)."""

    def test_package_json_missing_type_field(self, tmp_path):
        """package.json without 'type' field triggers missing_module_type."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test", "version": "1.0.0", "dependencies": {"express": "4.0.0"}}')
        result = validate_disk_compliance(str(pkg), str(tmp_path))
        categories = [
            i.get("category") for i in result.semantic_issues
            if isinstance(i, dict)
        ]
        # missing_module_type should fire because no "type" field
        assert "missing_module_type" in categories

    def test_package_json_structural_failure_skips_semantic(self, tmp_path):
        """Structurally invalid package.json should return early without semantic checks."""
        pkg = tmp_path / "package.json"
        pkg.write_text("not valid json")
        result = validate_disk_compliance(str(pkg), str(tmp_path))
        assert result.ast_valid is False
        # Should have no semantic issues (returned early on parse failure)
        assert len(result.semantic_issues) == 0
