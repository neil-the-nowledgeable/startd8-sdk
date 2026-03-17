"""Tests for Go-specific capabilities: goimports cleanup, go.mod generation."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.languages.go import GoLanguageProfile


@pytest.mark.unit
class TestGoPostGenerationCleanup:
    """Tests for GoLanguageProfile.post_generation_cleanup (P2)."""

    def test_skips_non_go_files(self, tmp_path):
        """Non-.go files are ignored."""
        py_file = tmp_path / "main.py"
        py_file.write_text("print('hello')")
        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([py_file], tmp_path)
        assert warnings == []

    def test_skips_nonexistent_files(self, tmp_path):
        """Missing files are silently skipped."""
        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup(
            [tmp_path / "missing.go"], tmp_path,
        )
        assert warnings == []

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_runs_goimports_when_available(self, mock_run, mock_which, tmp_path):
        """goimports is preferred over gofmt."""
        go_file = tmp_path / "main.go"
        go_file.write_text('package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("hi") }\n')

        mock_which.side_effect = lambda name: f"/usr/local/bin/{name}" if name == "goimports" else None
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([go_file], tmp_path)

        assert warnings == []
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "goimports" in call_args[0]
        assert "-w" in call_args

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_falls_back_to_gofmt(self, mock_run, mock_which, tmp_path):
        """Falls back to gofmt when goimports is not installed."""
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n")

        mock_which.side_effect = lambda name: "/usr/local/bin/gofmt" if name == "gofmt" else None
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([go_file], tmp_path)

        # Should warn about missing goimports (but still run gofmt)
        assert any("goimports not found" in w for w in warnings)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gofmt" in call_args[0]

    @patch("shutil.which")
    def test_warns_when_no_go_tools(self, mock_which, tmp_path):
        """Warns when neither goimports nor gofmt is available."""
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n")

        mock_which.return_value = None

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([go_file], tmp_path)

        assert len(warnings) >= 1
        assert any("neither goimports nor gofmt" in w for w in warnings)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_handles_tool_failure(self, mock_run, mock_which, tmp_path):
        """Captures stderr when tool fails."""
        go_file = tmp_path / "main.go"
        go_file.write_text("invalid go code {{{")

        mock_which.side_effect = lambda name: f"/usr/local/bin/{name}" if name == "goimports" else None
        mock_run.return_value = MagicMock(returncode=1, stderr="syntax error")

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([go_file], tmp_path)

        assert len(warnings) == 1
        assert "goimports failed" in warnings[0]
        assert "syntax error" in warnings[0]

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_handles_timeout(self, mock_run, mock_which, tmp_path):
        """Captures timeout."""
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n")

        mock_which.side_effect = lambda name: f"/usr/local/bin/{name}" if name == "goimports" else None
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="goimports", timeout=30)

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup([go_file], tmp_path)

        assert len(warnings) == 1
        assert "timed out" in warnings[0]

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_processes_multiple_files(self, mock_run, mock_which, tmp_path):
        """Processes all .go files in the list."""
        files = []
        for name in ["main.go", "handler.go", "config.go"]:
            f = tmp_path / name
            f.write_text("package main\n")
            files.append(f)

        mock_which.side_effect = lambda name: f"/usr/local/bin/{name}" if name == "goimports" else None
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        profile = GoLanguageProfile()
        warnings = profile.post_generation_cleanup(files, tmp_path)

        assert warnings == []
        assert mock_run.call_count == 3


@pytest.mark.unit
class TestGoModGeneration:
    """Tests for GoLanguageProfile.generate_dependency_file (P3)."""

    def test_basic_go_mod(self):
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="frontend",
            module_path="github.com/GoogleCloudPlatform/microservices-demo/src/frontend",
            dependencies=[
                "google.golang.org/grpc v1.68.0",
                "github.com/sirupsen/logrus v1.9.3",
            ],
        )
        assert "module github.com/GoogleCloudPlatform/microservices-demo/src/frontend" in content
        assert "go 1.23" in content
        assert "require (" in content
        assert "\tgoogle.golang.org/grpc v1.68.0" in content
        assert "\tgithub.com/sirupsen/logrus v1.9.3" in content

    def test_custom_go_version(self):
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="frontend",
            module_path="example.com/frontend",
            dependencies=[],
            metadata={"go_version": "1.22"},
        )
        assert "go 1.22" in content

    def test_at_version_format(self):
        """Handles module@version format."""
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="svc",
            module_path="example.com/svc",
            dependencies=["github.com/gorilla/mux@v1.8.1"],
        )
        assert "\tgithub.com/gorilla/mux v1.8.1" in content

    def test_module_without_version(self):
        """Module without version gets placeholder."""
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="svc",
            module_path="example.com/svc",
            dependencies=["github.com/some/pkg"],
        )
        assert "\tgithub.com/some/pkg v0.0.0" in content

    def test_empty_dependencies(self):
        """No require block when dependencies are empty."""
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="svc",
            module_path="example.com/svc",
            dependencies=[],
        )
        assert "require" not in content
        assert "module example.com/svc" in content

    def test_fallback_module_path(self):
        """Service name used as fallback when module_path is empty."""
        profile = GoLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="myservice",
            module_path="",
            dependencies=[],
        )
        assert "module myservice" in content


@pytest.mark.unit
class TestNodePackageJsonGeneration:
    """Tests for NodeLanguageProfile.generate_dependency_file."""

    def test_basic_package_json(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        import json

        profile = NodeLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="currencyservice",
            module_path="",
            dependencies=["@grpc/grpc-js@^1.10.0", "pino@^8.0.0"],
        )
        pkg = json.loads(content)
        assert pkg["name"] == "currencyservice"
        assert pkg["dependencies"]["@grpc/grpc-js"] == "^1.10.0"
        assert pkg["dependencies"]["pino"] == "^8.0.0"

    def test_empty_deps(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        import json

        profile = NodeLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="svc",
            module_path="",
            dependencies=[],
        )
        pkg = json.loads(content)
        assert "dependencies" not in pkg


@pytest.mark.unit
class TestJavaBuildGradleGeneration:
    """Tests for JavaLanguageProfile.generate_dependency_file."""

    def test_basic_build_gradle(self):
        from startd8.languages.java import JavaLanguageProfile

        profile = JavaLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="adservice",
            module_path="hipstershop.AdService",
            dependencies=[
                "io.grpc:grpc-netty:1.68.0",
                "org.apache.logging.log4j:log4j-core:2.23.0",
            ],
        )
        assert "id 'java'" in content
        assert "implementation 'io.grpc:grpc-netty:1.68.0'" in content
        assert "mainClass = 'hipstershop.AdService'" in content

    def test_custom_java_version(self):
        from startd8.languages.java import JavaLanguageProfile

        profile = JavaLanguageProfile()
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/test"),
            service_name="svc",
            module_path="",
            dependencies=[],
            metadata={"java_version": "17"},
        )
        assert "VERSION_17" in content
