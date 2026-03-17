"""Tests for SemanticImportFixStep (REQ-SR-200)."""

from pathlib import Path

import pytest

from startd8.repair.models import RepairContext, RepairStepResult, SemanticDiagnostic
from startd8.repair.steps.semantic_import_fix import SemanticImportFixStep


@pytest.fixture()
def project(tmp_path):
    """Create a flat-layout project structure for import resolution tests."""
    svc = tmp_path / "emailservice"
    svc.mkdir()
    (svc / "email_server.py").write_text("class EmailServiceStub: pass\n")
    (svc / "logger.py").write_text("def getJSONLogger(): pass\n")
    (svc / "email_client.py").write_text("")  # the file under test
    # Another service
    rec = tmp_path / "recommendationservice"
    rec.mkdir()
    (rec / "logger.py").write_text("def getJSONLogger(): pass\n")
    (rec / "client.py").write_text("def main(): pass\n")
    return tmp_path


def _make_diag(symbol, line, file="emailservice/email_client.py"):
    return SemanticDiagnostic(
        category="semantic", file=file,
        message=f"Unresolvable import: '{symbol}'",
        semantic_category="import_resolution",
        severity="error", symbol=symbol, line=line,
    )


def _ctx(project_root, diagnostics):
    return RepairContext(diagnostics=diagnostics, project_root=project_root)


class TestFlatLayoutFromPkgMod:
    """Case 1: from <pkg>.<module> import <names> → from <module> import <names>."""

    def test_simple_rewrite(self, project):
        code = "from emailservice.email_server import EmailServiceStub\n"
        diags = [_make_diag("emailservice.email_server", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from email_server import EmailServiceStub\n" == result.code

    def test_two_imports(self, project):
        code = (
            "from emailservice.email_server import EmailServiceStub\n"
            "from emailservice.logger import getJSONLogger\n"
        )
        diags = [
            _make_diag("emailservice.email_server", 1),
            _make_diag("emailservice.logger", 2),
        ]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from email_server import EmailServiceStub\n" in result.code
        assert "from logger import getJSONLogger\n" in result.code
        assert len(result.metrics["fixes"]) == 2

    def test_multi_name_import(self, project):
        code = "from emailservice.logger import getJSONLogger, get_logger, setup\n"
        diags = [_make_diag("emailservice.logger", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from logger import getJSONLogger, get_logger, setup\n" == result.code

    def test_aliased_import(self, project):
        code = "from emailservice.logger import getJSONLogger as log\n"
        diags = [_make_diag("emailservice.logger", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from logger import getJSONLogger as log\n" == result.code


class TestFlatLayoutFromPkg:
    """Case 2: from <pkg> import <module> → import <module>."""

    def test_bare_import(self, project):
        (project / "emailservice" / "demo_pb2.py").write_text("")
        code = "from emailservice import demo_pb2\n"
        diags = [_make_diag("emailservice", 1)]
        # The symbol for bare imports is just the package name
        # but the semantic validator reports the full "emailservice" as symbol
        # Actually, let's check — for `from emailservice import demo_pb2`,
        # the validator reports symbol="emailservice" or the full thing.
        # The step handles this via Case 2 regex.
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "import demo_pb2\n" == result.code


class TestPackageLayout:
    """No modification when __init__.py exists."""

    def test_package_layout_skipped(self, project):
        (project / "emailservice" / "__init__.py").write_text("")
        code = "from emailservice.email_server import EmailServiceStub\n"
        diags = [_make_diag("emailservice.email_server", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert not result.modified
        assert result.code == code


class TestCrossServiceAmbiguity:
    """Skip when target module exists in importing file's own directory."""

    def test_ambiguous_skipped(self, project):
        """emailservice/email_client.py imports from recommendationservice.logger
        but emailservice/logger.py also exists — ambiguous."""
        code = "from recommendationservice.logger import getJSONLogger\n"
        diags = [_make_diag("recommendationservice.logger", 1, "emailservice/email_client.py")]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert not result.modified  # skipped due to ambiguity

    def test_cross_service_safe(self, project):
        """emailservice/email_client.py imports from recommendationservice.client
        and no client.py in emailservice/ — safe to rewrite."""
        code = "from recommendationservice.client import main\n"
        diags = [_make_diag("recommendationservice.client", 1, "emailservice/email_client.py")]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from client import main\n" == result.code


class TestNonRepairable:
    """Non-local imports are not modified."""

    def test_unknown_package_skipped(self, project):
        code = "from phantom_pkg import X\n"
        diags = [_make_diag("phantom_pkg", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert not result.modified  # phantom_pkg is not a sibling directory

    def test_single_segment_skipped(self, project):
        code = "import nonexistent\n"
        diags = [_make_diag("nonexistent", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert not result.modified  # single segment, nothing to strip


class TestThreeSegmentImport:
    """Three-segment paths strip only the first segment."""

    def test_three_segment(self, project):
        subpkg = project / "emailservice" / "subpkg"
        subpkg.mkdir()
        (subpkg / "module.py").write_text("X = 1\n")
        code = "from emailservice.subpkg.module import X\n"
        diags = [_make_diag("emailservice.subpkg.module", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "from subpkg.module import X\n" == result.code


class TestEdgeCases:
    def test_no_diagnostics(self, project):
        code = "import os\n"
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, []), project / "emailservice" / "email_client.py")
        assert not result.modified

    def test_indented_import(self, project):
        code = "    from emailservice.email_server import EmailServiceStub\n"
        diags = [_make_diag("emailservice.email_server", 1)]
        step = SemanticImportFixStep()
        result = step(code, _ctx(project, diags), project / "emailservice" / "email_client.py")
        assert result.modified
        assert "    from email_server import EmailServiceStub\n" == result.code

    def test_step_name(self):
        assert SemanticImportFixStep().name == "semantic_import_fix"
