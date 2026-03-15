"""Tests for L4 factory return check and L5 requirements cross-check.

Verifies REQ-SV-501/502 (factory return) and REQ-SV-601/602/603
(orphan dependency detection) from SEMANTIC_VALIDATION_REQUIREMENTS.md.
"""

import pytest

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


def _write_file(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _factory_issues(result):
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "factory_return"
    ]


def _orphan_issues(result):
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "orphan_dependency"
    ]


# ---------------------------------------------------------------------------
# L4: Factory return value check (REQ-SV-501)
# ---------------------------------------------------------------------------


class TestFactoryReturn:
    def test_create_app_with_return_passes(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def create_app():\n"
                "    app = object()\n"
                "    return app\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _factory_issues(result) == []

    def test_create_app_no_return_flagged(self, tmp_path):
        """Run-050 bug: create_app() missing return app."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def create_app():\n"
                "    app = object()\n"
                "    app.config = {}\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert issues[0]["symbol"] == "create_app"

    def test_create_app_bare_return_flagged(self, tmp_path):
        """Bare 'return' without a value is not a valid factory return."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def create_app():\n"
                "    app = object()\n"
                "    return\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1

    def test_make_function_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "factory.py",
            "def make_widget():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "make_widget"

    def test_build_function_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "factory.py",
            "def build_config():\n    x = 1\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "build_config"

    def test_suffix_factory_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "factory.py",
            "def widget_factory():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "widget_factory"

    def test_non_factory_no_return_ok(self, tmp_path):
        """Functions not matching factory patterns are not checked."""
        rel = _write_py(
            tmp_path, "app.py",
            "def process_data():\n    print('done')\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _factory_issues(result) == []

    def test_async_factory_flagged(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "async def create_session():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert len(issues) == 1

    def test_factory_with_conditional_return(self, tmp_path):
        """Factory with a return in an if branch should pass."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def create_app():\n"
                "    app = object()\n"
                "    if True:\n"
                "        return app\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _factory_issues(result) == []

    def test_custom_factory_patterns(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "def new_widget():\n    pass\n",
        )
        # Default patterns don't match "new_" prefix
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _factory_issues(result) == []

        # Custom pattern matches
        result = validate_disk_compliance(
            rel, str(tmp_path), factory_patterns=[r"^new_"],
        )
        issues = _factory_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "new_widget"

    def test_line_number_reported(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            "x = 1\n\ndef create_app():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _factory_issues(result)
        assert issues[0]["line"] == 3


# ---------------------------------------------------------------------------
# L5: Requirements-to-import cross-check (REQ-SV-601)
# ---------------------------------------------------------------------------


class TestRequirementsCoverage:
    def test_used_dep_passes(self, tmp_path):
        """All packages in requirements.in are imported → no issues."""
        _write_file(tmp_path, "svc/requirements.in", "flask\nrequests\n")
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask", "requests"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        assert _orphan_issues(result) == []

    def test_orphan_dep_flagged(self, tmp_path):
        """customjsonformatter in reqs but never imported → warning."""
        _write_file(
            tmp_path, "svc/requirements.in",
            "flask\ncustomjsonformatter\n",
        )
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        issues = _orphan_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["symbol"] == "customjsonformatter"

    def test_alias_mapped_dep_passes(self, tmp_path):
        """grpcio in requirements, 'import grpc' in sibling → passes."""
        _write_file(tmp_path, "svc/requirements.in", "grpcio\n")
        rel = "svc/requirements.in"
        sibling_imports = {"svc/server.py": {"grpc"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        assert _orphan_issues(result) == []

    def test_pyyaml_alias_passes(self, tmp_path):
        """pyyaml in requirements, 'import yaml' in sibling → passes."""
        _write_file(tmp_path, "svc/requirements.in", "pyyaml\n")
        rel = "svc/requirements.in"
        sibling_imports = {"svc/config.py": {"yaml"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        assert _orphan_issues(result) == []

    def test_known_non_import_skipped(self, tmp_path):
        """gunicorn in requirements without import → no warning."""
        _write_file(tmp_path, "svc/requirements.in", "gunicorn\nflask\n")
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        assert _orphan_issues(result) == []

    def test_no_sibling_imports_skips_check(self, tmp_path):
        """Without sibling_imports kwarg, L5 check is skipped entirely."""
        _write_file(
            tmp_path, "svc/requirements.in",
            "flask\ncustomjsonformatter\n",
        )
        rel = "svc/requirements.in"
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _orphan_issues(result) == []

    def test_multiple_orphans(self, tmp_path):
        _write_file(
            tmp_path, "svc/requirements.in",
            "flask\nfake_pkg_one\nfake_pkg_two\n",
        )
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        issues = _orphan_issues(result)
        assert len(issues) == 2
        symbols = {i["symbol"] for i in issues}
        assert symbols == {"fake_pkg_one", "fake_pkg_two"}

    def test_line_number_correct(self, tmp_path):
        _write_file(
            tmp_path, "svc/requirements.in",
            "# comment\nflask\norphan_pkg\n",
        )
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        issues = _orphan_issues(result)
        assert len(issues) == 1
        assert issues[0]["line"] == 3  # line 1=comment, 2=flask, 3=orphan

    def test_version_specifiers_stripped(self, tmp_path):
        _write_file(
            tmp_path, "svc/requirements.in",
            "flask>=2.0\norphan_pkg~=1.0\n",
        )
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"flask"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        issues = _orphan_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "orphan_pkg"

    def test_dotted_import_matches_package(self, tmp_path):
        """opentelemetry.trace import matches opentelemetry-api package."""
        _write_file(tmp_path, "svc/requirements.in", "opentelemetry-api\n")
        rel = "svc/requirements.in"
        sibling_imports = {"svc/app.py": {"opentelemetry", "opentelemetry.trace"}}
        result = validate_disk_compliance(
            rel, str(tmp_path), sibling_imports=sibling_imports,
        )
        assert _orphan_issues(result) == []
