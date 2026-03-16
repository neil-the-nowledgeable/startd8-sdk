"""Tests for L1 import resolution semantic validation in validate_disk_compliance().

Verifies REQ-SV-201 through REQ-SV-204 from SEMANTIC_VALIDATION_REQUIREMENTS.md.
"""

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    validate_disk_compliance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path, rel_path, content):
    """Write a Python file under tmp_path and return the relative path string."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _write_file(tmp_path, rel_path, content):
    """Write any file under tmp_path and return the relative path string."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _import_issues(result):
    """Extract import_resolution issues from a DiskComplianceResult."""
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "import_resolution"
    ]


# ---------------------------------------------------------------------------
# Stdlib imports — should never be flagged
# ---------------------------------------------------------------------------


class TestStdlibImports:
    def test_stdlib_import_passes(self, tmp_path):
        rel = _write_py(tmp_path, "app.py", "import os\nimport sys\nimport json\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_stdlib_from_import_passes(self, tmp_path):
        rel = _write_py(tmp_path, "app.py", "from pathlib import Path\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []


# ---------------------------------------------------------------------------
# Protobuf stubs — always pass (no requirements.in needed)
# ---------------------------------------------------------------------------


class TestProtobufImports:
    def test_pb2_import_passes(self, tmp_path):
        rel = _write_py(tmp_path, "svc/server.py", "import demo_pb2\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_pb2_grpc_import_passes(self, tmp_path):
        rel = _write_py(tmp_path, "svc/server.py", "import demo_pb2_grpc\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_from_pb2_import_passes(self, tmp_path):
        rel = _write_py(
            tmp_path, "svc/server.py",
            "from demo_pb2_grpc import EmailServiceServicer\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []


# ---------------------------------------------------------------------------
# Local sibling imports — pass when sibling files exist
# ---------------------------------------------------------------------------


class TestLocalSiblingImports:
    def test_sibling_via_disk_scan(self, tmp_path):
        """When no sibling_files kwarg, validator scans the directory."""
        _write_py(tmp_path, "svc/logger.py", "# logger module\n")
        rel = _write_py(tmp_path, "svc/server.py", "import logger\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_sibling_via_explicit_list(self, tmp_path):
        rel = _write_py(tmp_path, "svc/server.py", "import logger\n")
        result = validate_disk_compliance(
            rel, str(tmp_path),
            sibling_files=["svc/logger.py"],
        )
        assert _import_issues(result) == []

    def test_directory_package_sibling(self, tmp_path):
        """A subdirectory in the same parent counts as a local package."""
        (tmp_path / "svc" / "utils").mkdir(parents=True)
        rel = _write_py(tmp_path, "svc/server.py", "import utils\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []


# ---------------------------------------------------------------------------
# PyPI imports — pass when in requirements.in or alias-mapped
# ---------------------------------------------------------------------------


class TestPipImports:
    def test_pip_with_requirements_in(self, tmp_path):
        _write_file(tmp_path, "svc/requirements.in", "flask\nrequests\n")
        rel = _write_py(tmp_path, "svc/app.py", "import flask\nimport requests\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_alias_mapped_without_requirements(self, tmp_path):
        """grpc → grpcio alias should resolve even without requirements.in."""
        rel = _write_py(tmp_path, "svc/server.py", "import grpc\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []

    def test_pip_via_requirements_alias(self, tmp_path):
        """pyyaml in requirements.in should match 'import yaml'."""
        _write_file(tmp_path, "svc/requirements.in", "pyyaml\n")
        rel = _write_py(tmp_path, "svc/app.py", "import yaml\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []


# ---------------------------------------------------------------------------
# Phantom imports — MUST be flagged
# ---------------------------------------------------------------------------


class TestPhantomImports:
    def test_phantom_import_flagged(self, tmp_path):
        """Run-050 bug: from alloydbengine import AlloyDBEngine."""
        rel = _write_py(
            tmp_path, "svc/app.py",
            "from alloydbengine import AlloyDBEngine\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _import_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "alloydbengine" in issues[0]["symbol"]

    def test_multiple_phantom_imports(self, tmp_path):
        rel = _write_py(
            tmp_path, "svc/app.py",
            "import alloydbengine\nimport nonexistent_pkg\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _import_issues(result)
        assert len(issues) == 2

    def test_phantom_import_has_line_number(self, tmp_path):
        rel = _write_py(
            tmp_path, "svc/app.py",
            "import os\nimport phantom_module\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _import_issues(result)
        assert len(issues) == 1
        assert issues[0]["line"] == 2


# ---------------------------------------------------------------------------
# Golden seed import map — closed-world mode
# ---------------------------------------------------------------------------


class TestImportMapMode:
    def test_import_map_all_present(self, tmp_path):
        rel = _write_py(
            tmp_path, "svc/server.py",
            "import os\nimport grpc\nimport demo_pb2\n",
        )
        import_map = {
            "os": "stdlib",
            "grpc": "pip:grpcio",
            "demo_pb2": "proto:demo.proto",
        }
        result = validate_disk_compliance(
            rel, str(tmp_path), import_map=import_map,
        )
        assert _import_issues(result) == []

    def test_import_map_rejects_unlisted(self, tmp_path):
        """Closed-world: import not in map → error, even if stdlib."""
        rel = _write_py(
            tmp_path, "svc/server.py",
            "import os\nimport grpc\nimport alloydbengine\n",
        )
        import_map = {"os": "stdlib", "grpc": "pip:grpcio"}
        result = validate_disk_compliance(
            rel, str(tmp_path), import_map=import_map,
        )
        issues = _import_issues(result)
        assert len(issues) == 1
        assert "alloydbengine" in issues[0]["symbol"]

    def test_import_map_empty_flags_all(self, tmp_path):
        """Empty import map means nothing is allowed."""
        rel = _write_py(tmp_path, "svc/app.py", "import os\n")
        result = validate_disk_compliance(
            rel, str(tmp_path), import_map={},
        )
        issues = _import_issues(result)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# Scoring integration — semantic_issues degrade the score
# ---------------------------------------------------------------------------


class TestScoringIntegration:
    def test_phantom_imports_degrade_score(self, tmp_path):
        """4 phantom imports (error severity, 0.3 each) → semantic_penalty = 0."""
        from startd8.contractors.prime_postmortem import compute_disk_quality_score

        rel = _write_py(
            tmp_path, "svc/app.py",
            "import phantom1\nimport phantom2\nimport phantom3\nimport phantom4\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert len(_import_issues(result)) == 4

        score = compute_disk_quality_score(result)
        # 4 errors × 0.3 = 1.2 → semantic_penalty = max(0, 1.0 - 1.2) = 0.0
        # composite = 1.0*0.4 + 1.0*0.2 + 1.0*0.2 + 0.0*0.2 = 0.80
        assert score == pytest.approx(0.80)

    def test_clean_file_score_unchanged(self, tmp_path):
        """File with only stdlib imports should score 1.0."""
        from startd8.contractors.prime_postmortem import compute_disk_quality_score

        rel = _write_py(tmp_path, "app.py", "import os\nimport sys\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _import_issues(result) == []
        score = compute_disk_quality_score(result)
        assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Backward compatibility — no kwargs, existing behavior preserved
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_no_kwargs_still_works(self, tmp_path):
        """Calling with only positional args produces a valid result."""
        rel = _write_py(tmp_path, "app.py", "import os\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.error is None

    def test_no_kwargs_with_manifest(self, tmp_path):
        """Positional args + manifest still works."""
        from startd8.forward_manifest import (
            ForwardManifest,
            ForwardFileSpec,
            ForwardImportSpec,
        )

        rel = _write_py(tmp_path, "app.py", "import os\n")
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[ForwardImportSpec(kind="import", module="os")],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest)
        assert result.import_completeness == pytest.approx(1.0)

    def test_syntax_error_skips_semantic_checks(self, tmp_path):
        """Files with syntax errors should not have semantic issues."""
        rel = _write_py(tmp_path, "broken.py", "def oops(\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert result.semantic_issues == []

    def test_non_python_file_unaffected(self, tmp_path):
        """Non-Python files should not get import resolution checks."""
        rel_path = "requirements.in"
        (tmp_path / rel_path).write_text("flask\nrequests\n", encoding="utf-8")
        result = validate_disk_compliance(rel_path, str(tmp_path))
        assert result.ast_valid is True
        # No import_resolution issues — only requirements validator runs
        assert all(
            not (isinstance(i, dict) and i.get("category") == "import_resolution")
            for i in result.semantic_issues
        )
