"""Tests for plan ingestion file extraction and file-role inference."""

import pytest

from startd8.workflows.builtin.plan_ingestion_parsing import (
    _extract_file_paths_from_block,
    _infer_file_role,
)


# ---------------------------------------------------------------------------
# _extract_file_paths_from_block
# ---------------------------------------------------------------------------

class TestExtractFilePathsFromBlock:
    def test_dockerfile_extracted(self):
        block = "Build the `Dockerfile` for the service."
        result = _extract_file_paths_from_block(block)
        assert "Dockerfile" in result

    def test_dockerfile_with_path_extracted(self):
        block = "Create `path/to/Dockerfile` for the service."
        result = _extract_file_paths_from_block(block)
        assert "path/to/Dockerfile" in result

    def test_makefile_extracted(self):
        block = "Add a `Makefile` for build automation."
        result = _extract_file_paths_from_block(block)
        assert "Makefile" in result

    def test_dockerfile_dev_extracted(self):
        block = "Create `Dockerfile.dev` for local development."
        result = _extract_file_paths_from_block(block)
        # Dockerfile.dev has a .dev extension which is not in _FILE_EXTENSIONS,
        # but it matches _EXTENSIONLESS_FILENAMES pattern (Dockerfile variant)
        assert "Dockerfile.dev" in result

    def test_cs_file_extracted(self):
        block = "Implement the cart service in `src/main.cs`."
        result = _extract_file_paths_from_block(block)
        assert "src/main.cs" in result

    def test_csproj_file_extracted(self):
        block = "Configure `project.csproj` with the right dependencies."
        result = _extract_file_paths_from_block(block)
        assert "project.csproj" in result

    def test_regular_py_still_works(self):
        block = "Edit `src/service.py` to add the handler."
        result = _extract_file_paths_from_block(block)
        assert "src/service.py" in result

    def test_python_expression_filtered(self):
        block = "Use `logging.INFO` for the log level."
        result = _extract_file_paths_from_block(block)
        assert "logging.INFO" not in result

    def test_typing_expression_filtered(self):
        block = "Import `typing.Any` for type hints."
        result = _extract_file_paths_from_block(block)
        assert "typing.Any" not in result

    def test_multiple_files_extracted(self):
        block = (
            "Create `src/main.go` and `src/util.go` with the "
            "`Dockerfile` for deployment."
        )
        result = _extract_file_paths_from_block(block)
        assert "src/main.go" in result
        assert "src/util.go" in result
        assert "Dockerfile" in result

    def test_proto_file_extracted(self):
        block = "Define the API in `cart.proto`."
        result = _extract_file_paths_from_block(block)
        assert "cart.proto" in result

    def test_yaml_file_extracted(self):
        block = "Add config in `config.yaml`."
        result = _extract_file_paths_from_block(block)
        assert "config.yaml" in result

    def test_no_duplicates(self):
        block = "Use `Dockerfile` and also see `Dockerfile` again."
        result = _extract_file_paths_from_block(block)
        assert result.count("Dockerfile") == 1

    def test_jenkinsfile_extracted(self):
        block = "Add `Jenkinsfile` for CI/CD pipeline."
        result = _extract_file_paths_from_block(block)
        assert "Jenkinsfile" in result

    def test_procfile_extracted(self):
        block = "Create `Procfile` for Heroku deployment."
        result = _extract_file_paths_from_block(block)
        assert "Procfile" in result

    def test_java_file_extracted(self):
        block = "Implement in `CartService.java`."
        result = _extract_file_paths_from_block(block)
        assert "CartService.java" in result


# ---------------------------------------------------------------------------
# _infer_file_role
# ---------------------------------------------------------------------------

class TestInferFileRole:
    def test_csharp_interface_file(self):
        role = _infer_file_role("ICartStore.cs")
        assert "INTERFACE" in role
        assert "FILE ROLE CONSTRAINT" in role
        assert "ICartStore" in role

    def test_csharp_interface_file_ifoo(self):
        role = _infer_file_role("IFoo.cs")
        assert "INTERFACE" in role
        assert "IFoo" in role

    def test_regular_cs_file_empty(self):
        role = _infer_file_role("CartStore.cs")
        assert role == ""

    def test_dockerfile(self):
        role = _infer_file_role("Dockerfile")
        assert "Dockerfile" in role
        assert "FILE ROLE CONSTRAINT" in role

    def test_dockerfile_with_path(self):
        role = _infer_file_role("src/Dockerfile")
        assert "Dockerfile" in role
        assert "FILE ROLE CONSTRAINT" in role

    def test_csproj(self):
        role = _infer_file_role("project.csproj")
        assert "project configuration" in role
        assert "FILE ROLE CONSTRAINT" in role

    def test_sln_file(self):
        role = _infer_file_role("MySolution.sln")
        assert "project configuration" in role

    def test_proto_file(self):
        role = _infer_file_role("cart.proto")
        assert "Protocol Buffer" in role
        assert "FILE ROLE CONSTRAINT" in role

    def test_build_gradle(self):
        role = _infer_file_role("build.gradle")
        assert "build configuration" in role
        assert "FILE ROLE CONSTRAINT" in role

    def test_pom_xml(self):
        role = _infer_file_role("pom.xml")
        assert "build configuration" in role

    def test_regular_py_empty(self):
        role = _infer_file_role("regular.py")
        assert role == ""

    def test_regular_go_empty(self):
        role = _infer_file_role("main.go")
        assert role == ""

    def test_java_interface_file(self):
        role = _infer_file_role("CartStoreInterface.java")
        assert "INTERFACE" in role

    def test_dockerfile_dot_dev(self):
        role = _infer_file_role("Dockerfile.dev")
        assert "Dockerfile" in role

    def test_settings_gradle(self):
        role = _infer_file_role("settings.gradle")
        assert "build configuration" in role

    def test_build_gradle_kts(self):
        role = _infer_file_role("build.gradle.kts")
        assert "build configuration" in role
